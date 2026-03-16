from typing import Any, Literal

import attrs
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoDataFrame, GeoSeries
from structlog import get_logger

from aer.spatial import GridSpatialExtent
from aer.spectral import Channel, Product, Satellite
from aer.temporal import TimeRange
from typing import Protocol

logger = get_logger()

CellOverlapMode = Literal["contains", "intersects"]


class SearchResultSchema(pa.DataFrameModel):  # type: ignore[misc]
    """Schema defining the minimum required columns for search results.

    Extra columns (e.g. ``grid_cells``, ``channels``) are allowed thanks to
    ``strict = False``.  Types are coerced so that, for example, a plugin
    returning ``size_mb`` as an integer will have it automatically cast to
    ``float``.

    The ``geometry`` column holds the granule footprint polygon (nullable
    because some products like GOES may not carry granule-level geometry).

    The ``channels`` column holds a tuple of :class:`Channel` objects
    indicating which spectral bands the row covers.  Downstream extraction
    plugins use this to know which bands to read from the file.
    """

    product_name: Series[pa.String] = pa.Field(nullable=False)
    granule_id: Series[pa.String] = pa.Field(nullable=False)
    start_time: Series[pa.DateTime] = pa.Field(nullable=False)
    end_time: Series[pa.DateTime] = pa.Field(nullable=False)
    s3_url: Series[pa.String] = pa.Field(nullable=True)
    https_url: Series[pa.String] = pa.Field(nullable=True)
    size_mb: Series[float] = pa.Field(nullable=True)
    geometry: GeoSeries[Any] = pa.Field(nullable=True)
    overlapping_spatial_extent: Series[Any] = pa.Field(nullable=True)
    input_spatial_extent: Series[Any] = pa.Field(nullable=True)
    cell_overlap_mode: Series[pa.String] = pa.Field(nullable=False)

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
