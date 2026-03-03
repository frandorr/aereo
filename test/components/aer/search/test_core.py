import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import geopandas as gpd
import pandas as pd
from pandera.errors import SchemaError
from shapely.geometry import Polygon

from aer.search import SearchMethod, SearchResultSchema
from aer.temporal import TimeRange
from aer.spectral import VNP02IMG


def test_searchmethod_registry():
    """Test the SearchMethod registry and basic plugin behavior."""

    # Create a dummy search function
    def dummy_search(
        products,
        time_range,
        spatial_extent=None,
        cell_overlap_mode="contains",
        **kwargs,
    ):
        return gpd.GeoDataFrame(
            [
                {
                    "product_name": products[0].name,
                    "granule_id": "dummy_123",
                    "concept_id": "C123",
                    "start_time": pd.to_datetime("2023-01-01T00:00:00Z"),
                    "end_time": pd.to_datetime("2023-01-01T01:00:00Z"),
                    "s3_url": "s3://dummy",
                    "https_url": "https://dummy",
                    "size_mb": 1.0,
                    "dummy_flag": True,
                }
            ],
            geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        )

    # 1. Register a new plugin
    dummy_plugin = SearchMethod.register("dummy_plugin", dummy_search)
    assert dummy_plugin.name == "dummy_plugin"

    # 2. Retrieve plugin
    retrieved = SearchMethod.get("dummy_plugin")
    assert retrieved is dummy_plugin

    # 3. Double registering the exact same function returns the existing instance
    dummy_plugin_2 = SearchMethod.register("dummy_plugin", dummy_search)
    assert dummy_plugin_2 is dummy_plugin

    # 4. Registering a different function with the same name raises ValueError
    def dummy_search_other(*args, **kwargs):
        pass

    with pytest.raises(
        ValueError, match="already registered with a different function"
    ):
        SearchMethod.register("dummy_plugin", dummy_search_other)

    # 5. Check 'all' contains our new plugin
    all_plugins = SearchMethod.all()
    assert dummy_plugin in all_plugins

    # Note: earthaccess is normally loaded as an entrypoint, but may not be
    # present in purely isolated test environments unless specifically installed.

    # 6. Verify missing plugin raises KeyError
    with pytest.raises(KeyError, match="not registered"):
        SearchMethod.get("non_existent_plugin")

    # 7. Execution through the SearchMethod class (calls __call__)
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    gdf = dummy_plugin(products=[VNP02IMG], time_range=time_range)
    assert not gdf.empty
    assert gdf.iloc[0]["product_name"] == VNP02IMG.name
    assert bool(gdf.iloc[0]["dummy_flag"])
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert "geometry" in gdf.columns


def test_searchmethod_validation_rejects_missing_columns():
    """SearchMethod rejects a GeoDataFrame missing required schema columns."""

    def invalid_search(*args, **kwargs):
        # Missing most required columns
        return gpd.GeoDataFrame(
            [{"product_name": "TEST", "granule_id": "123", "size_mb": 1.0}],
            geometry=[None],
        )

    invalid_plugin = SearchMethod.register("invalid_plugin", invalid_search)

    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )

    with pytest.raises(SchemaError):
        invalid_plugin(products=[VNP02IMG], time_range=time_range)


def test_schema_allows_extra_columns():
    """Extra columns beyond the schema are preserved (strict=False)."""

    def search_with_extras(*args, **kwargs):
        return gpd.GeoDataFrame(
            [
                {
                    "product_name": "VNP02IMG",
                    "granule_id": "G123",
                    "concept_id": "C123",
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

    plugin = SearchMethod.register("extras_plugin", search_with_extras)
    time_range = TimeRange(start=datetime(2023, 1, 1), end=datetime(2023, 1, 2))
    gdf = plugin(products=[VNP02IMG], time_range=time_range)

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

    def search_no_geom(*args, **kwargs):
        return gpd.GeoDataFrame(
            [
                {
                    "product_name": "ABI-L1b-RadF",
                    "granule_id": "G999",
                    "concept_id": "C999",
                    "start_time": pd.to_datetime("2023-06-01"),
                    "end_time": pd.to_datetime("2023-06-02"),
                    "s3_url": "s3://goes-bucket/key",
                    "https_url": "https://example.com/goes",
                    "size_mb": 100.0,
                }
            ],
            geometry=[None],
        )

    plugin = SearchMethod.register("null_geom_plugin", search_no_geom)
    time_range = TimeRange(start=datetime(2023, 6, 1), end=datetime(2023, 6, 2))
    gdf = plugin(products=[VNP02IMG], time_range=time_range)

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
            "concept-id": "G1234567890-LPDAAC_ECS",
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
        from aer.search_earthaccess.core import search_earthaccess

        # Register if not already
        try:
            plugin = SearchMethod.register(
                "earthaccess_schema_test", search_earthaccess
            )
        except ValueError:
            plugin = SearchMethod.get("earthaccess_schema_test")

        time_range = TimeRange(
            start=datetime(2023, 1, 1, 10, 0),
            end=datetime(2023, 1, 1, 12, 0),
        )

        # This calls __call__ which wraps result in GeoDataFrame[SearchResultSchema]
        gdf = plugin(products=[VNP02IMG], time_range=time_range)

    # Validate the output structure
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert not gdf.empty
    assert len(gdf) == 1
    assert gdf.iloc[0]["product_name"] == "VNP02IMG"
    assert gdf.iloc[0]["granule_id"] == "VIIRS_NRT.A2023001.1030.002.2023001123456"
    assert gdf.iloc[0]["concept_id"] == "G1234567890-LPDAAC_ECS"
    assert gdf.iloc[0]["s3_url"] == "s3://nrt-bucket/VNP02IMG.A2023001.1030.002.nc"
    assert gdf.iloc[0]["size_mb"] == pytest.approx(256.7)

    # Verify the geometry column has the expected polygon
    assert gdf.iloc[0]["geometry"].equals(expected_poly)

    # Validate schema compliance explicitly too
    SearchResultSchema.validate(gdf)
