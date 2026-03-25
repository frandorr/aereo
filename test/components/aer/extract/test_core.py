from datetime import datetime

import geopandas as gpd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Point

from aer.extract.core import ExtractedResultSchema, ExtractPlugin


def test_extracted_result_schema() -> None:
    """Test that a valid GeoDataFrame passes ExtractedResultSchema validation."""
    from shapely.geometry import Polygon

    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    data = {
        "unique_id": ["U1"],
        "product_id": ["test_product"],
        "granule_id": ["granule_1"],
        "start_time": [datetime(2025, 1, 1)],
        "end_time": [datetime(2025, 1, 2)],
        "s3_url": ["s3://bucket/test.nc"],
        "https_url": ["https://bucket/test.nc"],
        "size_mb": [10.5],
        "name": ["10U_20R"],
        "row": ["10U"],
        "col": ["20R"],
        "row_idx": [0],
        "col_idx": [0],
        "utm_zone": ["31N"],
        "epsg": ["EPSG:32615"],
        "dist": [100],
        "cell_bounds": [test_geom],
        "channel": ["I1"],
        "overlap_mode": ["contains"],
        "reprojected_path": ["/local/path/to/extracted.tif"],
        "resolution": [1000.0],
    }
    gdf = gpd.GeoDataFrame(data, geometry=[Point(0, 0)])

    # This should pass without raising pa.errors.SchemaError
    validated_gdf: GeoDataFrame[ExtractedResultSchema] = ExtractedResultSchema.validate(
        gdf
    )

    assert "reprojected_path" in validated_gdf.columns
    assert "resolution" in validated_gdf.columns
    assert validated_gdf.iloc[0]["resolution"] == 1000.0


def test_extract_plugin_protocol() -> None:
    """Test that the ExtractPlugin Protocol can be implemented."""
    from aer.extract.core import ExtractionTask

    class DummyExtractPlugin:
        def extract(
            self,
            task: ExtractionTask,
        ) -> ExtractionTask:
            """Dummy implementation that returns the task with updated status."""
            return task

    # The key verification: DummyExtractPlugin can be assigned to ExtractPlugin
    # This is the structural subtyping check that Protocol provides
    plugin: ExtractPlugin = DummyExtractPlugin()
    assert hasattr(plugin, "extract")
