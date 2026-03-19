from typing import Any, Protocol

import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoDataFrame

from aer.search.core import SearchResultSchema


class ExtractedResultSchema(SearchResultSchema):
    """Schema for extracted results, extending the search result metadata."""

    reprojected_path: Series[pa.String] = pa.Field(nullable=False)
    resolution: Series[float] = pa.Field(nullable=False)


class ExtractPlugin(Protocol):
    """Protocol for extract plugins."""

    def extract(
        self,
        gdf: GeoDataFrame[SearchResultSchema],
        output_dir: str,
        **options: Any,
    ) -> GeoDataFrame["ExtractedResultSchema"]:
        """Extract data from a search result to a standardized grid."""
        ...
