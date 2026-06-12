"""Core client implementation for the Aereo geospatial pipeline.

This module defines :class:`AereoClient` and its supporting utilities.
"""

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any, cast

import pandas as pd
from aereo.backends import LocalProcessBackend, TaskRunner
from aereo.interfaces import (
    ExtractConfig,
    ExecutionBackend,
    ExtractionTask,
    GridConfig,
    PatchConfig,
    SearchProvider,
)
from aereo.interfaces import normalize_geometry_input
from aereo.schemas import ArtifactSchema, AssetSchema
from aereo.pipeline import ExtractionJob
from aereo.task_builder import prepare_for_extraction
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()

DEFAULT_CELLS_PER_TASK = 50


class FailureMode(str, Enum):
    """Determines pipeline behavior when partial or total plugin failures occur."""

    STRICT = "strict"
    BEST_EFFORT = "best_effort"


def normalize_geometry(geom: Any) -> BaseGeometry | None:
    """Ensures input geometries are Shapely objects before passing to Plugins.

    Args:
        geom: Geometry input (dict, BaseGeometry, path string/Path, or None).

    Returns:
        A Shapely BaseGeometry, or None if input was None.

    Raises:
        ValueError: If the geometry format is unsupported.
    """
    return normalize_geometry_input(geom)


class AereoClient:
    """Core external entrypoint orchestrating the Geospatial pipeline.

    Responsibilities:
    - Accepts user queries and parameters
    - Executes search dispatch to remote plugin APIs
    - Prepares and distributes extraction tasks dynamically based on results
    """

    def __init__(
        self,
        grid_config: GridConfig | None = None,
        patch_config: PatchConfig | None = None,
        aoi: BaseGeometry | dict | None = None,
        backend: ExecutionBackend | None = None,
        cells_per_task: int | None = None,
    ):
        """Initialize the AereoClient.

        Args:
            grid_config: Default grid configuration for extraction.
            patch_config: Default patch configuration for ML extraction.
            aoi: Default area of interest geometry.
            backend: Default execution backend.
            cells_per_task: Default number of grid cells per extraction task.
        """
        self._grid_config = grid_config
        self._patch_config = patch_config
        self._aoi = normalize_geometry(aoi)
        self._backend = backend
        self._cells_per_task = cells_per_task

    def search(
        self,
        search_provider: SearchProvider,
    ) -> GeoDataFrame[AssetSchema]:
        """Execute search via the given search provider.

        Args:
            search_provider: SearchProvider instance to execute.

        Returns:
            A verified GeoDataFrame of combined search results.
        """
        logger.info("search_called", provider=search_provider.__class__.__name__)
        return search_provider()

    def prepare_tasks(
        self,
        search_results: GeoDataFrame[AssetSchema],
        extract: ExtractConfig,
        grid_config: GridConfig | None = None,
        patch_config: PatchConfig | None = None,
        output_uri: str | None = None,
        target_aoi: BaseGeometry | dict | str | Path | None = None,
        cells_per_task: int | None = None,
        job: ExtractionJob | None = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by start time and distributes batches into tasks.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            extract: Declarative configuration of extraction stages to execute.
            grid_config: Explicit tiling specification. Falls back to client default.
            patch_config: Explicit patch configuration. Falls back to client default.
            output_uri: An optional URI defining output path.
            target_aoi: Optional AOI geometry used to clip prepared tasks. Falls back
                to the client default AOI if not provided.
            cells_per_task: Max grid cells per ExtractionTask. Falls back to client default.
            job: Optional parent ``ExtractionJob`` to attach to each task.

        Returns:
            A Sequence of prepared ExtractionTasks.
        """
        if search_results.empty:
            return []

        grid_config = self._grid_config if grid_config is None else grid_config
        if grid_config is None:
            raise ValueError(
                "grid_config must be provided either as a method argument or as a client default."
            )

        patch_config = self._patch_config if patch_config is None else patch_config
        if patch_config is None:
            raise ValueError(
                "patch_config must be provided either as a method argument or as a client default."
            )

        effective_cells_per_task = (
            cells_per_task
            if cells_per_task is not None
            else (self._cells_per_task or DEFAULT_CELLS_PER_TASK)
        )

        effective_aoi = (
            normalize_geometry_input(target_aoi)
            if target_aoi is not None
            else self._aoi
        )

        return prepare_for_extraction(
            search_results=search_results,
            grid_config=grid_config,
            patch_config=patch_config,
            extract=extract,
            output_uri=output_uri or "",
            target_aoi=effective_aoi,
            cells_per_task=effective_cells_per_task,
            job=job,
        )

    def execute_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        backend: ExecutionBackend | None = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Execute a sequence of ExtractionTasks through a configurable backend.

        Args:
            tasks: A sequence of ExtractionTasks, usually from prepare_tasks.
            backend: An ExecutionBackend implementation. Defaults to LocalProcessBackend().
            failure_mode: STRICT raises on the first failure; BEST_EFFORT processes tasks individually.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        if not tasks:
            logger.warning("execute_tasks_empty", reason="No tasks provided")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        backend = backend or self._backend or LocalProcessBackend()
        runner = TaskRunner(
            per_cell_failure_mode="strict"
            if failure_mode == FailureMode.STRICT
            else "best_effort"
        )

        logger.info(
            "execute_tasks_start",
            task_count=len(tasks),
            backend=backend.__class__.__name__,
            failure_mode=failure_mode.value,
        )

        if failure_mode == FailureMode.BEST_EFFORT:
            results: list[GeoDataFrame[ArtifactSchema]] = []
            for task in tasks:
                try:
                    task_results = list(backend.run_tasks([task], runner))
                    if task_results:
                        results.append(task_results[0])
                except Exception:
                    logger.warning("task_failed_best_effort", exc_info=True)
            if not results:
                logger.warning("execute_tasks_empty_result")
                return cast(GeoDataFrame, ArtifactSchema.empty())

            concatenated = pd.concat(results, ignore_index=True)
            return cast(GeoDataFrame, ArtifactSchema.validate(concatenated))

        # STRICT mode — batch for efficiency, raise on first failure
        try:
            results = list(backend.run_tasks(tasks, runner))
        except Exception:
            logger.error("execute_tasks_failed", exc_info=True)
            raise

        if not results:
            logger.warning("execute_tasks_empty_result")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        concatenated = pd.concat(results, ignore_index=True)
        return cast(GeoDataFrame, ArtifactSchema.validate(concatenated))
