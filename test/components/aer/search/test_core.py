import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import geopandas as gpd
import pandas as pd
from pandera.errors import SchemaError
from shapely.geometry import Polygon

from aer.search import SearchQuery, SearchResultSchema
from aer.temporal import TimeRange
from aer.product_viirs_earthaccess import VNP02IMG_EA, VNP02MOD_EA
from aer.spectral_viirs import VIIRS_I1, VIIRS_M1


def test_schema_rejects_missing_columns():
    """Schema rejects a GeoDataFrame missing required columns."""
    gdf = gpd.GeoDataFrame(
        [{"product_name": "TEST", "granule_id": "123", "size_mb": 1.0}],
        geometry=[None],
    )

    with pytest.raises(SchemaError):
        SearchResultSchema.validate(gdf)


def test_schema_rejects_nulls_in_required_columns():
    """Schema rejects a GeoDataFrame if required columns contain nulls."""
    # Test each required column one by one
    for null_col in ["product_name", "granule_id", "start_time", "end_time"]:
        row = {
            "product_name": "TEST",
            "granule_id": "123",
            "start_time": pd.to_datetime("2023-01-01"),
            "end_time": pd.to_datetime("2023-01-02"),
        }
        # Set the one column to None (null)
        row[null_col] = None

        gdf = gpd.GeoDataFrame([row], geometry=[None])

        with pytest.raises(SchemaError):
            SearchResultSchema.validate(gdf)


def test_schema_allows_extra_columns():
    """Extra columns beyond the schema are preserved (strict=False)."""

    gdf = gpd.GeoDataFrame(
        [
            {
                "product_name": "VNP02IMG",
                "granule_id": "G123",
                "start_time": pd.to_datetime("2023-01-01"),
                "end_time": pd.to_datetime("2023-01-02"),
                "s3_url": "s3://bucket/key",
                "https_url": "https://example.com/key",
                "size_mb": 42.0,
                "my_custom_column": "extra_value",
                "another_custom": 999,
            }
        ],
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
    )

    gdf = SearchResultSchema.validate(gdf)

    # Required columns are present and validated
    assert "product_name" in gdf.columns
    assert "size_mb" in gdf.columns
    assert "geometry" in gdf.columns
    # Extra columns survive the validation
    assert "my_custom_column" in gdf.columns
    assert gdf.iloc[0]["my_custom_column"] == "extra_value"
    assert "another_custom" in gdf.columns
    assert gdf.iloc[0]["another_custom"] == 999


def test_schema_allows_null_geometry():
    """Geometry column can be None (e.g. GOES products without granule-level footprints)."""

    gdf = gpd.GeoDataFrame(
        [
            {
                "product_name": "ABI-L1b-RadF",
                "granule_id": "G999",
                "start_time": pd.to_datetime("2023-06-01"),
                "end_time": pd.to_datetime("2023-06-02"),
                "s3_url": "s3://goes-bucket/key",
                "https_url": "https://example.com/goes",
                "size_mb": 100.0,
            }
        ],
        geometry=[None],
    )
    gdf = SearchResultSchema.validate(gdf)
    assert not gdf.empty
    assert gdf.iloc[0]["geometry"] is None
    assert gdf.iloc[0]["product_name"] == "ABI-L1b-RadF"


def test_search_earthaccess_schema_validation():
    """Real-life test: mocked earthaccess granules pass through SearchResultSchema validation."""

    expected_poly = Polygon([(-10, -5), (10, -5), (10, 5), (-10, 5)])

    # Build a realistic mock granule mimicking what earthaccess.search_data returns
    mock_granule = MagicMock()
    mock_granule.__getitem__ = lambda self, key: {
        "meta": {
            "native-id": "VIIRS_NRT.A2023001.1030.002.2023001123456",
        },
        "umm": {
            "CollectionReference": {"ShortName": "VNP02IMG"},
            "TemporalExtent": {
                "RangeDateTime": {
                    "BeginningDateTime": "2023-01-01T10:30:00Z",
                    "EndingDateTime": "2023-01-01T10:36:00Z",
                }
            },
            "SpatialExtent": {
                "HorizontalSpatialDomain": {
                    "Geometry": {
                        "BoundingRectangles": [
                            {
                                "WestBoundingCoordinate": -10,
                                "SouthBoundingCoordinate": -5,
                                "EastBoundingCoordinate": 10,
                                "NorthBoundingCoordinate": 5,
                            }
                        ]
                    }
                }
            },
        },
    }[key]
    mock_granule.get = lambda key, default=None: {
        "meta": mock_granule["meta"],
        "umm": mock_granule["umm"],
    }.get(key, default)
    mock_granule.data_links = lambda access: (
        ["s3://nrt-bucket/VNP02IMG.A2023001.1030.002.nc"]
        if access == "direct"
        else ["https://ladsweb.modaps.eosdis.nasa.gov/VNP02IMG.A2023001.1030.002.nc"]
    )
    mock_granule.size = lambda: 256.7

    with patch(
        "aer.search_earthaccess.core.earthaccess.search_data",
        return_value=[mock_granule],
    ):
        from aer.plugin import plugin_registry

        # Load earthly plugins
        plugin_registry._ensure_loaded()
        plugin = plugin_registry.get("earthaccess")

        time_range = TimeRange(
            start=datetime(2023, 1, 1, 10, 0),
            end=datetime(2023, 1, 1, 12, 0),
        )
        query = SearchQuery(products=[VNP02IMG_EA], time_range=time_range)

        # Call the plugin directly
        gdf = plugin(query)

    # Validate the output structure
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty
    assert len(gdf) == 1
    assert gdf.iloc[0]["product_name"] == "VNP02IMG"
    assert gdf.iloc[0]["granule_id"] == "VIIRS_NRT.A2023001.1030.002.2023001123456"
    assert gdf.iloc[0]["s3_url"] == "s3://nrt-bucket/VNP02IMG.A2023001.1030.002.nc"
    assert gdf.iloc[0]["size_mb"] == pytest.approx(256.7)

    # Verify the geometry column has the expected polygon
    assert gdf.iloc[0]["geometry"].equals(expected_poly)

    # Validate schema compliance explicitly too
    SearchResultSchema.validate(gdf)


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
    )

    # 2. Invalid channel selection (M1 is not in VNP02IMG) raises ValueError
    with pytest.raises(ValueError, match="Requested channels .* must be a subset"):
        SearchQuery(
            products=[VNP02IMG_EA],
            time_range=time_range,
            channels=(VIIRS_M1,),
        )

    # 3. Multiple products: union of channels is allowed
    SearchQuery(
        products=[VNP02IMG_EA, VNP02MOD_EA],
        time_range=time_range,
        channels=(VIIRS_I1, VIIRS_M1),
    )

    # 4. None channels (default) is valid
    SearchQuery(products=[VNP02IMG_EA], time_range=time_range, channels=None)
