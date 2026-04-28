from abc import ABC, abstractmethod
from datetime import datetime
from functools import cached_property
from typing import Any, Mapping, Sequence, cast

import attrs
import pandas as pd
from aer.grid import GridCell, GridDefinition
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

        # 5. Empty sequences are allowed (used by plugins that only support plugin_hints)


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


@attrs.frozen
class ExtractionTask:
    assets: GeoDataFrame[AssetSchema]
    target_grid_d: int
    target_grid_overlap: bool
    resolution: float
    uri: str
    aoi: BaseGeometry | None = None
    task_context: dict[str, Any] = attrs.field(factory=dict)

    @cached_property
    def overlapping_grid_cells(self) -> Sequence[GridCell]:
        """
        Calculates the intersecting grid cells for this specific task's AOI.
        """
        grid_def = GridDefinition(
            d=self.target_grid_d,
            overlap=self.target_grid_overlap,
        )

        if hasattr(self.assets, "union_all"):
            geometry = self.assets.union_all()
        else:
            geometry = None

        intersection = (
            geometry.intersection(self.aoi)
            if (geometry is not None and self.aoi)
            else (geometry or self.aoi)
        )

        if intersection is None:
            return []

        return grid_def.generate_grid_cells(intersection)

    def __repr__(self) -> str:
        n_assets = len(self.assets) if self.assets is not None else 0
        geom_type = getattr(self.aoi, "geom_type", None)

        return (
            f"{self.__class__.__name__}("
            f"n_assets={n_assets}, "
            f"resolution={self.resolution}, "
            f"grid_d={self.target_grid_d}, "
            f"overlap={self.target_grid_overlap}, "
            f"aoi={geom_type}, "
            f"uri='{self.uri}'"
            f")"
        )


class Extractor(AerPlugin, plugin_abstract=True):
    @property
    @abstractmethod
    def target_grid_d(self) -> int:
        """The size of the square grid cell in meters (e.g., 100000)."""
        pass

    @property
    def target_grid_overlap(self) -> bool:
        """Default overlap setting. Subclasses can override this."""
        return False

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        target_aoi: BaseGeometry | None = None,
        resolution: float | None = None,
        uri: str | None = None,
        prepare_params: Mapping[str, Any] | None = None,
    ) -> Sequence[ExtractionTask]:
        """Prepare search results for extraction by grouping/filtering/transforming/etc
        them into one or more GeoDataFrames of extraction tasks.
        Each GeoDataFrame represents a batch of results that can be processed together for extraction.

        Args:
            search_results: The GeoDataFrame of search results to prepare for extraction.
            target_aoi: The area of interest as a shapely geometry. This can be used to spatially filter or group the search results.
            resolution: The desired resolution for extraction, which can be used to determine how to group or filter the search results.
                It can be None if user prefers to infer resolution from the search results.
            uri: An optional URI that can be used to define an output path or identifier for the extraction results.
                This can be used to group search results that should be extracted together.
                For example it can be a bucket.
                It can be None if user prefers to infer uri from the search results or other parameters.
            prepare_params: Additional parameters for preparation,
                user defined and specific to the collection, provider, outputs, etc.

        Returns:
            A Sequence of ExtractionTask, each containing a batch of search results to be extracted together.
            If you wish to extract each result individually, return a sequence where each extraction_task.assets
            is a single-row GeoDataFrame (e.g., `[results.iloc[[i]] for i in range(len(results))]`).

        """

        # Default implementation: one task per asset (no grouping), need resolution and uri to be defined for the task
        if resolution is None or uri is None:
            raise ValueError(
                "Default prepare_for_extraction requires resolution and uri to be defined"
                "If you want to prepare without resolution or uri, you need to override this method with a custom implementation."
            )
        tasks = []
        for i in range(len(search_results)):
            asset_batch = search_results.iloc[[i]]  # single-row GeoDataFrame
            task = ExtractionTask(
                assets=asset_batch,
                target_grid_d=self.target_grid_d,
                target_grid_overlap=self.target_grid_overlap,
                resolution=resolution,
                uri=uri,
                aoi=target_aoi,
                task_context={"prepare_params": prepare_params},
            )
            tasks.append(task)
        return tasks

    @abstractmethod
    def extract(
        self,
        extraction_task: ExtractionTask,
        extract_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Extract data for a batch of assets (equivalent to one item of the prepare_for_extraction output).
        Args:
            extraction_task: An ExtractionTask containing a batch of assets to extract.
                This is one of the items returned by the `prepare_for_extraction` method.
                    extraction_task.task_context holds batch-specific data generated during preparation
            extract_params: Additional parameters for extraction,
                user defined and specific to the collection, provider, outputs, etc. Holds global configuration (e.g. max_retries, credentials).

        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
            time range, and any other relevant attributes.
        """
        ...

    def extract_batches(
        self,
        extraction_task_batch: Sequence[ExtractionTask],
        extract_params: Mapping[str, Any] | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Execute extraction over multiple batches.

        The default implementation is sequential. Subclasses can override
        this method to implement parallel execution (e.g., ThreadPoolExecutor,
        multiprocessing, or distributed cloud compute) suited to their specific I/O profile.

        Args:
            extraction_task_batch: A sequence of ExtractionTask, where each one contains a batch
                of assets to extract. This is the output of the `prepare_for_extraction` method.
            extract_params: Additional parameters for extraction,
                user defined and specific to the collection, provider, outputs, etc.
        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
        """
        # default implementation: sequential execution of extract for each batch
        results = []
        for batch in extraction_task_batch:
            # We call the abstract method internally
            results.append(self.extract(batch, extract_params))

        # concat
        concatenated = pd.concat(results, ignore_index=True)
        validated = ArtifactSchema.validate(concatenated)
        return cast(GeoDataFrame[ArtifactSchema], validated)
