from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, cast

import pandas as pd
from aer.interfaces.core import Extractor
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


@dataclass
class ExtractionError:
    """Structured capture of an isolated plugin failure without crashing the whole pipeline."""

    plugin: str
    collection: str
    exception: Exception


@dataclass
class ExtractorBatch:
    """Explicit mapping linking an Extractor instance to its specific task workloads."""

    extractor: Extractor
    batches: list[GeoDataFrame[AssetSchema]]


class PreparedExtractionContext:
    """
    Holds prepared batches of Assets grouped by collection and mapped to their respective Extractor instances, ready for execution.

    This context is the output of the preparation stage and the input to the extraction stage,
    encapsulating all necessary state for the latter to perform its function without needing to reference external state or the registry.

    """

    def __init__(self, extractor_map: list[ExtractorBatch]):
        """
        Initializes the PreparedExtractionContext with a mapping of Extractor instances to their corresponding batches of Assets.

        Args:
            extractor_map (list[ExtractorBatch]): A list of ExtractorBatch dataclasses,
                each containing an Extractor instance and its associated batches of Assets to be extracted.
        """
        self.extractor_map = extractor_map
        self.errors: list[ExtractionError] = []

    def extract(
        self,
        extract_params: Optional[dict[str, Any]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Executes the extraction phase by iterating over the prepared ExtractorBatch mappings,
        invoking each Extractor's extract_batches method, and collating results.

        Args:
            extract_params (Optional[dict[str, Any]]): Additional parameters to pass to each Extractor's extract_batches method.
            failure_mode (FailureMode): Determines pipeline behavior when partial or total plugin failures occur during extraction. Defaults to STRICT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.
        Returns:
            GeoDataFrame[ArtifactSchema]: A unified GeoDataFrame containing all extracted Artifacts from
            successful Extractor executions, validated against the ArtifactSchema.
        """

        all_artifacts = []

        for batch_context in self.extractor_map:
            plugin_name = type(batch_context.extractor).__name__
            batch_count = len(batch_context.batches)

            logger.info(
                "extract_batches_start", plugin=plugin_name, batch_count=batch_count
            )

            try:
                # The extract_batches method handles its own internal concurrency per the Plugin Contract
                df = batch_context.extractor.extract_batches(
                    batch_context.batches, extract_params
                )
                all_artifacts.append(df)

            except Exception as e:
                logger.error("extract_failed", plugin=plugin_name, exc_info=True)

                # In robust infra, we retain structured error footprints instead of raw Exceptions
                self.errors.append(
                    ExtractionError(
                        plugin=plugin_name, collection="merged", exception=e
                    )
                )

        if not all_artifacts:
            if failure_mode == FailureMode.STRICT and self.errors:
                raise RuntimeError(
                    f"Extraction failed strictly for all plugins. {len(self.errors)} errors captured."
                )

            logger.warning("extract_empty_result", reason="No artifacts retrieved")
            return cast(GeoDataFrame, ArtifactSchema.empty())

        final_df = pd.concat(all_artifacts, ignore_index=True)
        return cast(GeoDataFrame, ArtifactSchema.validate(final_df))


class SearchResultContext:
    """
    Holds successfully fetched Assets across multiple collections.
    This context is the output of the search stage and the input to the preparation stage,
    encapsulating all necessary state for the latter to perform its function without needing to reference external state or the
    registry.
    """

    def __init__(
        self, registry: AerRegistry, search_results: GeoDataFrame[AssetSchema]
    ):
        """
        Initializes the SearchResultContext with the merged search results and a reference to the AerRegistry for downstream operations.

        Args:
            registry (AerRegistry): A reference to the AerRegistry instance for plugin discovery during preparation and extraction stages.
            search_results (GeoDataFrame[AssetSchema]): A GeoDataFrame containing the merged search results from
                all successful search plugins, validated against the AssetSchema.
        """
        self.registry = registry
        self.search_results = search_results

    def prepare(
        self,
        prepare_params: Optional[dict[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
    ) -> "PreparedExtractionContext":
        """Groups search results by collection and distributes batches to appropriate Extractors.

        Args:
            prepare_params (Optional[dict[str, Any]]): Additional parameters to pass to each Extractor's prepare_for_extraction method.
            plugin_hints (Optional[dict[str, str]]): Optional mapping of collection to preferred plugin name for preparation.
                    If not provided, the first registered plugin will be used for each collection.
         Returns:
            PreparedExtractionContext: A context object containing the mapping of Extractor instances to their respective batches of Assets,
                ready for the extraction phase.
         Raises:
            ValueError: If no Extractor plugins are found for a collection or if a hinted plugin is not registered for the collection.
        """
        if self.search_results.empty:
            return PreparedExtractionContext([])

        plugin_hints = plugin_hints or {}
        extractor_map = []

        grouped_results = self.search_results.groupby("collection")

        for collection, df_group in grouped_results:
            # 1. Find eligible Extractor plugins for this collection
            extractor_names = self.registry.find_extractors_for(str(collection))
            if not extractor_names:
                raise ValueError(
                    f"No Extractor plugin found for collection: {collection}"
                )
            # 2. Apply plugin hinting if provided, otherwise default to the first registered plugin
            target_plugin = plugin_hints.get(str(collection), extractor_names[0])
            if target_plugin not in extractor_names:
                raise ValueError(
                    f"Hinted plugin '{target_plugin}' is not registered for {collection}."
                )

            # Instantiation happens here, guaranteeing a fresh, stateless plugin per collection
            extractor = self.registry.get_extractor(target_plugin)
            logger.debug(
                "prepare_batches_start", plugin=target_plugin, collection=collection
            )

            batches = extractor.prepare_for_extraction(
                cast(GeoDataFrame, df_group), prepare_params
            )
            extractor_map.append(ExtractorBatch(extractor=extractor, batches=batches))

        return PreparedExtractionContext(extractor_map)


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
    - Provides structured contexts for downstream preparation and extraction stages
    - Implements configurable failure modes for robust real-world operation."""

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
    ) -> SearchResultContext:
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
            SearchResultContext: A context object containing the merged search results and registry reference for downstream operations.

        Example Usage:
        >>> client = AerClient()
        >>> search_ctx = client.search(
        ...     collections=["sentinel-2-l2a", "landsat-8-l2"],
        ...     intersects={"type": "Polygon", "coordinates": [[[...]]]},
        ...     start_datetime=datetime(2023, 1, 1),
        ...     end_datetime=datetime(2023, 1, 31),
        ...     search_params={"cloud_cover": {"lte": 20}},
        ...     plugin_hints={"sentinel-2-l2a": "custom_sentinel_plugin"},
        ...     failure_mode=FailureMode.BEST_EFFORT,
        ... )

        Pipeline example:
        >>> artifacts_df = client.run_pipeline(
        ...     collections=["sentinel-2-l2a", "landsat-8-l2"],
        ...     intersects={"type": "Polygon", "coordinates": [[[...]]]},
        ...     start_datetime=datetime(2023, 1, 1),
        ...     end_datetime=datetime(2023, 1, 31),
        ...     search_params={"cloud_cover": {"lte": 20}},
        ...     prepare_params={"resample": "16D"},
        ...     extract_params={"bands": ["B04", "B08"]},
        ...     plugin_hints={"sentinel-2-l2a": "custom_sentinel_plugin"},
        ...     failure_mode=FailureMode.BEST_EFFORT,
        ... )
        """

        plugin_hints = plugin_hints or {}
        norm_intersects = normalize_geometry(intersects)

        # 1. Map plugins to collections safely
        searcher_to_collections = defaultdict(list)
        for collection in collections:
            plugin_names = self.registry.find_searchers_for(collection)
            if not plugin_names:
                logger.warning("search_plugin_not_found", collection=collection)
                continue

            target_plugin = plugin_hints.get(collection, plugin_names[0])
            searcher_to_collections[target_plugin].append(collection)

        all_results = []
        errors = []

        if not searcher_to_collections:
            if failure_mode == FailureMode.STRICT:
                raise RuntimeError(
                    "No eligible search plugins found for the requested collections."
                )
            return SearchResultContext(
                self.registry, cast(GeoDataFrame, AssetSchema.empty())
            )

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
            return SearchResultContext(
                self.registry, cast(GeoDataFrame, AssetSchema.empty())
            )

        # 4. Collapse results safely
        merged_results = cast(
            GeoDataFrame,
            AssetSchema.validate(pd.concat(all_results, ignore_index=True)),
        )
        return SearchResultContext(self.registry, merged_results)

    def run_pipeline(
        self,
        collections: Sequence[str],
        intersects: Optional[BaseGeometry | dict] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
        prepare_params: Optional[dict[str, Any]] = None,
        extract_params: Optional[dict[str, Any]] = None,
        plugin_hints: Optional[dict[str, str]] = None,
        failure_mode: FailureMode = FailureMode.STRICT,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Convenience 'God Method' running the entire data lifecycle sequentially.

        Args:
            collections (Sequence[str]): List of collection identifiers to search across.
            intersects (Optional[BaseGeometry | dict]): Optional geometry to spatially filter search results.
            start_datetime (Optional[datetime]): Optional start datetime for temporal filtering.
            end_datetime (Optional[datetime]): Optional end datetime for temporal filtering.
            search_params (Optional[Mapping[str, Any]]): Additional parameters to pass to search plugins.
            prepare_params (Optional[dict[str, Any]]): Additional parameters to pass to each Extractor's prepare_for_extraction method.
            extract_params (Optional[dict[str, Any]]): Additional parameters to pass to each Extractor's extract_batches method.
            plugin_hints (Optional[dict[str, str]]): Optional mapping of collection to preferred plugin name for search and preparation.
                    If not provided, the first registered plugin will be used for each collection.
            failure_mode (FailureMode): Determines pipeline behavior when partial or total plugin failures occur. Defaults to STRICT.
                - STRICT: Any plugin failure raises an exception and halts the pipeline.
                - BEST_EFFORT: Logs failures but continues processing with successful plugins.
        Returns:
            GeoDataFrame[ArtifactSchema]: A unified GeoDataFrame containing all extracted Artifacts from successful Extractor executions, validated against the ArtifactSchema.
        """
        search_ctx = self.search(
            collections=collections,
            intersects=intersects,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            search_params=search_params,
            plugin_hints=plugin_hints,
            failure_mode=failure_mode,
        )

        prep_ctx = search_ctx.prepare(
            prepare_params=prepare_params, plugin_hints=plugin_hints
        )

        return prep_ctx.extract(
            extract_params=extract_params, failure_mode=failure_mode
        )
