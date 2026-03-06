import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import geopandas as gpd
from shapely.geometry import Polygon

from aer.search import SearchQuery
from aer.search_earthaccess import search_earthaccess
from aer.search_earthaccess.core import _parse_umm_polygon
from aer.temporal import TimeRange
from aer.product_viirs_earthaccess import VNP02IMG_EA
from aer.product_modis_earthaccess import MODIS_02QKM_EA
from aer.spatial import GridCell, GridSpatialExtent, GridDefinition

GRID_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4] / "components" / "aer" / "spatial"
)


def test_search_earthaccess_empty():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    with patch("aer.search_earthaccess.core.earthaccess.search_data") as mock_search:
        mock_search.return_value = []
        query = SearchQuery(products=[VNP02IMG_EA], time_range=time_range)
        gdf = search_earthaccess(query)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert gdf.empty
        assert "product_name" in gdf.columns
        assert "geometry" in gdf.columns
        mock_search.assert_called_once()
        kwargs = mock_search.call_args.kwargs
        assert kwargs["short_name"] == [VNP02IMG_EA.name]
        assert kwargs["temporal"] == ("2023-01-01 00:00:00", "2023-01-01 01:00:00")


def test_search_earthaccess_results():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    with patch("aer.search_earthaccess.core.earthaccess.search_data") as mock_search:
        granule = MagicMock()
        granule.get.side_effect = lambda k, d=None: {
            "meta": {"native-id": "123", "concept-id": "C123"},
            "umm": {
                "CollectionReference": {"ShortName": VNP02IMG_EA.name},
                "TemporalExtent": {
                    "RangeDateTime": {
                        "BeginningDateTime": "2023-01-01T00:05:00Z",
                        "EndingDateTime": "2023-01-01T00:10:00Z",
                    }
                },
            },
        }.get(k, d)
        granule.data_links.side_effect = lambda access="direct": (
            ["s3://bucket/test.nc"]
            if access == "direct"
            else ["https://bucket/test.nc"]
        )
        granule.size.return_value = 15.5

        mock_search.return_value = [granule]

        query = SearchQuery(products=[VNP02IMG_EA], time_range=time_range)
        gdf = search_earthaccess(query)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert not gdf.empty
        assert len(gdf) == 1
        assert gdf.iloc[0]["product_name"] == VNP02IMG_EA.name
        assert gdf.iloc[0]["s3_url"] == "s3://bucket/test.nc"
        assert gdf.iloc[0]["https_url"] == "https://bucket/test.nc"
        assert gdf.iloc[0]["size_mb"] == 15.5
        # Geometry is None because mock has no SpatialExtent in UMM
        assert gdf.iloc[0]["geometry"] is None


@pytest.mark.slow
def test_search_earthaccess_real_vnp02img():
    # A known timeframe where VIIRS data should exist globally.
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 2, 0)
    )
    query = SearchQuery(
        products=[VNP02IMG_EA], time_range=time_range, options={"count": 10}
    )
    df = search_earthaccess(query)

    assert not df.empty, (
        f"Expected non-empty results for {VNP02IMG_EA.name} over {time_range}"
    )
    assert "product_name" in df.columns
    assert "s3_url" in df.columns
    assert df.iloc[0]["product_name"] == VNP02IMG_EA.name


@pytest.mark.slow
def test_search_earthaccess_real_modis():
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 2, 0)
    )
    query = SearchQuery(
        products=[MODIS_02QKM_EA], time_range=time_range, options={"count": 10}
    )
    df = search_earthaccess(query)

    assert not df.empty, (
        f"Expected non-empty results for {MODIS_02QKM_EA.name} over {time_range}"
    )
    assert "product_name" in df.columns
    assert "s3_url" in df.columns
    assert df.iloc[0]["product_name"] == MODIS_02QKM_EA.name


@pytest.mark.slow
def test_search_earthaccess_real_multiple():
    from aer.product_viirs_earthaccess import VNP03IMG_EA

    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 1, 0)
    )
    query = SearchQuery(
        products=[VNP02IMG_EA, VNP03IMG_EA],
        time_range=time_range,
        options={"count": 10},
    )
    df = search_earthaccess(query)

    assert not df.empty, (
        f"Expected non-empty results for multiple products over {time_range}"
    )
    assert "product_name" in df.columns
    pnames = set(df["product_name"].unique())
    assert VNP02IMG_EA.name in pnames
    assert VNP03IMG_EA.name in pnames


@pytest.mark.slow
def test_search_earthaccess_real_multiple_constellations():
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 1, 0)
    )
    # Query across VIIRS (VNP02IMG_EA) and MODIS (MODIS_02QKM_EA)
    query = SearchQuery(
        products=[VNP02IMG_EA, MODIS_02QKM_EA],
        time_range=time_range,
        options={"count": 10},
    )
    df = search_earthaccess(query)

    assert not df.empty, (
        f"Expected non-empty results for multiple constellations over {time_range}"
    )
    assert "product_name" in df.columns
    pnames = set(df["product_name"].unique())
    assert VNP02IMG_EA.name in pnames, f"Expected to find {VNP02IMG_EA.name} in results"
    assert MODIS_02QKM_EA.name in pnames, (
        f"Expected to find {MODIS_02QKM_EA.name} in results"
    )


