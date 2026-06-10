"""Task runner for executing single extraction tasks.

Supports the refactored pipeline architecture with Reader, Processor,
Reprojector, and Writer plugin callables.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence, cast

import geopandas as gpd
import pandas as pd

from aereo.interfaces.core import (
    ExtractionTask,
    PipelineCallback,
)
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class TaskRunner:
    """Orchestrates the refactored extraction pipeline for a single task.

    Execution order:
        read -> pre-process -> reproject (per cell) -> post-process (per cell) -> write (per cell)
    """

    def __init__(
        self,
        callbacks: Sequence[PipelineCallback] | None = None,
        per_cell_failure_mode: Literal["strict", "best_effort"] = "strict",
    ) -> None:
        """Create a new TaskRunner.

        Args:
            callbacks: Optional pipeline lifecycle callbacks.
            per_cell_failure_mode: How to handle exceptions in the per-cell loop.
                ``"strict"`` aborts the entire task; ``"best_effort"`` skips
                failed cells and continues.
        """
        self.callbacks = list(callbacks or [])
        self.per_cell_failure_mode = per_cell_failure_mode

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

        try:
            # Stage 1: Read
            ds = reader(task)
            self._fire_callbacks("on_download_complete", task)
            self._fire_callbacks("on_read_complete", task, ds)

            # Stage 2: Pre-reproject processing (once, outside cell loop)
            for proc in pre_processors:
                ds = proc(ds)

            # Stage 3-5: Per-patch loop
            artifacts: list[GeoDataFrame[ArtifactSchema]] = []
            for patch in task.patches:
                try:
                    if reprojector is not None:
                        ds_patch = reprojector(ds, patch.geobox)
                        self._fire_callbacks(
                            "on_reproject_complete", task, patch, ds_patch
                        )
                    else:
                        ds_patch = ds

                    for proc in post_processors:
                        ds_patch = proc(ds_patch)

                    if writer is not None:
                        patch_artifacts = writer(ds_patch, task, patch)
                        artifacts.append(patch_artifacts)
                        self._fire_callbacks(
                            "on_patch_write_complete", task, patch, patch_artifacts
                        )
                except Exception as exc:
                    if self.per_cell_failure_mode == "strict":
                        raise
                    self._fire_callbacks("on_task_failed", task, exc)
                    logger.warning(
                        "Patch %s failed, skipping: %s", patch.id, exc, exc_info=True
                    )

            if artifacts:
                artifacts_gdf = gpd.GeoDataFrame(
                    pd.concat(artifacts, ignore_index=True),
                    geometry="geometry",
                )
            else:
                artifacts_gdf = gpd.GeoDataFrame(
                    columns=list(ArtifactSchema.to_schema().columns.keys()),
                    geometry="geometry",
                )

            artifacts_gdf = cast(GeoDataFrame[ArtifactSchema], artifacts_gdf)
            self._fire_callbacks("on_task_complete", task, artifacts_gdf)

            return artifacts_gdf

        except Exception as exc:
            self._fire_callbacks("on_task_failed", task, exc)
            raise
