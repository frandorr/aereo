from typing import Any, Literal

import attrs
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

from aer.spatial import GridCell, GridSpatialExtent, GridSchema
from aer.spectral import Channel, Product, Satellite
from aer.temporal import TimeRange
from typing import Protocol

logger = get_logger()

CellOverlapMode = Literal["contains", "intersects"]


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

    class Config:
        strict = False
        coerce = True

    @classmethod
    def from_grid_cell(
        cls, cell: "GridCell", channel: "Channel", **base_fields
    ) -> dict[str, Any]:
        """Create a row dict from a GridCell and Channel."""
        return {
            **base_fields,
            "row": cell.row,
            "col": cell.col,
            "epsg": cell.epsg,
            "cell_bounds": cell.bounds,
            "channel": channel,
        }

    @classmethod
    def to_grid_cell(cls, row: dict[str, Any], dist: int = 100) -> "GridCell":
        """Reconstruct a GridCell from a row."""
        return GridCell(
            row=row["row"],
            col=row["col"],
            dist=dist,
            bounds=row["cell_bounds"],
            epsg=row["epsg"],
        )


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
