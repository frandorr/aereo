"""Core client implementation for the Aereo geospatial pipeline.

This module defines :class:`AereoClient` and its supporting utilities,
including geometry normalisation, parameter resolution, and parallel
search / extraction orchestration.
"""

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
import json
from typing import Any, cast

import pandas as pd
from aereo.backends import LocalProcessBackend, TaskRunner
from aereo.interfaces import (
    AereoProfile,
    ExecutionBackend,
    ExtractionTask,
    GridConfig,
    merge_params,
)
from aereo.registry import AereoRegistry
from aereo.schemas import ArtifactSchema, AssetSchema
from aereo.task_builder import prepare_for_extraction
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()

DEFAULT_CELLS_PER_TASK = 50


def _json_default(obj: Any) -> Any:
    """Custom JSON encoder that recursively stringifies non-string dict keys."""
    if isinstance(obj, dict):
        return {str(k): _json_default(v) for k, v in obj.items()}
    return str(obj)


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


class AereoClient:
    """Core external entrypoint orchestrating the Geospatial pipeline.

    Responsibilities:
    - Accepts user queries and parameters
    - Maps profiles to registered plugins with optional profile-level hints
    - Executes parallel fan-out search dispatch to remote plugin APIs
    - Collapses and validates results into a unified DataFrame
    - Prepares and distributes extraction tasks dynamically based on results
    - Implements configurable failure modes for robust real-world operation.
    """

    def __init__(
        self,
        registry: AereoRegistry | None = None,
        profiles: Sequence[AereoProfile] | None = None,
        grid_config: GridConfig | None = None,
        aoi: BaseGeometry | dict | None = None,
        backend: ExecutionBackend | None = None,
        cells_per_task: int | None = None,
    ):
        """Initialize the AereoClient with an optional AereoRegistry instance.

        If no registry is provided, a default one is instantiated.

        Args:
            registry: An instance of AereoRegistry to manage plugin discovery
                and instantiation. If None, a default AereoRegistry is created.
            profiles: Default profiles to use for search and extraction.
            grid_config: Default grid configuration for extraction.
            aoi: Default area of interest geometry.
            backend: Default execution backend.
            cells_per_task: Default number of grid cells per extraction task.
        """
        self.registry = registry or AereoRegistry()
        self._profiles = profiles
        self._grid_config = grid_config
        self._aoi = normalize_geometry(aoi)
        self._backend = backend
        self._cells_per_task = cells_per_task

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

    @staticmethod
    def _empty_artifact_df() -> GeoDataFrame:
        """Return an empty validated ArtifactSchema GeoDataFrame."""
        return cast(GeoDataFrame, ArtifactSchema.empty())

    @staticmethod
    def _first_collection(profile: AereoProfile) -> str:
        """Return the first collection name from a profile, or empty string."""
        return next(iter(profile.collections)) if profile.collections else ""

    @staticmethod
    def _concat_and_validate(dfs: Sequence[GeoDataFrame], schema: Any) -> GeoDataFrame:
        """Concatenate a list of GeoDataFrames and validate against a schema.

        Args:
            dfs: Sequence of GeoDataFrames to concatenate.
            schema: Pandera schema class with a ``validate`` method.

        Returns:
            A validated GeoDataFrame.
        """
        concatenated = pd.concat(dfs, ignore_index=True)
        return cast(GeoDataFrame, schema.validate(concatenated))

    def _resolve_params(
        self,
        params: Mapping[str, Any] | None,
        collection: str,
        _known_collections_lower: set[str] | None = None,
    ) -> Mapping[str, Any]:
        """Resolves parameters for a specific collection by merging global and per-collection overrides.

        All collection-name key lookups are case-insensitive: the user can write
        ``"Sentinel-2-L2A"``, ``"sentinel-2-l2a"``, or ``"SENTINEL-2-L2A"`` in
        ``params`` and the right override will always be applied.

        Algorithm:
          1. Build a lowercase-key index of ``params`` for case-insensitive matching.
          2. Start with non-collection-name params (global params).
          3. Merge the per-collection override block (if present) on top.

        Args:
            params: Raw parameter mapping.
            collection: Target collection name.
            _known_collections_lower: Optional pre-computed set of lowercase known
                collection names to avoid repeated registry queries.

        Returns:
            Resolved parameter mapping with per-collection overrides applied.
        """
        if params is None:
            return {}

        # canonical set of all known collection names (lowercase)
        all_known_collections_lower = _known_collections_lower or {
            c.lower() for c in self.registry.list_supported_collections()
        }

        # 1. Build a lowercase-key lookup for the incoming params dict so we can
        #    do case-insensitive matching without mutating the caller's data.
        params_lower: dict[
            str, tuple[str, Any]
        ] = {}  # lower_key -> (original_key, value)
        for k, v in params.items():
            params_lower[k.lower()] = (k, v)

        collection_lower = collection.lower()

        # 2. Start with all global (non-collection) params.
        #    A key is considered a "collection key" if its lowercase form appears
        #    in the known collections set.
        resolved: dict[str, Any] = {
            orig_key: value
            for lower_key, (orig_key, value) in params_lower.items()
            if lower_key not in all_known_collections_lower
        }

        # 3. Merge the per-collection override block on top (if present).
        if collection_lower in params_lower:
            override = params_lower[collection_lower][1]
            if isinstance(override, Mapping):
                resolved.update(override)

        return resolved

    def _resolve_plugin_for_profile(
        self, plugin_type: str, profile: AereoProfile
    ) -> str | None:
        """Resolves the appropriate plugin name for a profile.

        Resolution order:
          1. ``profile.plugin_hints.get(hint_key)`` where hint_key is
             ``"search"`` for searchers.
          2. If absent, auto-discover from ``profile.collections`` using the registry.
          3. If hinted plugin is not registered → ``ValueError``.
          4. If auto-discovery returns nothing → ``None``.

        Args:
            plugin_type: "searcher".
            profile: The AereoProfile to resolve a plugin for.

        Returns:
            The resolved target plugin name, or None if no plugin is found.

        Raises:
            ValueError: If a hinted plugin is not registered.
        """
        hint_key = "search"
        hint = profile.plugin_hints.get(hint_key)

        if plugin_type == "searcher":
            has_plugin = self.registry.has_searcher
            find_plugins = self.registry.find_searchers_for
        else:
            raise ValueError(f"Unknown plugin type: {plugin_type}")

        if hint:
            target_plugin = hint
            if not has_plugin(target_plugin):
                raise ValueError(
                    f"Hinted plugin '{target_plugin}' is not a registered {plugin_type.capitalize()}."
                )
            return target_plugin

        # Auto-discover from collections
        for collection in profile.collections:
            plugin_names = find_plugins(collection)
            if plugin_names:
                return plugin_names[0]
        return None

    def _build_search_execution_groups(
        self,
        profiles: Sequence[AereoProfile],
        search_params: Mapping[str, Any] | None,
    ) -> dict[tuple[str, str], tuple[list[AereoProfile], Mapping[str, Any]]]:
        """Group profiles by (target_plugin, resolved_params) to minimize redundant calls.

        Args:
            profiles: Sequence of profiles to search for.
            search_params: Raw search parameters.

        Returns:
            Mapping from (plugin_name, params_key) to (profile_list, resolved_params).
        """
        execution_groups: dict[
            tuple[str, str], tuple[list[AereoProfile], Mapping[str, Any]]
        ] = {}

        known_collections_lower = {
            c.lower() for c in self.registry.list_supported_collections()
        }

        for profile in profiles:
            target_plugin = self._resolve_plugin_for_profile("searcher", profile)
            if not target_plugin:
                logger.warning(
                    "search_skipped_no_plugin",
                    profile=profile.name,
                    collections=profile.collections,
                )
                continue

            first_collection = self._first_collection(profile)
            batch_resolved = self._resolve_params(
                search_params,
                first_collection,
                _known_collections_lower=known_collections_lower,
            )
            c_params = merge_params(batch_resolved, profile.search_params)
            p_key = json.dumps(c_params, sort_keys=True, default=_json_default)

            group_key = (target_plugin, p_key)
            if group_key not in execution_groups:
                execution_groups[group_key] = ([profile], c_params)
            else:
                execution_groups[group_key][0].append(profile)

        return execution_groups

    def _execute_search_groups(
        self,
        execution_groups: dict[
            tuple[str, str], tuple[list[AereoProfile], Mapping[str, Any]]
        ],
        norm_intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        init_params: Mapping[str, Any] | None,
    ) -> tuple[list[GeoDataFrame], list[Exception]]:
        """Dispatch search calls in parallel and collect results.

        Args:
            execution_groups: Grouped profiles and parameters.
            norm_intersects: Normalized AOI geometry.
            start_datetime: Optional start filter.
            end_datetime: Optional end filter.
            init_params: Optional plugin init params.

        Returns:
            Tuple of (list_of_result_dataframes, list_of_exceptions).
        """
        all_results: list[GeoDataFrame] = []
        errors: list[Exception] = []

        with ThreadPoolExecutor(max_workers=max(1, len(execution_groups))) as executor:
            futures: dict[Any, tuple[str, list[AereoProfile]]] = {}
            for (p_name, _), (s_profiles, s_params) in execution_groups.items():
                first_collection = self._first_collection(s_profiles[0])
                searcher = self.registry.get_searcher(
                    p_name,
                    **self._resolve_params(init_params, first_collection),
                )
                future = executor.submit(
                    searcher.search,
                    profiles=s_profiles,
                    intersects=norm_intersects,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    search_params=s_params,
                )
                futures[future] = (p_name, s_profiles)

            for future in as_completed(futures):
                plugin_name, profs = futures[future]
                try:
                    df = future.result()
                    logger.debug(
                        "search_completed",
                        plugin=plugin_name,
                        profiles=[p.name for p in profs],
                        count=len(df),
                    )
                    all_results.append(df)
                except Exception as e:
                    logger.error(
                        "search_failed",
                        plugin=plugin_name,
                        profiles=[p.name for p in profs],
                        exc_info=True,
                    )
                    errors.append(e)

        return all_results, errors

    def search(
        self,
        profiles: Sequence[AereoProfile] | None = None,
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
            init_params: Optional constructor kwargs for plugin instantiation.
                Can be a flat dict (applied to every searcher) or use collection names as top-level keys
                for per-collection overrides, following the same pattern as ``search_params``::

                    # Global kwargs — applied to every searcher
                    init_params={"timeout": 30}

                    # Per-collection kwargs
                    init_params={"GOES-16": {"timeout": 60}, "Sentinel-2-L2A": {"timeout": 10}}

            failure_mode: Determines pipeline behavior when partial or total plugin failures occur. Defaults to BEST_EFFORT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.

        Returns:
            A verified GeoDataFrame of combined search results.
        """
        profiles = self._profiles if profiles is None else profiles
        if profiles is None:
            raise ValueError(
                "profiles must be provided either as a method argument or as a client default."
            )

        norm_intersects = self._resolve_aoi(intersects)
        logger.info("search_called", profiles=[p.name for p in profiles])

        execution_groups = self._build_search_execution_groups(profiles, search_params)
        if not execution_groups:
            if failure_mode == FailureMode.STRICT:
                raise RuntimeError(
                    "No eligible search plugins found for the requested profiles."
                )
            return self._empty_asset_df()

        all_results, errors = self._execute_search_groups(
            execution_groups,
            norm_intersects,
            start_datetime,
            end_datetime,
            init_params,
        )

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

        return self._concat_and_validate(all_results, AssetSchema)

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

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        grid_config: GridConfig | None = None,
        target_aoi: BaseGeometry | dict | None = None,
        resolution: float | None = None,
        uri: str | None = None,
        profiles: Sequence[AereoProfile] | None = None,
        cells_per_task: int | None = None,
        init_params: Mapping[str, Any] | None = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by collection and distributes batches into tasks.

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
            init_params: Optional parameters added to each task's context.

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

        tasks = prepare_for_extraction(
            search_results=cast(GeoDataFrame, search_results),
            grid_config=grid_config,
            profiles=resolved_profiles,
            uri=uri or "",
            target_aoi=norm_intersects,
            cells_per_task=effective_cells_per_task,
            init_params=dict(init_params) if init_params else None,
        )

        return list(tasks)

    def execute_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        backend: ExecutionBackend | None = None,
        failure_mode: FailureMode = FailureMode.STRICT,
        init_params: Mapping[str, Any] | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Execute a sequence of ExtractionTasks through a configurable backend.

        The client resolves the correct plugin for each task and delegates
        execution to the backend, which controls parallelism, memory, and
        remote dispatch.

        Args:
            tasks: A sequence of ExtractionTasks, usually from prepare_for_extraction.
            backend: An ExecutionBackend implementation. Defaults to
                LocalProcessBackend() (sequential execution).
            failure_mode: STRICT raises on the first failure; BEST_EFFORT
                processes tasks individually and returns partial results,
                skipping only the tasks that fail.
            init_params: Optional parameters forwarded to plugin instantiation
                for each task.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        if not tasks:
            logger.warning("execute_tasks_empty", reason="No tasks provided")
            return self._empty_artifact_df()

        backend = self._backend if backend is None else backend
        backend = backend or LocalProcessBackend()
        runner = TaskRunner(registry=self.registry, init_params=init_params)

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
                return self._empty_artifact_df()
            return self._concat_and_validate(results, ArtifactSchema)

        # STRICT mode — batch for efficiency, raise on first failure
        try:
            results = list(backend.run_tasks(tasks, runner))
        except Exception:
            logger.error("execute_tasks_failed", exc_info=True)
            raise

        if not results:
            logger.warning("execute_tasks_empty_result")
            return self._empty_artifact_df()

        return self._concat_and_validate(results, ArtifactSchema)
