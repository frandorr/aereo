from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Sequence, cast

import pandas as pd
from aereo.backends import LocalProcessBackend, TaskRunner
from aereo.driver import AereoDriver
from aereo.interfaces import (
    AereoProfile,
    ExecutionBackend,
    ExtractionTask,
    GridConfig,
    PipelineProfile,
)
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import shape
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
        geom: Geometry input (dict, BaseGeometry, or None).

    Returns:
        A Shapely BaseGeometry, or None if input was None.

    Raises:
        ValueError: If the geometry format is unsupported.
    """
    if geom is None:
        return None
    if isinstance(geom, dict):
        return shape(geom)
    if isinstance(geom, BaseGeometry):
        return geom
    raise ValueError(
        f"Invalid geometry format. Expected dict or BaseGeometry, got {type(geom)}"
    )


class _DriverTaskRunner:
    """Lightweight runner that delegates task execution to an AereoDriver."""

    def __init__(self, driver: AereoDriver) -> None:
        self._driver = driver

    def run(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Execute a single extraction task via the Hamilton driver."""
        return self._driver.extract(task)


class AereoClient:
    """Core external entrypoint orchestrating the Geospatial pipeline.

    Responsibilities:
    - Accepts user queries and parameters
    - Maps profiles to registered plugins with optional profile-level hints
    - Executes parallel fan-out search dispatch via the Hamilton-based driver
    - Collapses and validates results into a unified DataFrame
    - Prepares and distributes extraction tasks dynamically based on results
    - Implements configurable failure modes for robust real-world operation.
    """

    def __init__(
        self,
        registry: Any | None = None,
        profiles: Sequence[AereoProfile | PipelineProfile] | None = None,
        grid_config: GridConfig | None = None,
        aoi: BaseGeometry | dict | None = None,
        backend: Any | None = None,
        cells_per_task: int | None = None,
    ):
        """
        Initializes the AereoClient with an optional AereoRegistry instance.

        Args:
            registry: Deprecated — kept for backward compatibility.
            profiles: Default profiles to use for search and extraction.
            grid_config: Default grid configuration for extraction.
            aoi: Default area of interest geometry.
            backend: Default execution backend.
            cells_per_task: Default number of grid cells per extraction task.
        """
        self._registry = registry  # kept for backward compatibility
        self._profiles = profiles
        self._grid_config = grid_config
        self._aoi = normalize_geometry(aoi)
        self._backend = backend
        self._cells_per_task = cells_per_task
        self._driver = AereoDriver()

    def _resolve_aoi(self, intersects: Any | None) -> BaseGeometry | None:
        """Resolve an AOI geometry, falling back to the client default.

        Args:
            intersects: Explicit geometry (dict or BaseGeometry), or None.

        Returns:
            Normalized geometry, or the client's default AOI.
        """
        return normalize_geometry(intersects) if intersects is not None else self._aoi

    @staticmethod
    def _empty_asset_df() -> GeoDataFrame:
        """Return an empty validated AssetSchema GeoDataFrame."""
        return cast(GeoDataFrame, AssetSchema.empty())

    def _resolve_cells_per_task(self, cells_per_task: int | None) -> int:
        """Resolve the effective cells-per-task value.

        Args:
            cells_per_task: Explicit value, or None to fall back to defaults.

        Returns:
            Effective cells per task (argument > client default > 50).
        """
        if cells_per_task is not None:
            return cells_per_task
        if self._cells_per_task is not None:
            return self._cells_per_task
        return DEFAULT_CELLS_PER_TASK

    @staticmethod
    def _resolve_search_params(
        params: Mapping[str, Any] | None,
        profile: AereoProfile | PipelineProfile,
    ) -> dict[str, Any]:
        """Merge batch-level *params* with profile-level search_params.

        Collection-specific overrides in *params* are applied when the key
        matches a collection declared on *profile* (case-insensitive). All
        other collection keys are stripped so they do not leak across
        profiles.

        Args:
            params: Raw parameter mapping.
            profile: Profile whose collections and search_params are used.

        Returns:
            Resolved parameter mapping with per-collection overrides applied.
        """
        if params is None:
            return dict(profile.search_params)

        profile_collections_lower = {c.lower() for c in profile.collections}
        resolved: dict[str, Any] = {}
        for k, v in params.items():
            if k.lower() not in profile_collections_lower:
                resolved[k] = v

        # Apply per-collection override for this profile
        for col in profile.collections:
            for k in params:
                if k.lower() == col.lower():
                    override = params[k]
                    if isinstance(override, Mapping):
                        resolved.update(override)
                    break

        # Profile-level params win
        resolved.update(profile.search_params)
        return resolved

    def search(
        self,
        profiles: Sequence[AereoProfile | PipelineProfile] | None = None,
        intersects: BaseGeometry | dict | None = None,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        search_params: Mapping[str, Any] | None = None,
        init_params: Mapping[str, Any] | None = None,
        failure_mode: FailureMode = FailureMode.BEST_EFFORT,
    ) -> GeoDataFrame[AssetSchema]:
        """Find data across massive sensor networks utilizing parallel Fan-Out search dispatch.

        Args:
            profiles: Sequence of AereoProfile objects defining what to search for.
                Each profile carries its collections, channels, satellite, and plugin hints.
                Falls back to client-level profiles if not provided.
            intersects: Optional geometry to spatially filter search results.
                Falls back to client-level aoi if not provided.
            start_datetime: Optional start datetime for temporal filtering.
            end_datetime: Optional end datetime for temporal filtering.
            search_params: Meta-level parameters to pass to search plugins
                (credentials, timeouts, etc.). Domain-specific config lives on each AereoProfile.
                Per-profile ``search_params`` overrides batch-level values (profile wins).
            init_params: Deprecated — kept for backward compatibility.
            failure_mode: Determines pipeline behavior when partial or total plugin failures occur. Defaults to BEST_EFFORT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.

        Returns:
            A verified GeoDataFrame of combined search results.
        """
        del init_params  # no longer used in the Hamilton-based architecture

        profiles = self._profiles if profiles is None else profiles
        if profiles is None:
            raise ValueError(
                "profiles must be provided either as a method argument or as a client default."
            )

        norm_intersects = self._resolve_aoi(intersects)
        logger.info("search_called", profiles=[p.name for p in profiles])

        all_results: list[GeoDataFrame] = []
        errors: list[Exception] = []

        def _search_one(profile: AereoProfile | PipelineProfile) -> GeoDataFrame:
            effective_params = self._resolve_search_params(search_params, profile)
            profile_for_driver = profile.model_copy(
                update={"search_params": effective_params}
            )
            return self._driver.search(
                cast(PipelineProfile, profile_for_driver),
                norm_intersects,
                start_datetime,
                end_datetime,
            )

        if len(profiles) == 1:
            try:
                all_results.append(_search_one(profiles[0]))
            except Exception as e:
                errors.append(e)
        else:
            with ThreadPoolExecutor(max_workers=max(1, len(profiles))) as executor:
                futures = {
                    executor.submit(_search_one, profile): profile
                    for profile in profiles
                }
                for future in as_completed(futures):
                    profile = futures[future]
                    try:
                        all_results.append(future.result())
                    except Exception as e:
                        logger.error(
                            "search_failed",
                            profile=profile.name,
                            exc_info=True,
                        )
                        errors.append(e)
                        if failure_mode == FailureMode.STRICT:
                            break

        if failure_mode == FailureMode.STRICT and errors:
            raise RuntimeError(
                f"Search failed strictly. {len(errors)} plugin(s) failed: "
                + "; ".join(f"{type(e).__name__}: {e}" for e in errors)
            )

        if not all_results:
            logger.warning(
                "search_empty",
                reason="All searches returned empty or failed gracefully.",
            )
            return self._empty_asset_df()

        return cast(
            GeoDataFrame,
            AssetSchema.validate(pd.concat(all_results, ignore_index=True)),
        )

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        grid_config: GridConfig | None = None,
        target_aoi: BaseGeometry | dict | None = None,
        resolution: float | None = None,
        uri: str | None = None,
        profiles: Sequence[AereoProfile | PipelineProfile] | None = None,
        cells_per_task: int | None = None,
        init_params: Mapping[str, Any] | None = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by collection and distributes batches to the Hamilton driver.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            grid_config: Explicit tiling specification. All profiles share this grid.
                Falls back to client-level grid_config if not provided.
            target_aoi: Optional area of interest as a shapely geometry.
                Falls back to client-level aoi if not provided.
            resolution: The desired resolution for extraction. If provided, a default profile is created.
            uri: An optional URI defining output path or identifier.
            profiles: A sequence of AereoProfile objects. If provided, they take precedence over resolution.
                Falls back to client-level profiles if not provided.
            cells_per_task: Max grid cells per ExtractionTask. Falls back to client default, then 50.
            init_params: Deprecated — kept for backward compatibility.

        Returns:
            A Sequence of prepared ExtractionTasks.
        """
        del init_params  # no longer used in the Hamilton-based architecture

        if search_results.empty:
            return []

        grid_config = self._grid_config if grid_config is None else grid_config
        if grid_config is None:
            raise ValueError(
                "grid_config must be provided either as a method argument or as a client default."
            )

        profiles = self._profiles if profiles is None else profiles

        norm_intersects = self._resolve_aoi(target_aoi)

        if profiles:
            resolved_profiles = list(profiles)
        elif resolution is not None:
            resolved_profiles = [AereoProfile(name="default", resolution=resolution)]
        else:
            raise ValueError(
                "Either 'profiles' or 'resolution' must be provided for extraction."
            )

        effective_cells_per_task = self._resolve_cells_per_task(cells_per_task)

        all_tasks: list[ExtractionTask] = []
        for profile in resolved_profiles:
            tasks = self._driver.prepare(
                search_results,
                cast(PipelineProfile, profile),
                grid_config,
                norm_intersects,
                uri=uri,
                cells_per_task=effective_cells_per_task,
            )
            all_tasks.extend(tasks)

        return all_tasks

    def execute_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        backend: ExecutionBackend | None = None,
        failure_mode: FailureMode = FailureMode.STRICT,
        init_params: Mapping[str, Any] | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Execute a sequence of ExtractionTasks through a configurable backend.

        The client delegates execution to the Hamilton driver via the backend,
        which controls parallelism, memory, and remote dispatch.

        Args:
            tasks: A sequence of ExtractionTasks, usually from prepare_for_extraction.
            backend: An ExecutionBackend implementation. Defaults to
                LocalProcessBackend() (sequential execution).
            failure_mode: STRICT raises on the first failure; BEST_EFFORT
                processes tasks individually and returns partial results,
                skipping only the tasks that fail.
            init_params: Deprecated — kept for backward compatibility.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        del init_params  # no longer used in the Hamilton-based architecture

        if not tasks:
            logger.warning("execute_tasks_empty", reason="No tasks provided")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        backend = self._backend if backend is None else backend
        backend = backend or LocalProcessBackend()
        runner = _DriverTaskRunner(self._driver)

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
                    task_results = list(
                        backend.run_tasks([task], cast(TaskRunner, runner))
                    )
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
            results = list(backend.run_tasks(tasks, cast(TaskRunner, runner)))
        except Exception:
            logger.error("execute_tasks_failed", exc_info=True)
            raise

        if not results:
            logger.warning("execute_tasks_empty_result")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        concatenated = pd.concat(results, ignore_index=True)
        return cast(GeoDataFrame, ArtifactSchema.validate(concatenated))
