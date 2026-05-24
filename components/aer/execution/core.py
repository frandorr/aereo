"""Execution backends and task runner for AER extraction tasks."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Protocol, Sequence

from aer.interfaces import ExtractionTask, merge_params
from aer.registry import AerRegistry
from aer.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

logger = logging.getLogger(__name__)


class TaskStaging(Protocol):
    """Protocol for staging serialized tasks to remote storage and loading results.

    Concrete implementations handle upload/download for a specific object-store
    backend (e.g. S3, GCS, Azure Blob).
    """

    bucket: str

    def stage(self, src_dir: Path, job_id: str, task_idx: int) -> str:
        """Upload a serialized task directory and return its URI.

        Args:
            src_dir: Directory containing ``task_assets.parquet`` and
                ``task_meta.json`` produced by :class:`aer.serialization.TaskSerializer`.
            job_id: Logical job identifier for grouping staged tasks.
            task_idx: Index of the task within the job.

        Returns:
            A URI (e.g. ``s3://bucket/aer-tasks/{job_id}/{task_idx}/``) that the
            remote worker can use to retrieve the task.
        """
        ...

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        """Load artifact results from a manifest URI.

        Args:
            manifest_uri: URI pointing to a manifest produced by the remote worker
                (e.g. ``s3://bucket/results/{job_id}/{task_idx}/manifest.json``).

        Returns:
            A validated ``GeoDataFrame[ArtifactSchema]`` with the extracted artifacts.
        """
        ...


class ExecutionBackend(Protocol):
    """Protocol for pluggable task execution backends.

    Backends decide **where** and **how** a batch of :class:`ExtractionTask`
    objects are executed.  Local backends use the supplied *runner* directly;
    remote backends may serialize tasks and dispatch to external workers.
    """

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        """Execute *tasks* and yield or return their results.

        Because the return type is :class:`Iterable`, implementations are free
        to process tasks asynchronously and yield results as they arrive,
        enabling streaming consumption by the caller.

        Args:
            tasks: The extraction tasks to run.
            runner: A client-side :class:`TaskRunner` that knows how to execute
                a single task using the correct local plugin.
        """
        ...


class TaskRunner:
    """Executes a single :class:`ExtractionTask` using the correct plugin."""

    def __init__(self, registry: AerRegistry):
        self.registry = registry

    def run(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Resolve the extractor for *task* and run it.

        Resolution order:
          1. ``task.task_context["extractor_hint"]``
          2. ``task.profile.plugin_hints["extract"]``
          3. Auto-discover from ``task.profile.collections``
        """
        # 1. Hint from task context (highest priority)
        hint = task.task_context.get("extractor_hint")
        if hint and self.registry.has_extractor(hint):
            extractor = self.registry.get_extractor(hint)
        else:
            # 2. Fallback to profile hint
            profile_hint = task.profile.plugin_hints.get("extract")
            if profile_hint and self.registry.has_extractor(profile_hint):
                extractor = self.registry.get_extractor(profile_hint)
            else:
                # 3. Auto-discover from collections
                plugin_name: str | None = None
                for collection in task.profile.collections:
                    plugin_names = self.registry.find_extractors_for(collection)
                    if plugin_names:
                        plugin_name = plugin_names[0]
                        break
                if plugin_name is None:
                    raise ValueError(
                        f"No extractor plugin found for profile: {task.profile.name}"
                    )
                extractor = self.registry.get_extractor(plugin_name)

        # 4. Merge params (profile wins)
        effective_params = merge_params(None, task.profile.extract_params)

        # 5. Execute
        return extractor.extract(task, effective_params)


def setup_gdal_worker() -> None:
    """Configure GDAL environment variables once per process lifecycle.

    These settings cache connections and headers, improving performance for
    remote COG access via VSICURL.
    """
    os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    os.environ["GDAL_HTTP_MERGE_CONSECUTIVE_RANGES"] = "YES"
    os.environ["GDAL_HTTP_MULTIPLEX"] = "YES"
    os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif,.tiff,.vrt,.xml,.json"


class LocalProcessBackend:
    """Execute tasks locally using sequential or process-based parallelism.

    When *max_workers* is ``None`` or there is only one task, execution is
    sequential.  Otherwise a :class:`ProcessPoolExecutor` is used with
    :func:`setup_gdal_worker` as the worker initializer.
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        if not tasks:
            return []

        if self.max_workers is None or len(tasks) == 1:
            # Sequential path — simplest, easiest to debug, no process overhead
            return [runner.run(t) for t in tasks]

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        with ProcessPoolExecutor(
            max_workers=self.max_workers,
            initializer=setup_gdal_worker,
        ) as executor:
            futures = {
                executor.submit(runner.run, task): i for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error(
                        "local_task_failed",
                        extra={"task_index": idx, "error": str(exc)},
                    )
                    raise

        # Filter out any None values (shouldn't happen unless empty input)
        return [r for r in results if r is not None]
