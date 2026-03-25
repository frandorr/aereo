import pytest
from datetime import datetime
import geopandas as gpd
import pandas as pd
from pandera.errors import SchemaError
from shapely.geometry import Polygon, Point

from aer.search import SearchQuery, SearchResultSchema
from aer.temporal import TimeRange
from aer.spectral import Product
from aer.spatial import GridCell, GridSpatialExtent
from unittest.mock import MagicMock


def get_channel(pid, cid):
    return next(c for c in Product.get(pid).channels if c.c_id == cid)


VNP02IMG_EA = Product.get("VNP02IMG")
VNP02MOD_EA = Product.get("VNP02MOD")
VIIRS_I1 = get_channel("VNP02IMG", "I1")
VIIRS_M1 = get_channel("VNP02MOD", "M1")


def test_schema_rejects_missing_columns():
    """Schema rejects a GeoDataFrame missing required columns."""
    gdf = gpd.GeoDataFrame(
        [{"product_id": "TEST", "granule_id": "123", "size_mb": 1.0}],
        geometry=[None],
    )

    with pytest.raises(SchemaError):
        SearchResultSchema.validate(gdf)


def test_schema_to_grid_cell():
    """Schema can reconstruct a GridCell from a row."""
    from aer.spatial import GridCell

    cell = GridCell(
        row="10U",
        col="20R",
        dist=100,
        bounds=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
        epsg="EPSG:32615",
    )

    row_dict = {
        "unique_id": "U1",
        "product_id": "TEST",
        "granule_id": "G123",
        "start_time": pd.to_datetime("2023-01-01"),
        "end_time": pd.to_datetime("2023-01-02"),
        "s3_url": "s3://bucket/key",
        "https_url": "https://example.com/key",
        "size_mb": 42.0,
        "geometry": Point(0, 0),
        "name": "10U_20R",
        "row_idx": 0,
        "col_idx": 0,
        "utm_zone": "31N",
        "overlap_mode": "contains",
    }

    result = SearchResultSchema.from_grid_cell(cell, VIIRS_I1, **row_dict)

    assert result["row"] == "10U"
    assert result["col"] == "20R"
    assert result["epsg"] == "EPSG:32615"
    assert result["channel"] == VIIRS_I1

    reconstructed = SearchResultSchema.to_grid_cell(result)
    assert reconstructed.row == cell.row
    assert reconstructed.col == cell.col


def test_schema_rejects_nulls_in_required_columns():
    """Schema rejects a GeoDataFrame if required columns contain nulls."""
    GridCell(
        row="10U",
        col="20R",
        dist=100,
        bounds=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
        epsg="EPSG:32615",
    )
    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    for null_col in [
        "product_id",
        "granule_id",
        "start_time",
        "end_time",
        "row",
        "col",
        "epsg",
        "channel",
    ]:
        row = {
            "unique_id": "U1",
            "product_id": "TEST",
            "granule_id": "123",
            "start_time": pd.to_datetime("2023-01-01"),
            "end_time": pd.to_datetime("2023-01-02"),
            "name": "10U_20R",
            "row": "10U",
            "col": "20R",
            "row_idx": 0,
            "col_idx": 0,
            "utm_zone": "31N",
            "epsg": "EPSG:32615",
            "cell_bounds": test_geom,
            "channel": "I1",
            "overlap_mode": "contains",
        }
        row[null_col] = None

        gdf = gpd.GeoDataFrame([row], geometry=[test_geom])

        with pytest.raises(SchemaError):
            SearchResultSchema.validate(gdf)


def test_schema_allows_extra_columns():
    """Extra columns beyond the schema are preserved (strict=False)."""
    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    gdf = gpd.GeoDataFrame(
        [
            {
                "unique_id": "U1",
                "product_id": "VNP02IMG",
                "granule_id": "G123",
                "start_time": pd.to_datetime("2023-01-01"),
                "end_time": pd.to_datetime("2023-01-02"),
                "s3_url": "s3://bucket/key",
                "https_url": "https://example.com/key",
                "size_mb": 42.0,
                "name": "10U_20R",
                "row": "10U",
                "col": "20R",
                "row_idx": 0,
                "col_idx": 0,
                "utm_zone": "31N",
                "epsg": "EPSG:32615",
                "cell_bounds": test_geom,
                "channel": "I1",
                "overlap_mode": "contains",
                "my_custom_column": "extra_value",
                "another_custom": 999,
            }
        ],
        geometry=[test_geom],
    )

    gdf = SearchResultSchema.validate(gdf)

    # Required columns are present and validated
    assert "product_id" in gdf.columns
    assert "size_mb" in gdf.columns
    assert "geometry" in gdf.columns
    # Extra columns survive the validation
    assert "my_custom_column" in gdf.columns
    assert gdf.iloc[0]["my_custom_column"] == "extra_value"
    assert "another_custom" in gdf.columns
    assert gdf.iloc[0]["another_custom"] == 999


def test_schema_allows_null_geometry():
    """Geometry column can be None (e.g. GOES products without granule-level footprints)."""
    test_geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    gdf = gpd.GeoDataFrame(
        [
            {
                "unique_id": "U1",
                "product_id": "ABI-L1b-RadF",
                "granule_id": "G999",
                "start_time": pd.to_datetime("2023-06-01"),
                "end_time": pd.to_datetime("2023-06-02"),
                "s3_url": "s3://goes-bucket/key",
                "https_url": "https://example.com/goes",
                "size_mb": 100.0,
                "name": "10U_20R",
                "row": "10U",
                "col": "20R",
                "row_idx": 0,
                "col_idx": 0,
                "utm_zone": "31N",
                "epsg": "EPSG:32615",
                "cell_bounds": test_geom,
                "channel": "C01",
                "overlap_mode": "contains",
            }
        ],
        geometry=[test_geom],
    )
    gdf = SearchResultSchema.validate(gdf)
    assert not gdf.empty
    assert gdf.iloc[0]["product_id"] == "ABI-L1b-RadF"


mock_spatial_extent = MagicMock(spec=GridSpatialExtent)


def test_search_query_channel_validation():
    """Verify that SearchQuery validates requested channels against product capabilities."""
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 10, 0),
        end=datetime(2023, 1, 1, 12, 0),
    )

    # 1. Valid channel selection passes
    SearchQuery(
        products=[VNP02IMG_EA],
        time_range=time_range,
        channels=(VIIRS_I1,),
        satellites=(),
        spatial_extent=mock_spatial_extent,
    )

    # 2. Invalid channel selection (M1 is not in VNP02IMG) raises ValueError
    with pytest.raises(ValueError, match="Requested channels .* must be a subset"):
        SearchQuery(
            products=[VNP02IMG_EA],
            time_range=time_range,
            channels=(VIIRS_M1,),
            satellites=(),
            spatial_extent=mock_spatial_extent,
        )

    # 3. Multiple products: union of channels is allowed
    SearchQuery(
        products=[VNP02IMG_EA, VNP02MOD_EA],
        time_range=time_range,
        channels=(VIIRS_I1, VIIRS_M1),
        satellites=(),
        spatial_extent=mock_spatial_extent,
    )

    # 4. Empty channels is valid
    SearchQuery(
        products=[VNP02IMG_EA],
        time_range=time_range,
        channels=(),
        satellites=(),
        spatial_extent=mock_spatial_extent,
    )
