from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, cast

import pandas as pd
import json
from aereo.execution.core import ExecutionBackend, LocalProcessBackend, TaskRunner
from aereo.interfaces import AereoProfile, ExtractionTask, GridConfig, merge_params
from aereo.registry import AereoRegistry
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()


class FailureMode(str, Enum):
    """Determines pipeline behavior when partial or total plugin failures occur."""

    STRICT = "strict"
    BEST_EFFORT = "best_effort"


def normalize_geometry(geom: Any) -> Optional[BaseGeometry]:
    """Ensures input geometries are Shapely objects before passing to Plugins."""
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

    def __init__(self, registry: Optional[AereoRegistry] = None):
        """
        Initializes the AereoClient with an optional AereoRegistry instance.
         - If no registry is provided, a default one is instantiated.

        Args:
            registry (Optional[AereoRegistry]): An instance of AereoRegistry to manage plugin discovery and instantiation.
                If None, a default AereoRegistry is created.
        """
        self.registry = registry or AereoRegistry()

    def _resolve_params(
        self, params: Optional[Mapping[str, Any]], collection: str
    ) -> Mapping[str, Any]:
        """Resolves parameters for a specific collection by merging global and per-collection overrides.

        All collection-name key lookups are case-insensitive: the user can write
        ``"Sentinel-2-L2A"``, ``"sentinel-2-l2a"``, or ``"SENTINEL-2-L2A"`` in
        ``params`` and the right override will always be applied.

        Algorithm:
          1. Build a lowercase-key index of ``params`` for case-insensitive matching.
          2. Start with non-collection-name params (global params).
          3. Merge the per-collection override block (if present) on top.
        """
        if params is None:
            return {}

        # canonical set of all known collection names (lowercase)
        all_known_collections_lower = {
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
    ) -> Optional[str]:
        """Resolves the appropriate plugin name for a profile.

        Resolution order:
          1. ``profile.plugin_hints.get(hint_key)`` where hint_key is
             ``"search"`` for searchers or ``"extract"`` for extractors.
          2. If absent, auto-discover from ``profile.collections`` using the registry.
          3. If hinted plugin is not registered → ``ValueError``.
          4. If auto-discovery returns nothing → ``None``.

        Args:
            plugin_type: "searcher" or "extractor".
            profile: The AereoProfile to resolve a plugin for.

        Returns:
            The resolved target plugin name, or None if no plugin is found.

        Raises:
            ValueError: If a hinted plugin is not registered.
        """
        hint_key = "search" if plugin_type == "searcher" else "extract"
        hint = profile.plugin_hints.get(hint_key)

        if plugin_type == "searcher":
            has_plugin = self.registry.has_searcher
            find_plugins = self.registry.find_searchers_for
        elif plugin_type == "extractor":
            has_plugin = self.registry.has_extractor
            find_plugins = self.registry.find_extractors_for
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

    def search(
        self,
        profiles: Sequence[AereoProfile],
        intersects: Optional[BaseGeometry | dict] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        failure_mode: FailureMode = FailureMode.BEST_EFFORT,
    ) -> GeoDataFrame[AssetSchema]:
        """Find data across massive sensor networks utilizing parallel Fan-Out search dispatch.

        Args:
            profiles (Sequence[AereoProfile]): Sequence of AereoProfile objects defining what to search for.
                Each profile carries its collections, channels, satellite, and plugin hints.
            intersects (Optional[BaseGeometry | dict]): Optional geometry to spatially filter search results.
            start_datetime (Optional[datetime]): Optional start datetime for temporal filtering.
            end_datetime (Optional[datetime]): Optional end datetime for temporal filtering.
            search_params (Optional[Mapping[str, Any]]): Meta-level parameters to pass to search plugins
                (credentials, timeouts, etc.). Domain-specific config lives on each AereoProfile.
                Per-profile ``search_params`` overrides batch-level values (profile wins).
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for plugin instantiation.
                Can be a flat dict (applied to every searcher) or use collection names as top-level keys
                for per-collection overrides, following the same pattern as ``search_params``::

                    # Global kwargs — applied to every searcher
                    init_params={"timeout": 30}

                    # Per-collection kwargs
                    init_params={"GOES-16": {"timeout": 60}, "Sentinel-2-L2A": {"timeout": 10}}

            failure_mode (FailureMode): Determines pipeline behavior when partial or total plugin failures occur. Defaults to BEST_EFFORT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.
        Returns:
            GeoDataFrame[AssetSchema]: A verified GeoDataFrame of combined search results.
        """

        norm_intersects = normalize_geometry(intersects)

        logger.info(
            "search_called",
            profiles=[p.name for p in profiles],
        )

        # 1. Resolution & Grouping Phase
        # We group by (target_plugin, resolved_search_params) to minimize redundant plugin calls
        # while ensuring each profile gets its targeted parameters.

        def get_params_key(p: Mapping[str, Any]) -> str:
            # Simple stable key for grouping; default=str handles non-JSON-serializable objects
            return json.dumps(p, sort_keys=True, default=str)

        # Map (plugin_name, params_key) -> (list_of_profiles, resolved_params_dict)
        execution_groups: dict[
            tuple[str, str], tuple[list[AereoProfile], Mapping[str, Any]]
        ] = {}

        for profile in profiles:
            target_plugin = self._resolve_plugin_for_profile("searcher", profile)
            if not target_plugin:
                logger.warning(
                    "search_skipped_no_plugin",
                    profile=profile.name,
                    collections=profile.collections,
                )
                continue

            # Resolve targeted parameters using the first collection for per-collection overrides
            first_collection = (
                next(iter(profile.collections)) if profile.collections else ""
            )
            batch_resolved = self._resolve_params(search_params, first_collection)
            c_params = merge_params(batch_resolved, profile.search_params)
            p_key = get_params_key(c_params)

            group_key = (target_plugin, p_key)
            if group_key not in execution_groups:
                execution_groups[group_key] = ([profile], c_params)
            else:
                execution_groups[group_key][0].append(profile)

        all_results = []
        errors = []

        if not execution_groups:
            if failure_mode == FailureMode.STRICT:
                raise RuntimeError(
                    "No eligible search plugins found for the requested profiles."
                )
            return cast(GeoDataFrame, AssetSchema.empty())

        # 2. Parallel fan-out dispatch to remote plugin APIs
        with ThreadPoolExecutor(max_workers=max(1, len(execution_groups))) as executor:
            futures = {
                executor.submit(
                    self.registry.get_searcher(
                        p_name,
                        **self._resolve_params(
                            init_params,
                            next(iter(s_profiles[0].collections))
                            if s_profiles and s_profiles[0].collections
                            else "",
                        ),
                    ).search,
                    profiles=s_profiles,
                    intersects=norm_intersects,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    search_params=s_params,
                ): (p_name, s_profiles)
                for (p_name, _), (s_profiles, s_params) in execution_groups.items()
            }

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

        # 3. Handle Resilience & Failure Profiles
        if not all_results:
            if failure_mode == FailureMode.STRICT and errors:
                raise RuntimeError(
                    f"All search plugins failed strictly. {len(errors)} errors."
                )

            logger.warning(
                "search_empty",
                reason="All searches returned empty or failed gracefully.",
            )
            return cast(GeoDataFrame, AssetSchema.empty())

        # 4. Collapse results safely
        merged_results = cast(
            GeoDataFrame,
            AssetSchema.validate(pd.concat(all_results, ignore_index=True)),
        )
        return merged_results

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        grid_config: GridConfig,
        target_aoi: Optional[BaseGeometry | dict] = None,
        resolution: Optional[float] = None,
        uri: Optional[str] = None,
        profiles: Optional[Sequence[AereoProfile]] = None,
        cells_per_chunk: int = 50,
        init_params: Optional[Mapping[str, Any]] = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by collection and distributes batches to appropriate Extractors.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            grid_config: Explicit tiling specification. All profiles share this grid.
            target_aoi: Optional area of interest as a shapely geometry.
            resolution: The desired resolution for extraction. If provided, a default profile is created.
            uri: An optional URI defining output path or identifier.
            profiles: A sequence of AereoProfile objects. If provided, they take precedence over resolution.
            cells_per_chunk: Max grid cells per ExtractionTask (default 50).
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for extractor instantiation.
                Passed as a flat dict to the extractor constructor.

        Returns:
            A Sequence of prepared ExtractionTasks.
        """
        if search_results.empty:
            return []

        norm_intersects = normalize_geometry(target_aoi)
        all_tasks = []

        unique_collections = search_results["collection"].unique()

        # Determine profiles for extraction
        if profiles:
            resolved_profiles = list(profiles)
        elif resolution is not None:
            resolved_profiles = [AereoProfile(name="default", resolution=resolution)]
        else:
            raise ValueError(
                "Either 'profiles' or 'resolution' must be provided for extraction."
            )

        # Resolve extractor for all profiles
        plugin_set = set()
        for profile in resolved_profiles:
            target_plugin = self._resolve_plugin_for_profile("extractor", profile)
            if not target_plugin:
                # Fallback to search result collections for default/empty profiles
                for collection in unique_collections:
                    fallback_profile = AereoProfile(
                        name="fallback", resolution=0, collections={str(collection): []}
                    )
                    target_plugin = self._resolve_plugin_for_profile(
                        "extractor", fallback_profile
                    )
                    if target_plugin:
                        break
            if not target_plugin:
                raise ValueError(
                    f"No Extractor plugin found for profile: {profile.name}"
                )
            plugin_set.add(target_plugin)

        if len(plugin_set) > 1:
            raise ValueError(
                f"Multiple extractor plugins found for profiles: {[p.name for p in resolved_profiles]}. "
                "Ensure all profiles use the same extractor."
            )

        target_plugin = plugin_set.pop()
        first_collection = (
            next(iter(resolved_profiles[0].collections))
            if resolved_profiles and resolved_profiles[0].collections
            else ""
        )

        # Resolve init params and instantiate extractor
        c_init = self._resolve_params(init_params, first_collection)
        extractor = self.registry.get_extractor(target_plugin, **c_init)

        logger.debug(
            "prepare_batches_start",
            plugin=target_plugin,
            profiles=[p.name for p in resolved_profiles],
        )

        # Pass full search results to extractor (profile filtering happens there)
        batches = extractor.prepare_for_extraction(
            cast(GeoDataFrame, search_results),
            grid_config=grid_config,
            target_aoi=norm_intersects,
            uri=uri,
            profiles=resolved_profiles,
            cells_per_chunk=cells_per_chunk,
            extractor_hint=target_plugin,
        )

        all_tasks.extend(batches)

        return all_tasks

    def execute_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        backend: ExecutionBackend | None = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Execute a sequence of ExtractionTasks through a configurable backend.

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

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        if not tasks:
            logger.warning("execute_tasks_empty", reason="No tasks provided")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        backend = backend or LocalProcessBackend()
        runner = TaskRunner(registry=self.registry)

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
