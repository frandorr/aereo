from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, cast

import pandas as pd
from aer.interfaces.core import ExtractionTask
from aer.registry.core import AerRegistry
from aer.schemas.core import ArtifactSchema, AssetSchema
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

    def search(
        self,
        collections: Sequence[str],
        intersects: Optional[BaseGeometry | dict] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
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
            plugin_hints (Optional[dict[str, str]]): Optional mapping of collection to preferred plugin name for search.
                    If not provided, the first registered plugin will be used.
            failure_mode (FailureMode): Determines pipeline behavior when partial or total plugin failures occur. Defaults to BEST_EFFORT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.
        Returns:
            GeoDataFrame[AssetSchema]: A verified GeoDataFrame of combined search results.
        """

        plugin_hints = plugin_hints or {}
        norm_intersects = normalize_geometry(intersects)

        # 1. Map plugins to collections safely
        searcher_to_collections = defaultdict(list)
        for collection in collections:
            hint = plugin_hints.get(collection)
            if hint:
                target_plugin = hint
            else:
                plugin_names = self.registry.find_searchers_for(collection)
                if not plugin_names:
                    logger.warning(
                        "Search skipped for collection with no registered plugin. \n"
                        "You may want to check your registry configuration or plugin hints (e.g. plugin_hints={'a_collection': 'search_plugin'})",
                        collection=collection,
                    )
                    continue

                target_plugin = plugin_names[0]

            mapped_collections = self.registry.get_collection_mapping_for_searcher(
                target_plugin, [collection]
            )
            searcher_to_collections[target_plugin].extend(mapped_collections)

        all_results = []
        errors = []

        if not searcher_to_collections:
            if failure_mode == FailureMode.STRICT:
                raise RuntimeError(
                    "No eligible search plugins found for the requested collections."
                )
            return cast(GeoDataFrame, AssetSchema.empty())

        # 2. Parallel fan-out dispatch to remote plugin APIs
        with ThreadPoolExecutor(
            max_workers=max(1, len(searcher_to_collections))
        ) as executor:
            futures = {
                executor.submit(
                    self.registry.get_searcher(p_name).search,
                    collections=s_cols,
                    intersects=norm_intersects,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    search_params=search_params,
                ): (p_name, s_cols)
                for p_name, s_cols in searcher_to_collections.items()
            }

            for future in as_completed(futures):
                plugin_name, cols = futures[future]
                try:
                    df = future.result()
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
        prepare_params: Optional[dict[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
    ) -> Sequence[ExtractionTask]:
        """Groups search results by collection and distributes batches to appropriate Extractors.

        Args:
            search_results: The merged GeoDataFrame of search results to prepare.
            target_aoi: Optional area of interest as a shapely geometry.
            resolution: The desired resolution for extraction.
            uri: An optional URI defining output path or identifier.
            prepare_params: Additional parameters to pass to prepare_for_extraction method.
            plugin_hints: Optional mapping of collection to preferred plugin name.

        Returns:
            A Sequence of prepared ExtractionTasks.
        """
        if search_results.empty:
            return []

        plugin_hints = plugin_hints or {}
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

            target_plugin = plugin_hints.get(collection_str, extractor_names[0])
            if target_plugin not in extractor_names:
                raise ValueError(
                    f"Hinted plugin '{target_plugin}' is not registered for {collection_str}."
                )

            extractor = self.registry.get_extractor(target_plugin)
            logger.debug(
                "prepare_batches_start", plugin=target_plugin, collection=collection_str
            )

            batches = extractor.prepare_for_extraction(
                cast(GeoDataFrame, df_group),
                target_aoi=norm_intersects,
                resolution=resolution,
                uri=uri,
                prepare_params=prepare_params,
            )
            all_tasks.extend(batches)

        return all_tasks

    def extract_batches(
        self,
        extraction_task_batch: Sequence[ExtractionTask],
        extract_params: Optional[dict[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Executes the extraction phase by iterating over the provided ExtractionTasks,
        grouping them by collection, and dynamically invoking each Extractor plugin.

        Args:
            extraction_task_batch: A sequence of ExtractionTasks, usually from prepare_for_extraction.
            extract_params: Additional parameters to pass to each Extractor.
            plugin_hints: Optional mapping of collection to preferred plugin name.
            failure_mode: STRICT raises errors; BEST_EFFORT continues with successful plugins.

        Returns:
            A unified GeoDataFrame containing all extracted Artifacts.
        """
        all_artifacts = []
        errors = []
        plugin_hints = plugin_hints or {}

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

            target_plugin = plugin_hints.get(collection, extractor_names[0])
            if target_plugin not in extractor_names:
                e = ValueError(
                    f"Hinted plugin '{target_plugin}' not registered for {collection}."
                )
                errors.append(e)
                if failure_mode == FailureMode.STRICT:
                    raise e
                continue

            extractor = self.registry.get_extractor(target_plugin)
            plugin_name = type(extractor).__name__
            batch_count = len(tasks)

            logger.info(
                "extract_batches_start", plugin=plugin_name, batch_count=batch_count
            )

            try:
                df = extractor.extract_batches(tasks, extract_params)
                all_artifacts.append(df)
            except Exception as e:
                logger.error("extract_failed", plugin=plugin_name, exc_info=True)
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
        prepare_params: Optional[dict[str, Any]] = None,
        extract_params: Optional[dict[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Convenience 'God Method' running the entire data lifecycle sequentially.
        """
        search_df = self.search(
            collections=collections,
            intersects=intersects,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            search_params=search_params,
            plugin_hints=plugin_hints,
            failure_mode=failure_mode,
        )

        tasks = self.prepare_for_extraction(
            search_results=search_df,
            target_aoi=intersects,
            resolution=resolution,
            uri=uri,
            prepare_params=prepare_params,
            plugin_hints=plugin_hints,
        )

        return self.extract_batches(
            extraction_task_batch=tasks,
            extract_params=extract_params,
            plugin_hints=plugin_hints,
            failure_mode=failure_mode,
        )
