"""Task runner for resolving and executing single extraction tasks.

Supports the refactored pipeline architecture with Reader, Processor,
Reprojector, and Writer plugin stages.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence, cast

import geopandas as gpd
import pandas as pd

from aereo.interfaces.core import (
    ExtractionTask,
    PipelineCallback,
    PluginStage,
    Processor,
    Reader,
    Reprojector,
    Writer,
)
from aereo.registry import AereoRegistry
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class TaskRunner:
    """Orchestrates the refactored extraction pipeline for a single task.

    Execution order:
        download (optional) -> read -> pre-process -> reproject (per cell)
        -> post-process (per cell) -> write (per cell)

    Resolution follows a three-tier priority for each stage:
        1. ``task.task_context["{stage}_hint"]``
        2. ``task.profile.plugin_hints["{stage}"]``
        3. Auto-discover from ``task.profile.collections``
    """

    def __init__(
        self,
        registry: AereoRegistry,
        init_params: Mapping[str, Any] | None = None,
        callbacks: Sequence[PipelineCallback] | None = None,
        per_cell_failure_mode: Literal["strict", "best_effort"] = "strict",
    ) -> None:
        """Create a new TaskRunner.

        Args:
            registry: Plugin registry used to look up pipeline stages.
            init_params: Optional default parameters passed to every plugin
                constructor.
            callbacks: Optional pipeline lifecycle callbacks.
            per_cell_failure_mode: How to handle exceptions in the per-cell loop.
                ``"strict"`` aborts the entire task; ``"best_effort"`` skips
                failed cells and continues.
        """
        self.registry = registry
        self._init_params = dict(init_params or {})
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
        task_init = dict(self._init_params)
        task_init.update(task.task_context.get("init_params", {}))

        # Resolve pipeline stages
        reader = self._resolve_reader(task, task_init)
        reprojector = self._resolve_reprojector(task, task_init)
        pre_processors = self._resolve_processors(task, task_init, phase="pre")
        post_processors = self._resolve_processors(task, task_init, phase="post")
        writer = self._resolve_writer(task, task_init)

        self._fire_callbacks("on_task_start", task)

        try:
            # Stage 1: Read
            ds = reader.read(task, {})
            self._fire_callbacks("on_download_complete", task)
            self._fire_callbacks("on_read_complete", task, ds)

            # Stage 2: Pre-reproject processing (once, outside cell loop)
            for proc in pre_processors:
                ds = proc.process(ds, {})

            # Stage 3-5: Per-cell loop
            artifacts: list[GeoDataFrame[ArtifactSchema]] = []
            for cell in task.grid_cells:
                try:
                    geobox = cell.area_def(
                        resolution=int(task.profile.resolution),
                        padding=getattr(task.profile, "padding", None) or 0,
                        margin=task.grid_config.target_grid_margin,
                        conform_to=getattr(task.profile, "conform_to", None),
                    )
                    ds_cell = reprojector.reproject(ds, geobox, {})
                    self._fire_callbacks("on_reproject_complete", task, cell, ds_cell)

                    for proc in post_processors:
                        ds_cell = proc.process(ds_cell, {})

                    cell_artifacts = writer.write(ds_cell, task, cell, {})
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

    # --- Resolution helpers ---

    def _resolve_reader(self, task: ExtractionTask, init: dict[str, Any]) -> Reader:
        return self._resolve_stage(task, task.profile.read, init, type_label="reader")

    def _resolve_reprojector(
        self, task: ExtractionTask, init: dict[str, Any]
    ) -> Reprojector:
        return self._resolve_stage(
            task, task.profile.reproject, init, type_label="reprojector"
        )

    def _resolve_writer(self, task: ExtractionTask, init: dict[str, Any]) -> Writer:
        return self._resolve_stage(task, task.profile.write, init, type_label="writer")

    def _resolve_stage(
        self,
        task: ExtractionTask,
        stage: PluginStage | None,
        init: dict[str, Any],
        *,
        type_label: str,
    ) -> Any:
        """Resolve a single pipeline stage plugin.

        Args:
            task: The extraction task.
            stage: The configured PluginStage dict, if any.
            init: Context kwargs for the plugin.
            type_label: Registry type label (e.g. "reader").

        Returns:
            An instantiated plugin.
        """
        from aereo.interfaces import unpack_stage

        if stage:
            plugin_name, params = unpack_stage(stage)
            final_init = {**init, **params}
            if self.registry.has(type_label, plugin_name):
                return self.registry.get(type_label, plugin_name, **final_init)
            raise ValueError(
                f"Plugin '{plugin_name}' not found for type '{type_label}'"
            )

        # Fallback to auto-discovery
        plugin_name = self._auto_discover_plugin(task, type_label)
        if plugin_name is None:
            raise ValueError(
                f"No {type_label} plugin found for profile: {task.profile.name}"
            )

        return self.registry.get(type_label, plugin_name, **init)

    def _resolve_processors(
        self, task: ExtractionTask, init: dict[str, Any], phase: str = "post"
    ) -> list[Processor]:
        """Resolve pre or post processors.

        Args:
            task: The extraction task.
            init: Context kwargs.
            phase: 'pre' or 'post'.
        """
        from aereo.interfaces import unpack_stage

        processors: list[Processor] = []
        stages = (
            task.profile.pre_processors
            if phase == "pre"
            else task.profile.post_processors
        )

        for stage in stages:
            if isinstance(stage, str):
                plugin_name, params = stage, {}
            else:
                plugin_name, params = unpack_stage(stage)

            if self.registry.has("processor", plugin_name):
                final_init = {**init, **params}
                processors.append(
                    self.registry.get("processor", plugin_name, **final_init)
                )
            else:
                logger.warning("Processor '%s' not found, skipping.", plugin_name)

        return processors

    def _auto_discover_plugin(
        self, task: ExtractionTask, type_label: str
    ) -> str | None:
        """Auto-discover a plugin name from profile collections."""
        for collection in task.profile.collections:
            plugin_names = self.registry.find_for(type_label, collection)
            if plugin_names:
                return plugin_names[0]
        return None
