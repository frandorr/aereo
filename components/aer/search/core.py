from datetime import datetime
from typing import Any, Literal

import attrs
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aer.spatial import GridCell, GridSpatialExtent, GridSchema, GridRow
from aer.spectral import Channel, Product, Satellite
from aer.temporal import TimeRange
from typing import Protocol
from shapely.geometry import Polygon
import geopandas as gpd

logger = get_logger()

CellOverlapMode = Literal["contains", "intersects"]


@attrs.frozen
class SearchResult:
    """A typed representation of a single search result record.

    Matches the fields defined in SearchResultSchema and GridSchema.
    """

    unique_id: str
    product_id: str
    granule_id: str
    start_time: datetime
    end_time: datetime
    overlap_mode: str
    channel: Channel | None = None
    s3_url: str | None = None
    https_url: str | None = None
    size_mb: float | None = None

    # Grid fields
    grid: GridRow | None = None

    @property
    def grid_cell(self) -> "GridCell":
        """Reconstruct a GridCell from this SearchResult."""
        if not self.grid:
            raise ValueError("SearchResult is missing grid row data.")
        return self.grid.grid_cell

    @classmethod
    def from_gdf(cls, gdf: GeoDataFrame) -> list["SearchResult"]:
        """Convert a SearchResult GeoDataFrame to a list of SearchResult objects."""
        grid_cols = [
            "name",
            "row",
            "col",
            "row_idx",
            "col_idx",
            "utm_zone",
            "epsg",
            "dist",
            "geometry",
            "cell_bounds",
        ]
        results = []
        for row in gdf.to_dict("records"):
            # Separate grid fields from base fields
            grid_data = {k: row.pop(k) for k in grid_cols if k in row}
            base_data = row
            grid_obj = GridRow(**grid_data) if grid_data else None
            results.append(cls(grid=grid_obj, **base_data))
        return results

    @classmethod
    def to_gdf(
        cls, results: list["SearchResult"]
    ) -> GeoDataFrame["SearchResultSchema"]:
        """Convert a list of SearchResult objects back to a GeoDataFrame."""
        import geopandas as gpd

        records = []
        for r in results:
            data = attrs.asdict(r, filter=lambda attr, value: attr.name != "grid")
            if r.grid:
                data.update(attrs.asdict(r.grid))
            records.append(data)

        gdf = gpd.GeoDataFrame(records)
        if not gdf.empty:
            # GridSchema expects both geometry and cell_bounds as GeoSeries
            # and SearchResultSchema inherits from it.
            if "geometry" in gdf.columns:
                gdf = gdf.set_geometry("geometry")
        return SearchResultSchema.validate(gdf)


class SearchResultSchema(GridSchema):
    """Schema defining search results with one row per (granule, grid cell, channel).

    Each row represents a single file intersecting a single grid cell for a single
    channel. This exploded format allows direct iteration without unpacking nested
    structures.
    """

    unique_id: Series[pa.String] = pa.Field(nullable=False)
    product_id: Series[pa.String] = pa.Field(nullable=False)
    granule_id: Series[pa.String] = pa.Field(nullable=False)
    start_time: Series[pa.DateTime] = pa.Field(nullable=False)
    end_time: Series[pa.DateTime] = pa.Field(nullable=False)
    channel: Series[pa.Object] = pa.Field(nullable=True)
    overlap_mode: Series[pa.String] = pa.Field(nullable=False)
    s3_url: Series[pa.String] = pa.Field(nullable=True)
    https_url: Series[pa.String] = pa.Field(nullable=True)
    size_mb: Series[float] = pa.Field(nullable=True)
    dist: Series[pa.Int64] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class SearchPlugin(Protocol):
    """Protocol for search plugins."""

    def search(self, query: "SearchQuery") -> GeoDataFrame["SearchResultSchema"]:
        """Search for data given a SearchQuery."""
        ...


@attrs.define(frozen=True, slots=True, kw_only=True)
class SearchQuery:
    """A unified input query for search plugins."""

    products: list[Product]
    time_range: TimeRange
    spatial_extent: GridSpatialExtent
    satellites: tuple[Satellite, ...] = attrs.field()
    channels: tuple[Channel, ...] = attrs.field()
    cell_overlap_mode: CellOverlapMode = "contains"
    options: dict[str, Any] = attrs.field(factory=dict)

    @channels.validator
    def _validate_channels(self, attribute: Any, value: tuple[Channel, ...]) -> None:
        allowed_channels = {c for p in self.products for c in p.channels}
        if not set(value).issubset(allowed_channels):
            raise ValueError(
                f"Requested channels {value} must be a subset of the channels available "
                f"in the provided products: {allowed_channels}"
            )

    @satellites.validator
    def _validate_satellites(
        self, attribute: Any, value: tuple[Satellite, ...]
    ) -> None:
        allowed_satellites = {s for p in self.products for s in p.supported_satellites}
        if not set(value).issubset(allowed_satellites):
            raise ValueError(
                f"Requested satellites {value} must be a subset of the satellites available "
                f"in the provided products: {allowed_satellites}"
            )


def serialize_search_results(
    gdf: GeoDataFrame["SearchResultSchema"],
) -> gpd.GeoDataFrame:
    """Prepare SearchResultSchema GeoDataFrame for Parquet storage by serializing object columns.

    The 'channel' column containing Channel objects is converted to channel IDs (strings),
    which can be restored later using deserialize_search_results.
    """
    df = gdf.copy()
    if "channel" in df.columns:
        df["channel"] = df["channel"].apply(
            lambda x: x.c_id if hasattr(x, "c_id") else x
        )
    return df


def deserialize_search_results(
    gdf: gpd.GeoDataFrame,
) -> GeoDataFrame["SearchResultSchema"]:
    """Restore SearchResultSchema GeoDataFrame from Parquet storage by deserializing object columns.

    The 'channel' column containing channel IDs (strings) is converted back to Channel objects
    using the product_id and c_id.
    """
    df = gdf.copy()
    if "channel" in df.columns and "product_id" in df.columns:

        def restore_channel(row):
            p_id = row["product_id"]
            c_id = row["channel"]
            if not isinstance(c_id, str):
                return c_id
            try:
                product = Product.get(p_id)
                return next((c for c in product.channels if c.c_id == c_id), None)
            except (KeyError, StopIteration):
                return None

        df["channel"] = df.apply(restore_channel, axis=1)

    return SearchResultSchema.validate(df)