def test_search_earthaccess_with_spatial_extent():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )

    # Create two GridCells representing Spain area
    cell1 = GridCell(
        row="R1",
        col="C1",
        dist=10,
        bounds=Polygon([(-9, 36), (-5, 36), (-5, 40), (-9, 40)]),
        epsg="4326",
    )
    cell2 = GridCell(
        row="R1",
        col="C2",
        dist=10,
        bounds=Polygon([(-5, 36), (-1, 36), (-1, 40), (-5, 40)]),
        epsg="4326",
    )
    spatial_extent = GridSpatialExtent(frozenset([cell1, cell2]))

    with patch("aer.search_earthaccess.core.earthaccess.search_data") as mock_search:
        # Mocking the granule return
        granule = MagicMock()
        granule.get.side_effect = lambda k, d=None: {
            "meta": {"native-id": "123", "concept-id": "C123"},
            "umm": {
                "CollectionReference": {"ShortName": VNP02IMG_EA.name},
                "TemporalExtent": {
                    "RangeDateTime": {
                        "BeginningDateTime": "2023-01-01T00:05:00Z",
                        "EndingDateTime": "2023-01-01T00:10:00Z",
                    }
                },
                "SpatialExtent": {
                    "HorizontalSpatialDomain": {
                        "Geometry": {
                            # This box covers Spain entirely (-10 to 0 Long, 35 to 45 Lat)
                            "BoundingRectangles": [
                                {
                                    "WestBoundingCoordinate": -10.0,
                                    "EastBoundingCoordinate": 0.0,
                                    "SouthBoundingCoordinate": 35.0,
                                    "NorthBoundingCoordinate": 45.0,
                                }
                            ]
                        }
                    }
                },
            },
        }.get(k, d)

        granule.data_links.side_effect = lambda access="direct": (
            ["s3://doc"] if access == "direct" else ["https://doc"]
        )
        granule.size.return_value = 15.5
        mock_search.return_value = [granule]

        query = SearchQuery(
            products=[VNP02IMG_EA], time_range=time_range, spatial_extent=spatial_extent
        )
        df = search_earthaccess(query)

        # 1. Assert EarthAccess kwargs received the correct `bounding_box`
        # Total cell bounds is: min_lon=-9, max_lon=-1, min_lat=36, max_lat=40
        mock_search.assert_called_once()
        kwargs = mock_search.call_args.kwargs
        assert "bounding_box" in kwargs
        assert kwargs["bounding_box"] == (-9.0, 36.0, -1.0, 40.0)

        # 2. Assert dataframe contains "grid_cells"
        assert not df.empty
        assert "grid_cells" in df.columns
        assert isinstance(df.iloc[0]["grid_cells"], list)
        assert set(df.iloc[0]["grid_cells"]) == {"R1_C1", "R1_C2"}


def test_search_earthaccess_spatial_extent_and_bounding_box_raises():
    """Passing both spatial_extent and bounding_box should raise ValueError."""
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    cell = GridCell(
        row="R1",
        col="C1",
        dist=10,
        bounds=Polygon([(-9, 36), (-5, 36), (-5, 40), (-9, 40)]),
        epsg="4326",
    )
    spatial_extent = GridSpatialExtent(frozenset([cell]))

    query = SearchQuery(
        products=[VNP02IMG_EA],
        time_range=time_range,
        spatial_extent=spatial_extent,
        options={"bounding_box": (-10, 35, 0, 45)},
    )
    with pytest.raises(ValueError, match="Cannot specify both"):
        search_earthaccess(query)


