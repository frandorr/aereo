import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.viz import plot_coverage


@pytest.fixture
def sample_search_results():
    """Create sample search results for coverage testing."""
    data = {
        "id": ["asset1", "asset2", "asset3"],
        "collection": ["sentinel-2", "sentinel-2", "landsat"],
        "geometry": [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]),
            Polygon([(2, 2), (3, 2), (3, 3), (2, 3)]),
        ],
        "start_time": pd.to_datetime(
            ["2024-01-01 10:00", "2024-01-01 14:00", "2024-01-02 10:00"]
        ),
        "end_time": pd.to_datetime(
            ["2024-01-01 10:05", "2024-01-01 14:05", "2024-01-02 10:05"]
        ),
        "href": [
            "http://example.com/1",
            "http://example.com/2",
            "http://example.com/3",
        ],
    }
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


@pytest.fixture
def sample_aoi():
    """Create a sample AOI GeoDataFrame."""
    return gpd.GeoDataFrame(
        {"name": ["test_aoi"]},
        geometry=[Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])],
        crs="EPSG:4326",
    )


def test_plot_coverage_with_aoi(sample_search_results, sample_aoi):
    """Test plot_coverage with search results and AOI."""
    fig = plot_coverage(sample_search_results, sample_aoi)
    assert fig is not None
    fig.clf()


def test_plot_coverage_without_aoi(sample_search_results):
    """Test plot_coverage with search results only."""
    fig = plot_coverage(sample_search_results)
    assert fig is not None
    fig.clf()


def test_plot_coverage_empty_results():
    """Test plot_coverage with empty search results."""
    empty = gpd.GeoDataFrame(
        columns=["id", "collection", "geometry", "start_time", "end_time", "href"],
        crs="EPSG:4326",
    )
    fig = plot_coverage(empty)
    assert fig is not None
    fig.clf()


def test_plot_coverage_no_temporal_data():
    """Test plot_coverage when search results lack start_time."""
    data = {
        "id": ["asset1"],
        "collection": ["test"],
        "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        "href": ["http://example.com/1"],
    }
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
    fig = plot_coverage(gdf)
    assert fig is not None
    fig.clf()
