from typing import Any, Literal

import attrs
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoSeries
from structlog import get_logger

from aer.spatial import GridSpatialExtent
from aer.spectral import Product
from aer.temporal import TimeRange

logger = get_logger()


class SearchResultSchema(pa.DataFrameModel):  # type: ignore[misc]
    """Schema defining the minimum required columns for search results.

    Extra columns (e.g. ``grid_cells``) are allowed thanks to
    ``strict = False``.  Types are coerced so that, for example, a plugin
    returning ``size_mb`` as an integer will have it automatically cast to
    ``float``.

    The ``geometry`` column holds the granule footprint polygon (nullable
    because some products like GOES may not carry granule-level geometry).
    """

    product_name: Series[pa.String] = pa.Field(nullable=True)
    granule_id: Series[pa.String] = pa.Field(nullable=True)
    concept_id: Series[pa.String] = pa.Field(nullable=True)
    start_time: Series[pa.DateTime] = pa.Field(nullable=True)
    end_time: Series[pa.DateTime] = pa.Field(nullable=True)
    s3_url: Series[pa.String] = pa.Field(nullable=True)
    https_url: Series[pa.String] = pa.Field(nullable=True)
    size_mb: Series[float] = pa.Field(nullable=True)
    geometry: GeoSeries[Any] = pa.Field(nullable=True)

    class Config:
        strict = False
        coerce = True


CellOverlapMode = Literal["contains", "intersects"]


@attrs.define(frozen=True, slots=True, kw_only=True)
class SearchQuery:
    """A unified input query for search plugins."""

    products: list[Product]
    time_range: TimeRange
    spatial_extent: GridSpatialExtent | None = None
    cell_overlap_mode: CellOverlapMode = "contains"
    options: dict[str, Any] = attrs.field(factory=dict)
