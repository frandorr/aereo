"""Task runner for executing single extraction tasks.

Supports the refactored pipeline architecture with Reader, Processor,
Reprojector, and Writer plugin callables.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence, cast

import geopandas as gpd
import pandas as pd
import xarray as xr

from aereo.cache import TaskResultCache
from aereo.interfaces.core import (
    ExtractionTask,
    PipelineCallback,
)
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()

_STRICT_MODE = "strict"
_BEST_EFFORT_MODE = "best_effort"


def _build_artifacts_gdf(
    artifacts: list[GeoDataFrame[ArtifactSchema]],
) -> GeoDataFrame[ArtifactSchema]:
    """Build a validated GeoDataFrame from a list of per-patch artifact frames.

    Args:
        artifacts: Per-patch artifact GeoDataFrames. If empty, an empty
            schema-valid frame is returned.

    Returns:
        A validated GeoDataFrame containing all artifacts.
    """
    if artifacts:
        gdf = gpd.GeoDataFrame(
            pd.concat(artifacts, ignore_index=True),
            geometry="geometry",
        )
    else:
        gdf = gpd.GeoDataFrame(
            columns=list(ArtifactSchema.to_schema().columns.keys()),
            geometry="geometry",
        )
    return cast(GeoDataFrame[ArtifactSchema], gdf)


class TaskRunner:
    """Orchestrates the refactored extraction pipeline for a single task.

    Execution order:
        read -> pre-process -> reproject (per cell) -> post-process (per cell) -> write (per cell)
    """

    def __init__(
        self,
        callbacks: Sequence[PipelineCallback] | None = None,
        per_cell_failure_mode: Literal["strict", "best_effort"] = _STRICT_MODE,
        cache: TaskResultCache | None = None,
    ) -> None:
        """Create a new TaskRunner.

        Args:
            callbacks: Optional pipeline lifecycle callbacks.
            per_cell_failure_mode: How to handle exceptions in the per-cell loop.
                ``"strict"`` aborts the entire task; ``"best_effort"`` skips
                failed cells and continues.
            cache: Optional per-task artifact catalog cache. When provided and
                ``task.job.overwrite`` is False, cached results are returned
                without re-executing the pipeline.
        """
        self.callbacks = list(callbacks or [])
        self.per_cell_failure_mode = per_cell_failure_mode
        self.cache = cache

    def _fire_callbacks(self, event: str, *args: Any) -> None:
        """Fire a lifecycle event across all registered callbacks.

        Args:
            event: The callback method name to invoke.
            *args: Positional arguments to pass to the callback.
        """
        for cb in self.callbacks:
            getattr(cb, event)(*args)

    def run(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Execute the full pipeline for *task*.

        Args:
            task: The extraction task to execute.

        Returns:
            A ``GeoDataFrame[ArtifactSchema]`` containing all extracted artifacts.

        Raises:
            ValueError: If any required pipeline stage cannot be resolved.
            Exception: In ``strict`` mode, any per-cell exception aborts the task.
        """
        reader = task.extract.read
        reprojector = task.extract.reproject
        writer = task.extract.write
        pre_processors = task.extract.preprocess
        post_processors = task.extract.postprocess

        if reader is None:
            raise ValueError("Pipeline must contain a Reader stage.")

        self._fire_callbacks("on_task_start", task)

        if self.cache is not None and not task.job.overwrite:
            cached = self.cache.load(task)
            if cached is not None:
                self._fire_callbacks("on_task_cache_hit", task)
                self._fire_callbacks("on_task_complete", task, cached)
                return cached
            self._fire_callbacks("on_task_cache_miss", task)

        try:
            # Stage 1: Read
            ds = reader(task)
            self._fire_callbacks("on_download_complete", task)
            self._fire_callbacks("on_read_complete", task, ds)

            # Stage 2: Pre-reproject processing (once, outside cell loop)
            for proc in pre_processors:
                ds = proc(ds)

            # Stage 3: Reproject (once per task, outside cell loop)
            reprojected_map: dict[str, xr.Dataset] | None = None
            if reprojector is not None:
                reprojected_map = reprojector(ds, task)
                if set(reprojected_map) != {p.id for p in task.patches}:
                    raise ValueError(
                        "Reprojector did not return a dataset for every patch in the task."
                    )

            # Stage 4-5: Per-patch write loop
            artifacts: list[GeoDataFrame[ArtifactSchema]] = []
            for patch in task.patches:
                try:
                    ds_patch = (
                        reprojected_map[patch.id] if reprojected_map is not None else ds
                    )

                    if reprojected_map is not None:
                        self._fire_callbacks(
                            "on_reproject_complete", task, patch, ds_patch
                        )

                    for proc in post_processors:
                        ds_patch = proc(ds_patch)

                    if writer is not None:
                        patch_artifacts = writer(ds_patch, task, patch)
                        artifacts.append(patch_artifacts)
                        self._fire_callbacks(
                            "on_patch_write_complete", task, patch, patch_artifacts
                        )
                except Exception as exc:
                    if self.per_cell_failure_mode == _STRICT_MODE:
                        raise
                    self._fire_callbacks("on_task_failed", task, exc)
                    logger.warning(
                        "Patch %s failed, skipping: %s", patch.id, exc, exc_info=True
                    )

            artifacts_gdf = _build_artifacts_gdf(artifacts)
            if self.cache is not None:
                self.cache.save(task, artifacts_gdf)
            self._fire_callbacks("on_task_complete", task, artifacts_gdf)

            return artifacts_gdf

        except Exception as exc:
            self._fire_callbacks("on_task_failed", task, exc)
            raise
