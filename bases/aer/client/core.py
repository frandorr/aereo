from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, cast

import pandas as pd
import json
from aer.interfaces import ExtractionProfile, ExtractionTask
from aer.registry import AerRegistry
from aer.schemas import ArtifactSchema, AssetSchema
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


class AerClient:
    """Core external entrypoint orchestrating the Geospatial pipeline.

    Responsibilities:
    - Accepts user queries and parameters
    - Maps collections to registered plugins with optional user hints
    - Executes parallel fan-out search dispatch to remote plugin APIs
    - Collapses and validates results into a unified DataFrame
    - Prepares and distributes extraction tasks dynamically based on results
    - Implements configurable failure modes for robust real-world operation.
    """

    def __init__(self, registry: Optional[AerRegistry] = None):
        """
        Initializes the AerClient with an optional AerRegistry instance.
         - If no registry is provided, a default one is instantiated.

        Args:
            registry (Optional[AerRegistry]): An instance of AerRegistry to manage plugin discovery and instantiation.
                If None, a default AerRegistry is created.
        """
        self.registry = registry or AerRegistry()

    @staticmethod
    def _normalize_hints(hints: Mapping[str, str | Sequence[str]]) -> Mapping[str, str]:
        """Normalize plugin hints to a collection→plugin mapping with lower-cased keys.

        Supports two input shapes:

        * **Collection → plugin** (legacy)::
            ``{"Sentinel-2-L2A": "my_plugin", "ABI-L1b-RadF": "goes_plugin"}``
        * **Plugin → collections** (inverted)::
            ``{"extract_satpy": ["VJ202IMG", "VJ203IMG"]}``

        Both are normalized to ``{collection.lower(): plugin}`` so that downstream
        lookups are case-insensitive.
        """
        normalized: dict[str, str] = {}
        for key, value in hints.items():
            if isinstance(value, str):
                # Legacy format: collection -> plugin
                normalized[key.lower()] = value
            else:
                # Inverted format: plugin -> [collections, ...]
                for collection in value:
                    normalized[str(collection).lower()] = key
        return normalized

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

    def _resolve_plugin_for_collection(
        self, plugin_type: str, collection: str, plugin_hints: Mapping[str, str]
    ) -> Optional[str]:
        """Resolves the appropriate plugin name for a collection, factoring in user hints.

        Args:
            plugin_type: "searcher" or "extractor".
            collection: The collection name.
            plugin_hints: Normalized mapping of collection to preferred plugin name.

        Returns:
            The resolved target plugin name, or None if no plugin is found.

        Raises:
            ValueError: If a hinted plugin is not registered.
        """
        hint = plugin_hints.get(collection.lower())

        if plugin_type == "searcher":
            has_plugin = self.registry.has_searcher
            get_collections = self.registry.get_searcher_collections
            find_plugins = self.registry.find_searchers_for
        elif plugin_type == "extractor":
            has_plugin = self.registry.has_extractor
            get_collections = self.registry.get_extractor_collections
            find_plugins = self.registry.find_extractors_for
        else:
            raise ValueError(f"Unknown plugin type: {plugin_type}")

        if hint:
            target_plugin = hint
            if not has_plugin(target_plugin):
                raise ValueError(
                    f"Hinted plugin '{target_plugin}' is not a registered {plugin_type.capitalize()}."
                )

            supported = get_collections(target_plugin)
            if len(supported) > 0 and collection.lower() not in [
                s.lower() for s in supported
            ]:
                logger.warning(
                    f"Hinted {plugin_type} plugin '{target_plugin}' supports collections {supported}, but '{collection}' is not among them."
                )
            elif len(supported) == 0:
                logger.warning(
                    f"Hinted {plugin_type} plugin '{target_plugin}' declares no supported collections. Proceeding anyway for '{collection}'."
                )
            return target_plugin
        else:
            plugin_names = find_plugins(collection)
            if not plugin_names:
                return None
            return plugin_names[0]

    def search(
        self,
        collections: Sequence[str],
        intersects: Optional[BaseGeometry | dict] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[Mapping[str, str | Sequence[str]]] = None,
        failure_mode: FailureMode = FailureMode.BEST_EFFORT,
    ) -> GeoDataFrame[AssetSchema]:
        """Find data across massive sensor networks utilizing parallel Fan-Out search dispatch.

        Args:
            collections (Sequence[str]): List of collection identifiers to search across.
            intersects (Optional[BaseGeometry | dict]): Optional geometry to spatially filter search results.
            start_datetime (Optional[datetime]): Optional start datetime for temporal filtering.
            end_datetime (Optional[datetime]): Optional end datetime for temporal filtering.
            search_params (Optional[Mapping[str, Any]]): Additional parameters to pass to search plugins.
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for plugin instantiation.
                Can be a flat dict (applied to every searcher) or use collection names as top-level keys
                for per-collection overrides, following the same pattern as ``search_params``::

                    # Global kwargs — applied to every searcher
                    init_params={"timeout": 30}

                    # Per-collection kwargs
                    init_params={"GOES-16": {"timeout": 60}, "Sentinel-2-L2A": {"timeout": 10}}

            plugin_hints (Optional[dict[str, str | Sequence[str]]]): Optional mapping specifying preferred plugins.
                    Supports two formats:
                    * Collection → plugin: ``{"MODIS": "my_searcher"}``
                    * Plugin → collections (inverted): ``{"my_searcher": ["MODIS", "VIIRS"]}``
                    If not provided, the first registered plugin will be used.
            failure_mode (FailureMode): Determines pipeline behavior when partial or total plugin failures occur. Defaults to BEST_EFFORT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.
        Returns:
            GeoDataFrame[AssetSchema]: A verified GeoDataFrame of combined search results.
        """

        plugin_hints = self._normalize_hints(plugin_hints or {})
        norm_intersects = normalize_geometry(intersects)

        logger.info(
            "search_called",
            collections=collections,
            plugin_hints=plugin_hints,
        )

        # 1. Resolution & Grouping Phase
        # We group by (target_plugin, resolved_search_params) to minimize redundant plugin calls
        # while ensuring each collection gets its targeted parameters.

        def get_params_key(p: Mapping[str, Any]) -> str:
            # Simple stable key for grouping; default=str handles non-JSON-serializable objects
            return json.dumps(p, sort_keys=True, default=str)

        # Map (plugin_name, params_key) -> (list_of_collections, resolved_params_dict)
        execution_groups: dict[
            tuple[str, str], tuple[list[str], Mapping[str, Any]]
        ] = {}

        for collection in collections:
            target_plugin = self._resolve_plugin_for_collection(
                "searcher", collection, plugin_hints
            )
            if not target_plugin:
                logger.warning(
                    "search_skipped_no_plugin",
                    collection=collection,
                )
                continue

            # Resolve targeted parameters for this specific collection
            c_params = self._resolve_params(search_params, collection)
            p_key = get_params_key(c_params)

            group_key = (target_plugin, p_key)
            if group_key not in execution_groups:
                # First time we see this plugin+params combo, fetch canonical names
                mapped_cols = self.registry.get_collection_mapping_for_searcher(
                    target_plugin, [collection]
                )
                execution_groups[group_key] = (mapped_cols, c_params)
            else:
                # Add to existing group
                mapped_cols = self.registry.get_collection_mapping_for_searcher(
                    target_plugin, [collection]
                )
                execution_groups[group_key][0].extend(mapped_cols)

        all_results = []
        errors = []

        if not execution_groups:
            if failure_mode == FailureMode.STRICT:
                raise RuntimeError(
                    "No eligible search plugins found for the requested collections."
                )
            return cast(GeoDataFrame, AssetSchema.empty())

        # 2. Parallel fan-out dispatch to remote plugin APIs
        with ThreadPoolExecutor(max_workers=max(1, len(execution_groups))) as executor:
            futures = {
                executor.submit(
                    self.registry.get_searcher(
                        p_name,
                        **self._resolve_params(
                            init_params, s_cols[0] if s_cols else ""
                        ),
                    ).search,
                    collections=s_cols,
                    intersects=norm_intersects,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    search_params=s_params,
                ): (p_name, s_cols)
                for (p_name, _), (s_cols, s_params) in execution_groups.items()
            }

            for future in as_completed(futures):
                plugin_name, cols = futures[future]
                try:
                    df = future.result()
                    logger.debug(
                        "search_completed",
                        plugin=plugin_name,
                        collections=cols,
                        count=len(df),
                    )
                    all_results.append(df)
                except Exception as e:
                    logger.error(
                        "search_failed",
                        plugin=plugin_name,
                        collections=cols,
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
        target_aoi: Optional[BaseGeometry | dict] = None,
        resolution: Optional[float] = None,
        uri: Optional[str] = None,
        profiles: Optional[Sequence[ExtractionProfile]] = None,
        prepare_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[Mapping[str, str | Sequence[str]]] = None,
        target_grid_dist: Optional[int] = None,
        target_grid_overlap: Optional[bool] = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by collection and distributes batches to appropriate Extractors.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            target_aoi: Optional area of interest as a shapely geometry.
            resolution: The desired resolution for extraction. If provided, a default profile is created.
            uri: An optional URI defining output path or identifier.
            profiles: A sequence of ExtractionProfile objects. If provided, they take precedence over resolution.
            prepare_params: Additional parameters to pass to prepare_for_extraction method.
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for extractor instantiation.
                Supports global and per-collection overrides, matching the ``prepare_params`` pattern::

                    # Override target_grid_d for a specific collection
                    init_params={"ABI-L1b-RadC": {"target_grid_d": 50_000}}

                    # Or globally for all extractors
                    init_params={"target_grid_d": 50_000}

            plugin_hints (Optional[dict[str, str | Sequence[str]]]): Optional mapping specifying preferred plugins.
                Supports two formats:
                * Collection → plugin: ``{"MODIS": "my_extractor"}``
                * Plugin → collections (inverted): ``{"my_extractor": ["MODIS", "VIIRS"]}``
            target_grid_dist (Optional[int]): Override the extractor's default grid cell size in meters
                (e.g. ``100_000`` for 100 km cells).  When ``None``, the extractor's ``target_grid_d``
                property is used.
            target_grid_overlap (Optional[bool]): Override the extractor's default grid overlap setting.
                When ``None``, the extractor's ``target_grid_overlap`` property is used.

        Returns:
            A Sequence of prepared ExtractionTasks.
        """
        if search_results.empty:
            return []

        plugin_hints = self._normalize_hints(plugin_hints or {})
        norm_intersects = normalize_geometry(target_aoi)
        all_tasks = []

        # Resolve extractor for all collections (assumes single extractor for all collections in profiles)
        unique_collections = search_results["collection"].unique()
        plugin_set = set()
        for collection in unique_collections:
            collection_str = str(collection)
            target_plugin = self._resolve_plugin_for_collection(
                "extractor", collection_str, plugin_hints
            )
            if not target_plugin:
                raise ValueError(
                    f"No Extractor plugin found for collection: {collection_str}"
                )
            plugin_set.add(target_plugin)

        if len(plugin_set) > 1:
            raise ValueError(
                f"Multiple extractor plugins found for collections: {list(unique_collections)}. "
                "Ensure all collections use the same extractor or use per-collection profiles."
            )

        target_plugin = plugin_set.pop()
        first_collection = (
            str(unique_collections[0]) if len(unique_collections) > 0 else ""
        )

        # Resolve init and prepare params
        c_init = self._resolve_params(init_params, first_collection)
        extractor = self.registry.get_extractor(target_plugin, **c_init)
        c_params = self._resolve_params(prepare_params, first_collection)

        logger.debug(
            "prepare_batches_start",
            plugin=target_plugin,
            collections=list(unique_collections),
        )

        # Determine profiles for extraction
        if profiles:
            resolved_profiles = list(profiles)
        elif resolution is not None:
            resolved_profiles = [
                ExtractionProfile(name="default", resolution=resolution)
            ]
        else:
            raise ValueError(
                "Either 'profiles' or 'resolution' must be provided for extraction."
            )

        # Pass full search results to extractor (profile filtering happens there)
        batches = extractor.prepare_for_extraction(
            cast(GeoDataFrame, search_results),
            target_aoi=norm_intersects,
            target_grid_dist=target_grid_dist,
            target_grid_overlap=target_grid_overlap,
            uri=uri,
            profiles=resolved_profiles,
            prepare_params=c_params,
        )

        all_tasks.extend(batches)

        return all_tasks

    def extract_batches(
        self,
        extraction_task_batch: Sequence[ExtractionTask],
        extract_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[Mapping[str, str | Sequence[str]]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
        max_batch_workers: Optional[int] = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Executes the extraction phase by delegating all ExtractionTasks to the appropriate Extractor plugin.

        Args:
            extraction_task_batch: A sequence of ExtractionTasks, usually from prepare_for_extraction.
            extract_params: Additional parameters to pass to the Extractor.
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for extractor instantiation.
                Supports global and per-collection overrides, matching the ``extract_params`` pattern::

                    # Override target_grid_d globally
                    init_params={"target_grid_d": 50_000}

                    # Or per-collection
                    init_params={"ABI-L1b-RadC": {"target_grid_d": 50_000, "target_grid_overlap": True}}

            plugin_hints (Optional[dict[str, str | Sequence[str]]]): Optional mapping specifying preferred plugins.
                Supports two formats:
                * Collection → plugin: ``{"MODIS": "my_extractor"}``
                * Plugin → collections (inverted): ``{"my_extractor": ["MODIS", "VIIRS"]}``
            failure_mode: STRICT raises errors; BEST_EFFORT continues with successful plugins.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        all_artifacts = []
        errors = []
        plugin_hints = self._normalize_hints(plugin_hints or {})

        if not extraction_task_batch:
            logger.warning("extract_empty_result", reason="No tasks provided")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        # Collect all unique collections from tasks
        unique_collections: set[str] = set()
        for task in extraction_task_batch:
            if not task.assets.empty:
                unique_collections.add(str(task.assets["collection"].iloc[0]))

        if not unique_collections:
            logger.warning(
                "extract_empty_result", reason="No collections found in tasks"
            )
            return cast(GeoDataFrame, ArtifactSchema.empty())

        # Resolve extractor plugin for all collections, ensure consistency
        plugin_set: set[str] = set()
        for collection in unique_collections:
            target_plugin = self._resolve_plugin_for_collection(
                "extractor", collection, plugin_hints
            )
            if not target_plugin:
                raise RuntimeError(f"No plugin found for collection: {collection}")
            plugin_set.add(target_plugin)

        if len(plugin_set) > 1:
            raise ValueError(
                f"Multiple extractor plugins found for collections: {list(unique_collections)}. "
                "Ensure all collections use the same extractor."
            )

        target_plugin = plugin_set.pop()
        first_collection = next(iter(unique_collections))

        # Resolve init params and instantiate extractor
        c_init = self._resolve_params(init_params, first_collection)
        extractor = self.registry.get_extractor(target_plugin, **c_init)

        # Resolve extract params
        c_params = self._resolve_params(extract_params, first_collection)

        logger.info(
            "extract_batches_start",
            plugin=target_plugin,
            batch_count=len(extraction_task_batch),
            collections=list(unique_collections),
        )

        try:
            df = extractor.extract_batches(
                extraction_task_batch,
                extract_params=c_params,
                max_batch_workers=max_batch_workers,
            )
            all_artifacts.append(df)
        except Exception as e:
            logger.error(
                "extract_failed",
                plugin=target_plugin,
                collections=list(unique_collections),
                exc_info=True,
            )
            errors.append(e)

        if not all_artifacts:
            if failure_mode == FailureMode.STRICT and errors:
                raise RuntimeError(
                    f"Extraction failed strictly. {len(errors)} errors captured."
                )
            logger.warning("extract_empty_result", reason="No artifacts retrieved")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        final_df = pd.concat(all_artifacts, ignore_index=True)
        return cast(GeoDataFrame, ArtifactSchema.validate(final_df))

    def run_pipeline(
        self,
        collections: Sequence[str],
        intersects: Optional[BaseGeometry | dict] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
        resolution: Optional[float] = None,
        uri: Optional[str] = None,
        prepare_params: Optional[Mapping[str, Any]] = None,
        extract_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[Mapping[str, str | Sequence[str]]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
        max_batch_workers: Optional[int] = None,
        profiles: Optional[Sequence[ExtractionProfile]] = None,
        target_grid_dist: Optional[int] = None,
        target_grid_overlap: Optional[bool] = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Convenience "God Method" running the entire data lifecycle sequentially.

        Args:
            collections (Sequence[str]): List of collection identifiers to search across.
            intersects (Optional[BaseGeometry | dict]): Optional geometry for spatial filtering.
            start_datetime (Optional[datetime]): Optional start datetime for temporal filtering.
            end_datetime (Optional[datetime]): Optional end datetime for temporal filtering.
            search_params (Optional[Mapping[str, Any]]): Additional parameters for search plugins.
            resolution (Optional[float]): Desired resolution. Used if profiles is None.
            uri (Optional[str]): Output destination URI.
            prepare_params (Optional[Mapping[str, Any]]): Parameters for task preparation.
            extract_params (Optional[Mapping[str, Any]]): Parameters for data extraction.
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs forwarded to all
                plugin instantiations (searchers and extractors). Supports global and per-collection
                overrides — see :meth:`search`, :meth:`prepare_for_extraction`, and
                :meth:`extract_batches` for details.
            plugin_hints (Optional[dict[str, str | Sequence[str]]]): Preferred plugins for specific collections.
                Supports two formats:
                * Collection → plugin: ``{"MODIS": "my_searcher"}``
                * Plugin → collections (inverted): ``{"my_searcher": ["MODIS", "VIIRS"]}``
            failure_mode (FailureMode): Error handling strategy.
            max_batch_workers (Optional[int]): Number of parallel workers for extraction.
            profiles (Optional[Sequence[ExtractionProfile]]): Detailed extraction profiles.
            target_grid_dist (Optional[int]): Override the extractor's default grid cell size in meters.
                Forwarded to :meth:`prepare_for_extraction`.
            target_grid_overlap (Optional[bool]): Override the extractor's default grid overlap setting.
                Forwarded to :meth:`prepare_for_extraction`.
        """
        search_df = self.search(
            collections=collections,
            intersects=intersects,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            search_params=search_params,
            init_params=init_params,
            plugin_hints=plugin_hints,
            failure_mode=failure_mode,
        )

        tasks = self.prepare_for_extraction(
            search_results=search_df,
            target_aoi=intersects,
            resolution=resolution,
            uri=uri,
            profiles=profiles,
            prepare_params=prepare_params,
            init_params=init_params,
            plugin_hints=plugin_hints,
            target_grid_dist=target_grid_dist,
            target_grid_overlap=target_grid_overlap,
        )

        return self.extract_batches(
            extraction_task_batch=tasks,
            extract_params=extract_params,
            init_params=init_params,
            plugin_hints=plugin_hints,
            failure_mode=failure_mode,
            max_batch_workers=max_batch_workers,
        )
