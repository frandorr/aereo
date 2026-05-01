import logging
import sys
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

import attrs
import pandas as pd
from aer.grid import GridCell
from aer.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


class Downloader(Protocol):
    """Callable that downloads a URL to a local path."""

    def __call__(self, url: str, local_path: Path) -> None:
        """Download *url* to *local_path*."""
        ...


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
class ExtractionProfile:
    """
    Defines a blueprint for extraction, specifying which collections and variables
    to extract and at what resolution.

    Attributes:
        name: A unique identifier for this profile (e.g., 'viirs_cloud_mask').
        resolution: Resolution for extraction in meters for this specific profile.
        collection_variables_map: Mapping of collection to variables.
        extra_params: A container for user-specific or plugin-specific attributes
            (e.g., a mapping for Satpy readers).
    """

    name: str
    resolution: float
    collection_variables_map: Mapping[str, Sequence[str]] = attrs.field(factory=dict)
    extra_params: Mapping[str, Any] = attrs.field(factory=dict)


@attrs.frozen
class ExtractionTask:
    """
    A class representing a task for extracting data.

    Attributes:
        assets: GeoDataFrame of assets to extract. It can group multiple collections
            (for example Imagery + Geolocation). Schema is defined in `aer.schemas.AssetSchema`.
        profile: The ExtractionProfile containing target variables and resolution.
        uri: Destination URI for extracted artifacts.
        grid_cells: Spatial grid cells this task covers.
        aoi: Optional area-of-interest geometry used to clip the extraction region.
        prepare_params: Parameters forwarded from ``prepare_for_extraction`` that drove
            task construction (e.g. ``dataset_names``, ``cells_per_chunk``). Plugins can
            read these in ``extract()`` without needing them re-passed via ``extract_params``.
        task_context: Observability metadata generated during task preparation
            (e.g. ``chunk_id``, ``total_chunks``, ``start_time``).
    """

    assets: GeoDataFrame[AssetSchema]
    profile: ExtractionProfile
    uri: str
    grid_cells: Sequence[GridCell]
    aoi: BaseGeometry | None = None
    prepare_params: Mapping[str, Any] = attrs.field(factory=dict)
    task_context: Mapping[str, Any] = attrs.field(factory=dict)

    def __attrs_post_init__(self) -> None:
        if self.assets is None or len(self.assets) == 0:
            raise ValueError("assets cannot be empty")

        if self.profile.collection_variables_map:
            if "collection" in self.assets.columns:
                asset_collections = set(self.assets["collection"])
                for col in self.profile.collection_variables_map:
                    if col not in asset_collections:
                        raise ValueError(
                            f"Collection '{col}' in collection_variables_map not found in assets collection column."
                        )

    def __repr__(self) -> str:
        n_assets = len(self.assets) if self.assets is not None else 0

        if self.grid_cells:
            all_cells_str = (
                f"{self.grid_cells[0].__class__.__name__}('"
                + ", ".join([str(c) for c in self.grid_cells])
                + "')"
            )
        else:
            all_cells_str = "[]"

        return (
            f"{self.__class__.__name__}("
            f"n_assets={n_assets}, "
            f"profile='{self.profile.name}', "
            f"resolution={self.profile.resolution}, "
            f"grid_cells={all_cells_str}, "
            f"uri='{self.uri}'"
            f")"
        )


