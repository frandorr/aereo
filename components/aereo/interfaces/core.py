"""Core interface definitions, plugin types, and data models for AEREO.

Defines configuration schemas, plugin protocols, and task structures
like SearchProvider, Reader, Writer, Reprojector, and Processor.
"""

from __future__ import annotations

from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Mapping,
    Protocol,
    Sequence,
    cast,
    runtime_checkable,
)

if TYPE_CHECKING:
    from aereo.pipeline import ExtractionJob

import attrs
import numpy as np
import pandas as pd
import pystac
import shapely
import xarray as xr
from aereo.grid import GridCell
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

WGS84_CRS: str = "epsg:4326"


AereoPlugin = Any


@runtime_checkable
class Reader(Protocol):
    """Reads source data for an extraction task and returns an ``xr.Dataset``."""

    def __call__(self, task: ExtractionTask, **kwargs: Any) -> xr.Dataset:
        """Read data for *task* and return a dataset.

        The orchestrator passes the full ``ExtractionTask``. Readers that only
        need the source URIs or the AOI can use ``task.uris`` and ``task.bbox``.
        Readers that need STAC items can use ``task.stac_items``.
        Additional configuration (bands, CRS, resolution, etc.) is supplied
        through ``**kwargs`` or via ``functools.partial``.
        """
        ...


@runtime_checkable
class Processor(Protocol):
    """Pure ``xarray.Dataset -> xarray.Dataset`` transform."""

    def __call__(self, *args: Any, **kwargs: Any) -> xr.Dataset:
        """Transform a dataset and return a new dataset."""
        ...


@runtime_checkable
class Reprojector(Protocol):
    """Reprojects/resamples an ``xarray.Dataset`` to a target definition."""

    def __call__(self, *args: Any, **kwargs: Any) -> xr.Dataset:
        """Reproject a dataset and return a new dataset.

        The orchestrator may inject ``geobox`` when ``ExtractionJob.reproject_mode``
        is ``"grid"``. Otherwise the caller is responsible for providing target
        parameters such as ``crs`` and ``resolution`` through ``**kwargs``.
        """
        ...


