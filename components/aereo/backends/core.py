"""Local process-based and thread-based execution backends and task runner."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any, Iterable, Mapping, Sequence

from aereo.interfaces import ExecutionBackend, ExtractionTask, merge_params
from aereo.registry import AereoRegistry
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame

logger = logging.getLogger(__name__)


class TaskRunner:
    """Executes a single :class:`ExtractionTask` using the correct plugin."""

    def __init__(
        self,
        registry: AereoRegistry,
        init_params: Mapping[str, Any] | None = None,
    ):
        self.registry = registry
        self._init_params = dict(init_params or {})

    def run(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Resolve the extractor for *task* and run it.

        Resolution order:
          1. ``task.task_context["extractor_hint"]``
          2. ``task.profile.plugin_hints["extract"]``
          3. Auto-discover from ``task.profile.collections``
        """
        # Merge task-level init params (from deserialization) over constructor params
        task_init = dict(self._init_params)
        task_init.update(task.task_context.get("init_params", {}))

        # 1. Hint from task context (highest priority)
        hint = task.task_context.get("extractor_hint")
        if hint and self.registry.has_extractor(hint):
            extractor = self.registry.get_extractor(hint, **task_init)
        else:
            # 2. Fallback to profile hint
            profile_hint = task.profile.plugin_hints.get("extract")
            if profile_hint and self.registry.has_extractor(profile_hint):
                extractor = self.registry.get_extractor(profile_hint, **task_init)
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
                extractor = self.registry.get_extractor(plugin_name, **task_init)

        # 4. Merge params (profile wins)
        effective_params = merge_params(None, task.profile.extract_params)

        # 5. Execute
        return extractor.extract(task, effective_params)


class LocalProcessBackend(ExecutionBackend):
    """Execute tasks locally using sequential or process-based parallelism.

    When *max_workers* is ``None`` or there is only one task, execution is
    sequential.  Otherwise a :class:`ProcessPoolExecutor` is used.
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner | None = None,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        if runner is None:
            raise ValueError("LocalProcessBackend requires a runner")
        if not tasks:
            return []

        if self.max_workers is None or len(tasks) == 1:
            # Sequential path — simplest, easiest to debug, no process overhead
            return [runner.run(t) for t in tasks]

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
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


class ThreadBackend(ExecutionBackend):
    """Execute tasks locally using thread-based parallelism.

    This backend is ideal for **I/O-bound** extractors (e.g. those that spend
    most of their time waiting on HTTP requests for COG tiles).  Because
    threads share memory, there is no pickling overhead and no need for
    extractors to be serialisable across process boundaries.

    When *max_workers* is ``None`` or there is only one task, execution is
    sequential.  Otherwise a :class:`ThreadPoolExecutor` is used.
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner | None = None,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        if runner is None:
            raise ValueError("ThreadBackend requires a runner")
        if not tasks:
            return []

        if self.max_workers is None or len(tasks) == 1:
            # Sequential path — simplest, easiest to debug
            return [runner.run(t) for t in tasks]

        results: list[GeoDataFrame[ArtifactSchema] | None] = [None] * len(tasks)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(runner.run, task): i for i, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.error(
                        "thread_task_failed",
                        extra={"task_index": idx, "error": str(exc)},
                    )
                    raise

        return [r for r in results if r is not None]