def _extract_wrapper(
    extractor: "Extractor",
    task: "ExtractionTask",
    extract_params: Mapping[str, Any] | None,
) -> "GeoDataFrame[ArtifactSchema]":
    """Module-level wrapper so ProcessPoolExecutor can pickle the call."""
    return extractor.extract(task, extract_params)


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
        target_grid_dist: int | None = None,
        target_grid_overlap: bool | None = None,
        uri: str | None = None,
        profiles: Sequence[ExtractionProfile] | None = None,
        prepare_params: Mapping[str, Any] | None = None,
    ) -> Sequence[ExtractionTask]:
        """Prepare extraction tasks by grouping assets by profile and start time, then chunking grid cells."""
        if uri is None:
            raise ValueError(
                "Default prepare_for_extraction requires uri to be defined."
            )

        if not profiles:
            raise ValueError(
                "Default prepare_for_extraction requires at least one profile to be defined."
            )

        prepare_params = prepare_params or {}
        cells_per_chunk = int(prepare_params.get("cells_per_chunk", 50))

        grid_dist = (
            target_grid_dist if target_grid_dist is not None else self.target_grid_d
        )
        grid_overlap = (
            target_grid_overlap
            if target_grid_overlap is not None
            else self.target_grid_overlap
        )

        from aer.grid import GridDefinition

        grid_def = GridDefinition(d=grid_dist, overlap=grid_overlap)

        tasks = []

        # 1. Iterate over each profile
        for profile in profiles:
            # Filter assets by profile collections if specified
            if profile.collection_variables_map:
                profile_assets = search_results[
                    search_results["collection"].isin(
                        list(profile.collection_variables_map.keys())
                    )
                ].copy()
            else:
                profile_assets = search_results.copy()

            if profile_assets.empty:
                continue

            # 2. Group by exact start_time
            for start_time, time_group in profile_assets.groupby("start_time"):
                # 3. Determine base geometry union of the group
                if hasattr(time_group, "union_all"):
                    group_geom = time_group.union_all()
                else:
                    group_geom = time_group.geometry.unary_union

                if group_geom is None or group_geom.is_empty:
                    continue

                # 4. Intersect with target_aoi if provided
                if target_aoi is not None:
                    aoi_geom = target_aoi.intersection(group_geom)
                else:
                    aoi_geom = group_geom

                if aoi_geom is None or aoi_geom.is_empty:
                    continue

                # 5. Generate grid cells specifically for the intersected geometry
                all_cells = list(grid_def.generate_grid_cells(aoi_geom))
                if not all_cells:
                    continue

                # 6. Chunk cells and create tasks
                cell_chunks = [
                    all_cells[i : i + cells_per_chunk]
                    for i in range(0, len(all_cells), cells_per_chunk)
                ]

                for chunk_idx, cells in enumerate(cell_chunks):
                    task = ExtractionTask(
                        assets=cast(GeoDataFrame, time_group),
                        profile=profile,
                        uri=uri,
                        grid_cells=cells,
                        aoi=target_aoi,
                        prepare_params=prepare_params,
                        task_context={
                            "chunk_id": chunk_idx,
                            "total_chunks": len(cell_chunks),
                            "start_time": str(start_time),
                        },
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
                user defined and specific to the collection, provider, outputs, etc.
                Holds global configuration (e.g. max_retries, credentials).
                Per-task preparation parameters are available on ``extraction_task.prepare_params``.

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
        max_batch_workers: int | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Execute extraction over multiple batches, optionally in parallel.

        When ``max_batch_workers`` is set, batches are processed in parallel
        using ``ProcessPoolExecutor`` with a ``forkserver`` context (Unix) or
        ``spawn`` context (Windows).  This avoids thread-safety issues that can
        occur with the default ``fork`` start method when threaded libraries
        such as dask or rasterio have already been imported in the parent
        process.  Failed batches are logged and collected; if *all* batches fail
        a ``RuntimeError`` is raised.

        When ``max_batch_workers`` is ``None`` (default), falls back to
        sequential execution.

        Args:
            extraction_task_batch: A sequence of ExtractionTask, where each one contains a batch
                of assets to extract. This is the output of the `prepare_for_extraction` method.
            extract_params: Additional parameters for extraction,
                user defined and specific to the collection, provider, outputs, etc.
            max_batch_workers: Maximum number of worker processes for parallel execution.
                ``None`` (default) disables parallelism and runs sequentially.
        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
            time range, and any other relevant attributes.
        """
        if max_batch_workers is None:
            # Sequential path (original behaviour)
            results = []
            for batch in extraction_task_batch:
                results.append(self.extract(batch, extract_params))
            concatenated = pd.concat(results, ignore_index=True)
            validated = ArtifactSchema.validate(concatenated)
            return cast(GeoDataFrame[ArtifactSchema], validated)

        # Parallel path
        results: list[GeoDataFrame[ArtifactSchema]] = []
        errors: list[str] = []

        tasks = [(self, batch, extract_params) for batch in extraction_task_batch]

        mp_context = get_context("spawn" if sys.platform == "win32" else "forkserver")
        with ProcessPoolExecutor(
            max_workers=max_batch_workers, mp_context=mp_context
        ) as executor:
            futures = {
                executor.submit(_extract_wrapper, *t): i for i, t in enumerate(tasks)
            }

            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "batch_extract_failed",
                        extra={"batch": batch_idx, "error": str(exc)},
                    )
                    errors.append(str(exc))

        if not results:
            raise RuntimeError(
                f"All {len(extraction_task_batch)} batches failed. Errors: {errors}"
            )

        concatenated = pd.concat(results, ignore_index=True)
        validated = ArtifactSchema.validate(concatenated)
        return cast(GeoDataFrame[ArtifactSchema], validated)
