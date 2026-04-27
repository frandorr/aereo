from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, cast

import pandas as pd
import json
from aer.interfaces import ExtractionTask
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
    def _normalize_hints(hints: dict[str, str]) -> dict[str, str]:
        """Return a copy of *hints* with all keys lowercased.

        This makes plugin_hints lookups case-insensitive: the user can write
        ``{"Sentinel-2-L2A": "my_plugin"}`` and the lookup against
        ``"sentinel-2-l2a"`` (the value stored by the registry) will still
        resolve correctly.
        """
        return {k.lower(): v for k, v in hints.items()}

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

    def search(
        self,
        collections: Sequence[str],
        intersects: Optional[BaseGeometry | dict] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
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

            plugin_hints (Optional[dict[str, str]]): Optional mapping of collection to preferred plugin name for search.
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
            hint = plugin_hints.get(collection.lower())
            if hint:
                target_plugin = hint
            else:
                plugin_names = self.registry.find_searchers_for(collection)
                if not plugin_names:
                    logger.warning(
                        "search_skipped_no_plugin",
                        collection=collection,
                    )
                    continue
                target_plugin = plugin_names[0]

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
        prepare_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by collection and distributes batches to appropriate Extractors.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            target_aoi: Optional area of interest as a shapely geometry.
            resolution: The desired resolution for extraction.
            uri: An optional URI defining output path or identifier.
            prepare_params: Additional parameters to pass to prepare_for_extraction method.
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for extractor instantiation.
                Supports global and per-collection overrides, matching the ``prepare_params`` pattern::

                    # Override target_grid_d for a specific collection
                    init_params={"ABI-L1b-RadC": {"target_grid_d": 50_000}}

                    # Or globally for all extractors
                    init_params={"target_grid_d": 50_000}

            plugin_hints: Optional mapping of collection to preferred plugin name.

        Returns:
            A Sequence of prepared ExtractionTasks.
        """
        if search_results.empty:
            return []

        plugin_hints = self._normalize_hints(plugin_hints or {})
        norm_intersects = normalize_geometry(target_aoi)
        all_tasks = []

        grouped_results = search_results.groupby("collection")

        for collection, df_group in grouped_results:
            collection_str = str(collection)
            extractor_names = self.registry.find_extractors_for(collection_str)
            if not extractor_names:
                raise ValueError(
                    f"No Extractor plugin found for collection: {collection_str}"
                )

            target_plugin = plugin_hints.get(collection_str.lower(), extractor_names[0])
            if target_plugin not in extractor_names:
                raise ValueError(
                    f"Hinted plugin '{target_plugin}' is not registered for {collection_str}."
                )

            # Resolve targeted init kwargs and instantiate the extractor
            c_init = self._resolve_params(init_params, collection_str)
            extractor = self.registry.get_extractor(target_plugin, **c_init)

            # Resolve targeted parameters for this collection
            c_params = self._resolve_params(prepare_params, collection_str)

            logger.debug(
                "prepare_batches_start", plugin=target_plugin, collection=collection_str
            )

            batches = extractor.prepare_for_extraction(
                cast(GeoDataFrame, df_group),
                target_aoi=norm_intersects,
                resolution=resolution,
                uri=uri,
                prepare_params=c_params,
            )

            all_tasks.extend(batches)

        return all_tasks

    def extract_batches(
        self,
        extraction_task_batch: Sequence[ExtractionTask],
        extract_params: Optional[Mapping[str, Any]] = None,
        init_params: Optional[Mapping[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Executes the extraction phase by iterating over the provided ExtractionTasks,
        grouping them by collection, and dynamically invoking each Extractor plugin.

        Args:
            extraction_task_batch: A sequence of ExtractionTasks, usually from prepare_for_extraction.
            extract_params: Additional parameters to pass to each Extractor.
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs for extractor instantiation.
                Supports global and per-collection overrides, matching the ``extract_params`` pattern::

                    # Override target_grid_d globally
                    init_params={"target_grid_d": 50_000}

                    # Or per-collection
                    init_params={"ABI-L1b-RadC": {"target_grid_d": 50_000, "target_grid_overlap": True}}

            plugin_hints: Optional mapping of collection to preferred plugin name.
            failure_mode: STRICT raises errors; BEST_EFFORT continues with successful plugins.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        all_artifacts = []
        errors = []
        plugin_hints = self._normalize_hints(plugin_hints or {})

        # Group tasks by collection
        collection_tasks: dict[str, list[ExtractionTask]] = defaultdict(list)
        for task in extraction_task_batch:
            if not task.assets.empty:
                collection = str(task.assets["collection"].iloc[0])
                collection_tasks[collection].append(task)

        for collection, tasks in collection_tasks.items():
            extractor_names = self.registry.find_extractors_for(collection)
            if not extractor_names:
                e = RuntimeError(f"No plugin found for collection: {collection}")
                errors.append(e)
                if failure_mode == FailureMode.STRICT:
                    raise e
                continue

            target_plugin = plugin_hints.get(collection.lower(), extractor_names[0])
            if target_plugin not in extractor_names:
                e = ValueError(
                    f"Hinted plugin '{target_plugin}' not registered for {collection}."
                )
                errors.append(e)
                if failure_mode == FailureMode.STRICT:
                    raise e
                continue

            # Resolve targeted init kwargs and instantiate the extractor
            c_init = self._resolve_params(init_params, collection)
            extractor = self.registry.get_extractor(target_plugin, **c_init)
            plugin_name = type(extractor).__name__
            batch_count = len(tasks)

            # Resolve targeted parameters for this collection
            c_params = self._resolve_params(extract_params, collection)

            logger.info(
                "extract_batches_start",
                plugin=plugin_name,
                batch_count=batch_count,
                collection=collection,
            )

            try:
                df = extractor.extract_batches(tasks, c_params)
                all_artifacts.append(df)
            except Exception as e:
                logger.error(
                    "extract_failed",
                    plugin=plugin_name,
                    collection=collection,
                    exc_info=True,
                )
                errors.append(e)

        if not all_artifacts:
            if failure_mode == FailureMode.STRICT and errors:
                raise RuntimeError(
                    f"Extraction failed strictly for all plugins. {len(errors)} errors captured."
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
        plugin_hints: Optional[dict[str, str]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Convenience 'God Method' running the entire data lifecycle sequentially.

        Args:
            init_params (Optional[Mapping[str, Any]]): Optional constructor kwargs forwarded to all
                plugin instantiations (searchers and extractors). Supports global and per-collection
                overrides — see :meth:`search`, :meth:`prepare_for_extraction`, and
                :meth:`extract_batches` for details.
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
            prepare_params=prepare_params,
            init_params=init_params,
            plugin_hints=plugin_hints,
        )

        return self.extract_batches(
            extraction_task_batch=tasks,
            extract_params=extract_params,
            init_params=init_params,
            plugin_hints=plugin_hints,
            failure_mode=failure_mode,
        )
