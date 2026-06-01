"""Task runner for resolving and executing single extraction tasks.

Supports the refactored pipeline architecture with Reader, Processor,
Reprojector, and Writer plugin stages.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence, cast

import geopandas as gpd
import pandas as pd

from aereo.interfaces import (
    Downloader,
    ExtractionTask,
    PipelineCallback,
    Processor,
    Reader,
    Reprojector,
    Writer,
    merge_params,
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
        """Fire a lifecycle event across all registered callbacks."""
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
        processors = self._resolve_processors(task, task_init)
        writer = self._resolve_writer(task, task_init)

        pre = [p for p in processors if p.stage == "pre_reproject"]
        post = [p for p in processors if p.stage == "post_reproject"]

        # Build effective params for each stage
        download_params = merge_params(
            getattr(task.profile, "extract_params", {}),
            getattr(task.profile, "download_params", {}),
        )
        read_params = merge_params(
            task.profile.extract_params, task.profile.read_params
        )
        process_params = merge_params(
            task.profile.extract_params, task.profile.process_params
        )
        write_params = merge_params(
            task.profile.extract_params, task.profile.write_params
        )

        self._fire_callbacks("on_task_start", task)

        try:
            # Stage 0: Download (optional)
            downloader = self._resolve_downloader(task, task_init)
            if downloader is not None:
                downloader.download(task, download_params)
                self._fire_callbacks("on_download_complete", task)

            # Stage 1: Read
            ds = reader.read(task, read_params)
            if downloader is None:
                self._fire_callbacks("on_download_complete", task)
            self._fire_callbacks("on_read_complete", task, ds)

            # Stage 2: Pre-reproject processing (once, outside cell loop)
            for proc in pre:
                ds = proc.process(ds, process_params)

            # Stage 3-5: Per-cell loop
            artifacts: list[GeoDataFrame[ArtifactSchema]] = []
            for cell in task.grid_cells:
                try:
                    geobox = cell.area_def(
                        resolution=int(task.profile.resolution),
                        padding=task.profile.padding or 0,
                        margin=task.grid_config.target_grid_margin,
                        conform_to=task.profile.conform_to,
                    )
                    ds_cell = reprojector.reproject(ds, geobox, read_params)
                    self._fire_callbacks("on_reproject_complete", task, cell, ds_cell)

                    for proc in post:
                        ds_cell = proc.process(ds_cell, process_params)

                    cell_artifacts = writer.write(ds_cell, task, cell, write_params)
                    artifacts.append(cell_artifacts)

                    self._fire_callbacks(
                        "on_cell_write_complete", task, cell, cell_artifacts
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

    def _resolve_downloader(
        self, task: ExtractionTask, init: dict[str, Any]
    ) -> Downloader | None:
        """Resolve an optional downloader plugin.

        Returns ``None`` when no downloader is configured, allowing the
        reader to handle its own downloads.
        """
        try:
            return self._resolve_stage(
                task, init, stage="download", type_label="downloader"
            )
        except ValueError:
            return None

    def _resolve_reader(self, task: ExtractionTask, init: dict[str, Any]) -> Reader:
        return self._resolve_stage(
            task, init, stage="read", type_label="reader", fallback="extractor"
        )

    def _resolve_reprojector(
        self, task: ExtractionTask, init: dict[str, Any]
    ) -> Reprojector:
        return self._resolve_stage(
            task, init, stage="reproject", type_label="reprojector"
        )

    def _resolve_processors(
        self, task: ExtractionTask, init: dict[str, Any]
    ) -> list[Processor]:
        """Resolve all processors declared in plugin_hints['processors']."""
        hints: list[str] = []

        # 1. Task context hint
        task_hint = task.task_context.get("processor_hints") or task.task_context.get(
            "processors"
        )
        if task_hint:
            hints = [h.strip() for h in str(task_hint).split(",")]

        # 2. Profile hint
        if not hints:
            profile_hint = task.profile.plugin_hints.get("processors")
            if profile_hint:
                hints = [h.strip() for h in str(profile_hint).split(",")]

        if not hints:
            return []

        processors: list[Processor] = []
        for name in hints:
            if self.registry.has("processor", name):
                processors.append(self.registry.get("processor", name, **init))
            else:
                logger.warning(f"Processor '{name}' not found, skipping.")
        return processors

    def _resolve_writer(self, task: ExtractionTask, init: dict[str, Any]) -> Writer:
        return self._resolve_stage(
            task, init, stage="writer", type_label="writer", fallback="extractor"
        )

    def _resolve_stage(
        self,
        task: ExtractionTask,
        init: dict[str, Any],
        *,
        stage: str,
        type_label: str,
        fallback: str | None = None,
    ) -> Any:
        """Generic three-tier resolution for a single pipeline stage.

        Args:
            task: The extraction task.
            init: Constructor kwargs for the plugin.
            stage: Key used in ``task_context`` and ``plugin_hints``.
            type_label: Registry type label (e.g. "reader", "writer").
            fallback: Optional fallback type label if the primary is not found.

        Returns:
            An instantiated plugin.

        Raises:
            ValueError: If no plugin can be resolved.
        """
        # 1. Task context hint (check both stage_hint and type_label_hint)
        hint = task.task_context.get(f"{stage}_hint") or task.task_context.get(
            f"{type_label}_hint"
        )
        if hint and self.registry.has(type_label, hint):
            return self.registry.get(type_label, hint, **init)
        if fallback and hint and self.registry.has(fallback, hint):
            return self.registry.get(fallback, hint, **init)

        # 2. Profile hint
        profile_hint = task.profile.plugin_hints.get(
            stage
        ) or task.profile.plugin_hints.get(type_label)
        if profile_hint and self.registry.has(type_label, profile_hint):
            return self.registry.get(type_label, profile_hint, **init)
        if fallback and profile_hint and self.registry.has(fallback, profile_hint):
            return self.registry.get(fallback, profile_hint, **init)

        # 3. Auto-discover from collections
        plugin_name: str | None = None
        for collection in task.profile.collections:
            plugin_names = self.registry.find_for(type_label, collection)
            if plugin_names:
                plugin_name = plugin_names[0]
                break

        if plugin_name is None and fallback:
            for collection in task.profile.collections:
                plugin_names = self.registry.find_for(fallback, collection)
                if plugin_names:
                    plugin_name = plugin_names[0]
                    break

        if plugin_name is None:
            raise ValueError(
                f"No {type_label} plugin found for profile: {task.profile.name}"
            )

        return self.registry.get(type_label, plugin_name, **init)
