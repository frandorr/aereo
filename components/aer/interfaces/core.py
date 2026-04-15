from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Mapping, Sequence, cast

import pandas as pd
from aer.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry


class AerPlugin(ABC):
    """Base class for AER plugins"""

    # 1. Define the type hint, but remove the `= None` default.
    supported_collections: Sequence[str]

    def __init_subclass__(cls, plugin_abstract: bool = False, **kwargs):
        super().__init_subclass__(**kwargs)

        if plugin_abstract:
            return

        # 2. Force the attribute to exist on the subclass
        if not hasattr(cls, "supported_collections"):
            raise TypeError(
                f"Plugin class '{cls.__name__}' must define the 'supported_collections' attribute."
            )

        # 3. Catch the most common developer mistake: using a string instead of a sequence
        # e.g., supported_collections = "GOES-16" instead of ["GOES-16"]
        if isinstance(cls.supported_collections, str):
            raise TypeError(
                f"'{cls.__name__}.supported_collections' must be a Sequence of strings "
                f"(like a list, tuple, or set), but got a single string."
            )

        # 4. Ensure it is a valid sequence type
        if not isinstance(cls.supported_collections, (list, tuple, set)):
            raise TypeError(
                f"'{cls.__name__}.supported_collections' must be a Sequence "
                f"(list, tuple, or set), got {type(cls.supported_collections).__name__}."
            )

        # 5. Prevent empty sequences (optional, but recommended for strictness)
        if len(cls.supported_collections) == 0:
            raise ValueError(
                f"'{cls.__name__}.supported_collections' cannot be empty. "
                f"A plugin must support at least one collection."
            )


class SearchProvider(AerPlugin, plugin_abstract=True):
    @abstractmethod
    def search(
        self,
        collections: Sequence[str],
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        search_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[AssetSchema]:
        """Search for collections data matching the query.

        Args:
            collections: List of collection identifiers to search within.
            intersects: Optional shapely BaseGeometry to filter results by spatial intersection.
            start_datetime: Optional start datetime to filter results by temporal range.
            end_datetime: Optional end datetime to filter results by temporal range.
            search_params: Additional parameters for the search, specific to
                the collection or provider.

        Returns:
            A GeoDataFrame of search results, where each row represents a dataset
            or asset that matches the search criteria, and includes metadata such
            as collection, geometry, time range, and any other relevant attributes.
        """
        ...


class Extractor(AerPlugin, plugin_abstract=True):
    @abstractmethod
    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        prepare_params: dict[str, Any] | None,
    ) -> list[GeoDataFrame[AssetSchema]]:
        """Prepare search results for extraction by grouping/filtering/transforming/etc
        them into one or more GeoDataFrames of extraction tasks.
        Each GeoDataFrame represents a batch of results that can be processed together for extraction.

        Args:
            search_results: The GeoDataFrame of search results to prepare for extraction.
            prepare_params: Additional parameters for preparation,
                user defined and specific to the collection, provider, outputs, etc.

        Returns:
            A list of GeoDataFrames, each containing a batch of search results to be extracted together.
            If you wish to extract each result individually, return a list where each element
            is a single-row GeoDataFrame (e.g., `[results.iloc[[i]] for i in range(len(results))]`).

        """
        ...

    @abstractmethod
    def extract(
        self,
        assets_batch: GeoDataFrame[AssetSchema],
        extract_params: dict[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Extract data for a batch of assets.
        Args:
            assets_batch: A GeoDataFrame containing a batch of assets to extract.
                This is one of the GeoDataFrames returned by the `prepare_for_extraction` hook.
            extract_params: Additional parameters for extraction,
                user defined and specific to the collection, provider, outputs, etc.

        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
            time range, and any other relevant attributes.
        """
        ...

    def extract_batches(
        self,
        assets_batches: list[GeoDataFrame[AssetSchema]],
        extract_params: dict[str, Any] | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Execute extraction over multiple batches.

        The default implementation is sequential. Subclasses can override
        this method to implement parallel execution (e.g., ThreadPoolExecutor,
        multiprocessing, or distributed cloud compute) suited to their specific I/O profile.

        Args:
            assets_batches: A list of GeoDataFrames, where each GeoDataFrame contains a batch
                of assets to extract. This is the output of the `prepare_for_extraction` hook.
            extract_params: Additional parameters for extraction,
                user defined and specific to the collection, provider, outputs, etc.
        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
        """
        results = []
        for batch in assets_batches:
            # We call the abstract method internally
            results.append(self.extract(batch, extract_params))

        # concat
        concatenated = pd.concat(results, ignore_index=True)
        validated = ArtifactSchema.validate(concatenated)
        return cast(GeoDataFrame[ArtifactSchema], validated)
