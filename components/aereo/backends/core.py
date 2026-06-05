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
    Processor,
    Reader,
    Reprojector,
    Writer,
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
        # Find reader, reprojector, writer in task.pipeline
        reader = None
        reprojector = None
        writer = None
        reproject_idx = -1
        writer_idx = -1

        for idx, plugin in enumerate(task.pipeline):
            if isinstance(plugin, Reader):
                reader = plugin
            elif isinstance(plugin, Reprojector):
                reprojector = plugin
                reproject_idx = idx
            elif isinstance(plugin, Writer):
                writer = plugin
                writer_idx = idx

        if reader is None:
            raise ValueError("Pipeline must contain a Reader stage.")
        if reprojector is None:
            raise ValueError("Pipeline must contain a Reprojector stage.")
        if writer is None:
            raise ValueError("Pipeline must contain a Writer stage.")

        pre_processors = cast(Sequence[Processor], task.pipeline[1:reproject_idx])
        post_processors = cast(
            Sequence[Processor], task.pipeline[reproject_idx + 1 : writer_idx]
        )

        self._fire_callbacks("on_task_start", task)

        try:
            # Stage 1: Read
            ds = reader(task)
            self._fire_callbacks("on_download_complete", task)
            self._fire_callbacks("on_read_complete", task, ds)

            # Stage 2: Pre-reproject processing (once, outside cell loop)
            for proc in pre_processors:
                ds = proc(ds)

            # Stage 3-5: Per-cell loop
            artifacts: list[GeoDataFrame[ArtifactSchema]] = []
            for cell in task.grid_cells:
                try:
                    # Spatial parameters from reprojector
                    resolution = int(reprojector.resolution)
                    padding = getattr(reprojector, "padding", None) or 0
                    conform_to_shape = getattr(reprojector, "conform_to", None)

                    geobox = cell.area_def(
                        resolution=resolution,
                        padding=padding,
                        margin=task.grid_config.target_grid_margin,
                        conform_to=conform_to_shape,
                    )
                    ds_cell = reprojector(ds, geobox)
                    self._fire_callbacks("on_reproject_complete", task, cell, ds_cell)

                    for proc in post_processors:
                        ds_cell = proc(ds_cell)

                    cell_artifacts = writer(ds_cell, task, cell)
                    artifacts.append(cell_artifacts)

                    self._fire_callbacks(
                        "on_cell_complete", task, cell, ds_cell, cell_artifacts
                    )
                except Exception as exc:
                    if self.per_cell_failure_mode == "strict":
                        raise
                    self._fire_callbacks("on_task_failed", task, exc)
                    logger.warning(
                        "Cell %s failed, skipping: %s", cell.id(), exc, exc_info=True
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