@runtime_checkable
class Writer(Protocol):
    """Serialises an ``xarray.Dataset`` to a single file."""

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Write a dataset to a path and return the written path.

        The orchestrator is responsible for constructing the path (e.g. EOIDS
        layout) and for splitting time dimensions before calling the writer. The
        writer receives a dataset without a ``time`` dimension and returns the
        path it wrote to.
        """
        ...


@runtime_checkable
class TaskBuilder(Protocol):
    """Builds a sequence of extraction tasks from search results.

    Task builders are job-level plugins: they run once per job, grouping and
    chunking search-result assets into ``ExtractionTask`` objects that the
    per-task extraction pipeline can execute.
    """

    def __call__(
        self,
        search_results: GeoDataFrame[AssetSchema],
        job: ExtractionJob,
    ) -> Sequence[ExtractionTask]:
        """Build extraction tasks from *search_results* using *job* configuration.

        Args:
            search_results: GeoDataFrame of assets returned by a search provider.
            job: Parent extraction job supplying grid, output, and reader/writer
                configuration.

        Returns:
            A sequence of prepared extraction tasks.
        """
        ...


@runtime_checkable
class SearchProvider(Protocol):
    """Interface for search providers.

    Search providers are callables that receive collection, spatial, and
    temporal constraints and return a GeoDataFrame of matched assets.
    """

    def __call__(
        self,
        collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        **kwargs: Any,
    ) -> GeoDataFrame[AssetSchema]:
        """Execute search based on the provided constraints.

        Args:
            collections: Mapping of collection -> asset keys, or list of collections.
            intersects: AOI geometry.
            start_datetime: Optional start of temporal window.
            end_datetime: Optional end of temporal window.
            **kwargs: Implementation-specific parameters (e.g. ``stac_api_url``).

        Returns:
            GeoDataFrame of matched assets.
        """
        ...


def _to_native(obj: Any) -> Any:
    """Recursively convert numpy containers in *obj* to plain Python types.

    Parquet round-trips can leave list fields as ``np.ndarray`` instances.
    ``pystac.Item.from_dict`` expects JSON-like structures, so this helper
    normalises arrays/scalars before reconstruction.
    """
    if isinstance(obj, np.ndarray):
        return [_to_native(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    return obj


def empty_asset_result() -> GeoDataFrame[AssetSchema]:
    """Return an empty GeoDataFrame with AssetSchema columns."""
    import geopandas as gpd

    columns = list(AssetSchema.to_schema().columns.keys())
    if "geometry" not in columns:
        columns.append("geometry")
    gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry")
    return cast(GeoDataFrame[AssetSchema], AssetSchema.validate(gdf))


def build_collection_asset_filters(
    collections_config: Mapping[str, Sequence[str]] | Sequence[str] | None,
) -> tuple[list[str], dict[str, set[str] | None]]:
    """Derive collection list and per-collection asset filters from configuration mapping or sequence.

    Args:
        collections_config: Mapping of collection -> list of asset/channel keys,
            or sequence of collection names.

    Returns:
        A ``(collections, asset_filters)`` tuple.
    """
    if collections_config is None:
        return [], {}

    if isinstance(collections_config, Mapping):
        asset_filters: dict[str, set[str] | None] = {}
        for coll, vars_list in collections_config.items():
            if vars_list and "*" not in vars_list:
                asset_filters[coll] = set(str(v) for v in vars_list)
            else:
                asset_filters[coll] = None
        return list(collections_config.keys()), asset_filters

    collections = list(dict.fromkeys(collections_config))
    return collections, {coll: None for coll in collections}


@attrs.frozen
class ExtractionTask:
    """A serializable unit of extraction work.

    Attributes:
        id: Stable identifier generated by the task builder.
        assets: GeoDataFrame of source assets to read.
        job: Parent ``ExtractionJob`` that owns this task's extraction configuration.
        aoi: Optional task-specific AOI. When provided, the orchestrator uses this
            geometry instead of ``job.target_aoi`` to build the MajorTOM grid and
            index artifacts. This keeps the parent job immutable while allowing a
            task builder to split a job into smaller spatial chunks.
        grid_cells: Optional explicit list of MajorTOM grid cells this task is
            responsible for. When provided, the executor uses these cells directly
            instead of rediscovering them from the AOI. This is the normal case for
            tasks produced by ``build_grouped_tasks``.
        task_context: Optional metadata (e.g. ``chunk_id``, ``total_chunks``)
            carried with the task for tracing and logging. Grid cells are no longer
            stored here; use ``grid_cells`` instead.
    """

    id: str
    assets: GeoDataFrame[AssetSchema]
    job: ExtractionJob
    aoi: BaseGeometry | None = None
    grid_cells: Sequence[GridCell] | None = None
    task_context: dict[str, Any] = attrs.field(factory=dict)

    @property
    def uris(self) -> list[str]:
        """Source URIs derived from ``assets["href"]``."""
        return self.assets["href"].tolist()

    @property
    def bbox(self) -> tuple[float, float, float, float] | None:
        """WGS84 bounding box the reader should crop to, if any.

        When the task has explicit grid cells and ``job.grid_cells_margin`` is
        set, the returned bounds cover the expanded GeoBox of every cell so
        readers fetch enough source data to avoid cutting edge cells.

        Precedence:
            1. Expanded grid-cell GeoBoxes when ``grid_cells`` and
               ``grid_cells_margin`` are set.
            2. ``task.aoi.bounds`` when ``task.aoi`` is set.
            3. ``job.target_aoi.bounds`` when ``job.target_aoi`` is set.
            4. ``None``.
        """
        if self.grid_cells and self.job.resolution is not None:
            from aereo.spatial import reproject_geom

            expanded_boxes: list[BaseGeometry] = []
            for cell in self.grid_cells:
                gb = cell.to_geobox(
                    resolution=self.job.resolution,
                    margin=self.job.grid_cells_margin,
                )
                bb = gb.boundingbox
                utm_box = box(bb.left, bb.bottom, bb.right, bb.top)
                expanded_boxes.append(
                    reproject_geom(
                        utm_box,
                        src_epsg=str(gb.crs).lower(),
                        dst_epsg=WGS84_CRS,
                    )
                )
            return shapely.unary_union(expanded_boxes).bounds

        if self.aoi is not None:
            return self.aoi.bounds
        if self.job.effective_target_aoi is not None:
            return self.job.effective_target_aoi.bounds
        return None

    @property
    def collections(self) -> list[str]:
        """Unique collection identifiers present in ``assets["collection"]``."""
        if "collection" not in self.assets.columns:
            return []
        return sorted(self.assets["collection"].dropna().astype(str).unique().tolist())

    @property
    def datetime_range(self) -> tuple[datetime, datetime] | None:
        """Minimum start time and maximum end time across task assets."""
        start_time = None
        end_time = None
        if "start_time" in self.assets.columns:
            start_time = pd.to_datetime(self.assets["start_time"]).min().to_pydatetime()
        if "end_time" in self.assets.columns:
            end_time = pd.to_datetime(self.assets["end_time"]).max().to_pydatetime()
        if start_time is not None and end_time is not None:
            return start_time, end_time
        return None

    @property
    def stac_items(self) -> list[pystac.Item]:
        """Unique ``pystac.Item`` objects reconstructed from ``assets["stac_item"]``.

        Returns an empty list when the column is missing or contains only nulls.
        """
        if "stac_item" not in self.assets.columns:
            return []

        seen_ids: set[str] = set()
        items: list[pystac.Item] = []
        for raw in self.assets["stac_item"]:
            if raw is None:
                continue
            item = pystac.Item.from_dict(_to_native(raw))
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                items.append(item)
        return items

    @property
    def read(self) -> Reader:
        """Reader callable delegated to ``job``."""
        return self.job.read

    @property
    def write(self) -> Writer | None:
        """Writer callable delegated to ``job`` (may be ``None``)."""
        return self.job.write

    @property
    def output_uri(self) -> str:
        """Destination URI for extracted artifacts (delegated to ``job``)."""
        return self.job.output_uri

    @property
    def grid_dist(self) -> int:
        """Grid cell size in metres shared by all tasks in this run (delegated to ``job``)."""
        return self.job.grid_dist

    def __attrs_post_init__(self) -> None:
        """Validate task invariants after construction.

        Raises:
            ValueError: If assets is empty or assets have mixed native CRS.
        """
        if self.assets is None or len(self.assets) == 0:
            raise ValueError("assets cannot be empty")

        if any(col == "crs" for col in self.assets.columns):
            if bool(self.assets["crs"].isna().any()):
                raise ValueError(
                    "assets['crs'] contains null values. "
                    "Either populate crs for all assets or omit the column entirely."
                )
            unique_crs = self.assets["crs"].unique()
            if len(unique_crs) > 1:
                raise ValueError(
                    "All assets in an ExtractionTask must share the same native CRS, "
                    f"but found: {sorted(unique_crs)}."
                )

    def __repr__(self) -> str:
        n_assets = len(self.assets) if self.assets is not None else 0
        n_grid_cells = len(self.grid_cells) if self.grid_cells is not None else None
        return (
            f"{self.__class__.__name__}("
            f"id={self.id!r}, "
            f"n_assets={n_assets}, "
            f"n_grid_cells={n_grid_cells}, "
            f"read={self.read is not None}, "
            f"write={self.write is not None}, "
            f"output_uri='{self.output_uri}'"
            f")"
        )