def test_search_earthaccess_intersects_mode():
    """Using cell_overlap_mode='intersects' should include partially-overlapping cells."""
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )

    # Cell that partially overlaps a granule bounding box
    cell = GridCell(
        row="R1",
        col="C1",
        dist=10,
        bounds=Polygon([(-6, 38), (-2, 38), (-2, 42), (-6, 42)]),
        epsg="4326",
    )
    spatial_extent = GridSpatialExtent(frozenset([cell]))

    with patch("aer.search_earthaccess.core.earthaccess.search_data") as mock_search:
        granule = MagicMock()
        granule.get.side_effect = lambda k, d=None: {
            "meta": {"native-id": "456", "concept-id": "C456"},
            "umm": {
                "CollectionReference": {"ShortName": VNP02IMG_EA.name},
                "TemporalExtent": {
                    "RangeDateTime": {
                        "BeginningDateTime": "2023-01-01T00:05:00Z",
                        "EndingDateTime": "2023-01-01T00:10:00Z",
                    }
                },
                "SpatialExtent": {
                    "HorizontalSpatialDomain": {
                        "Geometry": {
                            # Granule covers (-5, 37) to (0, 41) — partially overlaps cell
                            "BoundingRectangles": [
                                {
                                    "WestBoundingCoordinate": -5.0,
                                    "EastBoundingCoordinate": 0.0,
                                    "SouthBoundingCoordinate": 37.0,
                                    "NorthBoundingCoordinate": 41.0,
                                }
                            ]
                        }
                    }
                },
            },
        }.get(k, d)
        granule.data_links.side_effect = lambda access="direct": (
            ["s3://x"] if access == "direct" else ["https://x"]
        )
        granule.size.return_value = 5.0
        mock_search.return_value = [granule]

        # "contains" mode should NOT match (cell extends beyond the granule)
        query_contains = SearchQuery(
            products=[VNP02IMG_EA],
            time_range=time_range,
            spatial_extent=spatial_extent,
            cell_overlap_mode="contains",
        )
        df_contains = search_earthaccess(query_contains)
        assert df_contains.iloc[0]["grid_cells"] == []

        # "intersects" mode SHOULD match (partial overlap)
        query_intersects = SearchQuery(
            products=[VNP02IMG_EA],
            time_range=time_range,
            spatial_extent=spatial_extent,
            cell_overlap_mode="intersects",
        )
        df_intersects = search_earthaccess(query_intersects)
        assert df_intersects.iloc[0]["grid_cells"] == ["R1_C1"]


def test_parse_umm_polygon_failure_on_missing_spatial():
    """_parse_umm_polygon returns Failure when there is no spatial metadata."""
    from returns.result import Failure as F

    result = _parse_umm_polygon({})
    assert isinstance(result, F)

    result_empty = _parse_umm_polygon({"SpatialExtent": {}})
    assert isinstance(result_empty, F)


def test_parse_umm_polygon_multi_bounding_rectangles():
    """_parse_umm_polygon unions multiple bounding rectangles into one polygon."""
    from returns.result import Success as S

    umm = {
        "SpatialExtent": {
            "HorizontalSpatialDomain": {
                "Geometry": {
                    "BoundingRectangles": [
                        {
                            "WestBoundingCoordinate": 170,
                            "EastBoundingCoordinate": 180,
                            "SouthBoundingCoordinate": -10,
                            "NorthBoundingCoordinate": 10,
                        },
                        {
                            "WestBoundingCoordinate": -180,
                            "EastBoundingCoordinate": -170,
                            "SouthBoundingCoordinate": -10,
                            "NorthBoundingCoordinate": 10,
                        },
                    ]
                }
            }
        }
    }
    result = _parse_umm_polygon(umm)
    assert isinstance(result, S)
    poly = result.unwrap()
    # The union of two 10-degree-wide boxes should be wider than either alone
    minx, _, maxx, _ = poly.bounds
    assert maxx - minx > 10


def test_parse_umm_polygon_gpolygons():
    """_parse_umm_polygon correctly parses GPolygons — the real CMR key for VIIRS/MODIS."""
    from returns.result import Success as S

    umm = {
        "SpatialExtent": {
            "HorizontalSpatialDomain": {
                "Geometry": {
                    "GPolygons": [
                        {
                            "Boundary": {
                                "Points": [
                                    {"Longitude": -170.6, "Latitude": -60.6},
                                    {"Longitude": -119.3, "Latitude": -52.9},
                                    {"Longitude": -134.8, "Latitude": -34.7},
                                    {"Longitude": -169.7, "Latitude": -40.0},
                                    {"Longitude": -170.6, "Latitude": -60.6},
                                ]
                            }
                        }
                    ]
                }
            }
        }
    }
    result = _parse_umm_polygon(umm)
    assert isinstance(result, S)
    poly = result.unwrap()
    assert not poly.is_empty
    assert poly.area > 0


@pytest.mark.slow
@patch(
    "aer.spatial.core.ENV_SETTINGS.GRID_STORE_PATH",
    new=GRID_FIXTURE_PATH,
)
def test_search_earthaccess_real_spatial_extent():
    # Expand to 10 days to guarantee spatial coverage over this exact box
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 10, 0, 0)
    )

    # Load from the real spatial component dataset
    grid = GridDefinition(name="global", dist=100)

    # Target polygon over central Mexico to ensure valid search footprint
    poly = Polygon([(-102, 18), (-98, 18), (-98, 22), (-102, 22), (-102, 18)])
    spatial_extent = grid.intersecting_grid_spatial_extent(poly)

    # Confirm the grid actually loaded correctly before proceeding
    assert len(spatial_extent.grid_cells) > 0, (
        "Failed to load grid cells from Parquet definition"
    )

    query = SearchQuery(
        products=[VNP02IMG_EA],
        time_range=time_range,
        spatial_extent=spatial_extent,
        options={"count": 5},
    )
    df = search_earthaccess(query)

    assert not df.empty, (
        "Expected non-empty results for spatial grid search over Mexico"
    )
    assert "grid_cells" in df.columns, "Expected 'grid_cells' column to be populated."

    # Verify that the array evaluates properly
    assert isinstance(df.iloc[0]["grid_cells"], list)
