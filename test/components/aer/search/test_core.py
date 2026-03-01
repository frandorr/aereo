import pytest
from unittest.mock import patch, MagicMock
from aer.search import search_earthaccess
from aer.temporal import TimeRange
from aer.spectral import VNP02IMG, MODIS_02QKM
from aer.spatial import GridCell, GridSpatialExtent, GridDefinition
from shapely.geometry import Polygon
from datetime import datetime
from pathlib import Path


def test_search_earthaccess_empty():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    with patch("aer.search.core.earthaccess.search_data") as mock_search:
        mock_search.return_value = []
        df = search_earthaccess(products=[VNP02IMG], time_range=time_range)
        assert df.empty
        assert "product_name" in df.columns
        mock_search.assert_called_once()
        kwargs = mock_search.call_args.kwargs
        assert kwargs["short_name"] == [VNP02IMG.name]
        assert kwargs["temporal"] == ("2023-01-01 00:00:00", "2023-01-01 01:00:00")


def test_search_earthaccess_results():
    time_range = TimeRange(
        start=datetime(2023, 1, 1, 0, 0), end=datetime(2023, 1, 1, 1, 0)
    )
    with patch("aer.search.core.earthaccess.search_data") as mock_search:
        granule = MagicMock()
        granule.get.side_effect = lambda k, d=None: {
            "meta": {"native-id": "123", "concept-id": "C123"},
            "umm": {
                "CollectionReference": {"ShortName": VNP02IMG.name},
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

        df = search_earthaccess(products=[VNP02IMG], time_range=time_range)
        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["product_name"] == VNP02IMG.name
        assert df.iloc[0]["s3_url"] == "s3://bucket/test.nc"
        assert df.iloc[0]["https_url"] == "https://bucket/test.nc"
        assert df.iloc[0]["size_mb"] == 15.5


@pytest.mark.slow
def test_search_earthaccess_real_vnp02img():
    # A known timeframe where VIIRS data should exist globally.
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 2, 0)
    )
    df = search_earthaccess(products=[VNP02IMG], time_range=time_range, count=10)

    assert not df.empty, (
        f"Expected non-empty results for {VNP02IMG.name} over {time_range}"
    )
    assert "product_name" in df.columns
    assert "s3_url" in df.columns
    assert df.iloc[0]["product_name"] == VNP02IMG.name


@pytest.mark.slow
def test_search_earthaccess_real_modis():
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 2, 0)
    )
    df = search_earthaccess(products=[MODIS_02QKM], time_range=time_range, count=10)

    assert not df.empty, (
        f"Expected non-empty results for {MODIS_02QKM.name} over {time_range}"
    )
    assert "product_name" in df.columns
    assert "s3_url" in df.columns
    assert df.iloc[0]["product_name"] == MODIS_02QKM.name


@pytest.mark.slow
def test_search_earthaccess_real_multiple():
    from aer.spectral import VNP03IMG

    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 1, 0)
    )
    df = search_earthaccess(
        products=[VNP02IMG, VNP03IMG], time_range=time_range, count=10
    )

    assert not df.empty, (
        f"Expected non-empty results for multiple products over {time_range}"
    )
    assert "product_name" in df.columns
    pnames = set(df["product_name"].unique())
    assert VNP02IMG.name in pnames
    assert VNP03IMG.name in pnames


@pytest.mark.slow
def test_search_earthaccess_real_multiple_constellations():
    time_range = TimeRange(
        start=datetime(2024, 1, 1, 0, 0), end=datetime(2024, 1, 1, 1, 0)
    )
    # Query across VIIRS (VNP02IMG) and MODIS (MODIS_02QKM)
    df = search_earthaccess(
        products=[VNP02IMG, MODIS_02QKM], time_range=time_range, count=10
    )

    assert not df.empty, (
        f"Expected non-empty results for multiple constellations over {time_range}"
    )
    assert "product_name" in df.columns
    pnames = set(df["product_name"].unique())
    assert VNP02IMG.name in pnames, f"Expected to find {VNP02IMG.name} in results"
    assert MODIS_02QKM.name in pnames, f"Expected to find {MODIS_02QKM.name} in results"


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

    with patch("aer.search.core.earthaccess.search_data") as mock_search:
        # Mocking the granule return
        granule = MagicMock()
        granule.get.side_effect = lambda k, d=None: {
            "meta": {"native-id": "123", "concept-id": "C123"},
            "umm": {
                "CollectionReference": {"ShortName": VNP02IMG.name},
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

        df = search_earthaccess(
            products=[VNP02IMG], time_range=time_range, spatial_extent=spatial_extent
        )

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


@pytest.mark.slow
@patch(
    "aer.spatial.core.ENV_SETTINGS.GRID_STORE_PATH",
    new=Path("/root/repos/aer/components/aer/spatial"),
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

    df = search_earthaccess(
        products=[VNP02IMG],
        time_range=time_range,
        spatial_extent=spatial_extent,
        count=5,
    )

    assert not df.empty, (
        "Expected non-empty results for spatial grid search over Mexico"
    )
    assert "grid_cells" in df.columns, "Expected 'grid_cells' column to be populated."

    # Verify that the array evaluates properly
    assert isinstance(df.iloc[0]["grid_cells"], list)
