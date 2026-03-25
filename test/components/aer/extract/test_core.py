from datetime import datetime
from typing import Any

import geopandas as gpd
import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Point

from aer.extract.core import ExtractedResultSchema, ExtractPlugin
from aer.search.core import SearchResultSchema


def test_extracted_result_schema() -> None:
    """Test that a valid GeoDataFrame passes ExtractedResultSchema validation."""
    from shapely.geometry import Polygon

    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    data = {
        "product_name": ["test_product"],
        "granule_id": ["granule_1"],
        "start_time": [datetime(2025, 1, 1)],
        "end_time": [datetime(2025, 1, 2)],
        "s3_url": ["s3://bucket/test.nc"],
        "https_url": ["https://bucket/test.nc"],
        "size_mb": [10.5],
        "geometry": [Point(0, 0)],
        "cell_row": ["10U"],
        "cell_col": ["20R"],
        "cell_dist": [100],
        "cell_epsg": ["EPSG:32615"],
        "cell_bounds": [test_geom],
        "channel_name": ["I1"],
        "cell_overlap_mode": ["contains"],
        "reprojected_path": ["/local/path/to/extracted.tif"],
        "resolution": [1000.0],
    }
    gdf = gpd.GeoDataFrame(data, geometry="geometry")

    # This should pass without raising pa.errors.SchemaError
    validated_gdf: GeoDataFrame[ExtractedResultSchema] = ExtractedResultSchema.validate(
        gdf
    )

    assert "reprojected_path" in validated_gdf.columns
    assert "resolution" in validated_gdf.columns
    assert validated_gdf.iloc[0]["resolution"] == 1000.0


def test_extract_plugin_protocol() -> None:
    """Test that the ExtractPlugin Protocol can be implemented."""

    class DummyExtractPlugin:
        def extract(
            self,
            gdf: GeoDataFrame[SearchResultSchema],
            output_dir: str,
            **options: Any,
        ) -> GeoDataFrame[ExtractedResultSchema]:
            return pd.DataFrame()

    plugin: ExtractPlugin = DummyExtractPlugin()
    assert hasattr(plugin, "extract")
