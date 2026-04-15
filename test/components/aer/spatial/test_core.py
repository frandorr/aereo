"""Tests for the spatial component core models.

Verifies GridCellOri, GridDefinition, GridSchema validation, polygon reprojection,
and pyresample AreaDefinition generation.
"""

from datetime import datetime

import geopandas as gpd
import pytest
from aer.spatial import (
    GridCellOri,
    GridDefinition,
    OverlapMode,
    add_overlapping_cells,
    reproject_geom,
)
from majortom_eg.MajorTom import MajorTomGrid
from pyresample.geometry import AreaDefinition
from shapely.geometry import Polygon, shape


@pytest.fixture
def sample_polygon():
    return Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])


@pytest.fixture
def sample_grid_cell(sample_polygon):
    return GridCellOri(
        grid_cell="A_1",
        footprint=sample_polygon,
        utm_footprint=sample_polygon,
        utm_crs="EPSG:32631",
        dist=100000,
    )


@pytest.fixture
def sample_geojson_feature():
    """A GeoJSON Feature object."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        },
        "properties": {"name": "test"},
    }


@pytest.fixture
def sample_geojson_polygon():
    """A plain GeoJSON Polygon (not a Feature)."""
    return {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
    }


def test_reproject_polygon(sample_polygon):
    reprojected = reproject_geom(sample_polygon, "EPSG:4326", "EPSG:32631")
    assert isinstance(reprojected, Polygon)
    assert reprojected.bounds[2] > 1000


def test_grid_cell_area_name(sample_grid_cell):
    name = sample_grid_cell.area_name(resolution=500)
    assert name == "A_1_dist-100000m_res-500m"


def test_grid_cell_area_def(sample_grid_cell):
    area_def = sample_grid_cell.area_def(resolution=500)
    assert isinstance(area_def, AreaDefinition)
    assert area_def.area_id == "A_1_dist-100000m_res-500m"
    assert area_def.width == 100000 // 500
    assert area_def.height == 100000 // 500


def test_grid_definition_init():
    grid_def = GridDefinition(name="TestGrid", dist=100000, extent=(-180, -90, 180, 90))
    assert grid_def.name == "TestGrid"
    assert grid_def.dist == 100000
    assert grid_def.extent == (-180, -90, 180, 90)


def test_grid_definition_default_utm_definition():
    grid_def = GridDefinition(name="TestGrid", dist=100000)
    assert grid_def.utm_definition == "center"


def test_grid_definition_custom_utm_definition():
    grid_def = GridDefinition(name="TestGrid", dist=100000, utm_definition="bottomleft")
    assert grid_def.utm_definition == "bottomleft"


@pytest.fixture
def sample_gdf():
    return gpd.GeoDataFrame(
        {
            "id": ["test1"],
            "collection": ["test"],
            "geometry": [Polygon([(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)])],
            "start_time": [datetime(2020, 1, 1)],
            "end_time": [datetime(2020, 1, 2)],
            "href": ["http://test.com"],
        },
        crs="EPSG:4326",
    )


@pytest.fixture
def sample_aoi():
    return shape(
        {"type": "Polygon", "coordinates": [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]]}
    )


@pytest.fixture
def sample_grid():
    return MajorTomGrid(d=320)


def test_add_overlapping_cells_basic(sample_gdf, sample_aoi, sample_grid):
    result = add_overlapping_cells(
        sample_gdf, sample_aoi, sample_grid, OverlapMode.INTERSECTS
    )
    assert "cell_id" in result.columns
    assert "cell_footprint" in result.columns
    assert "utm_crs" in result.columns
    assert len(result) > 0
    assert result.iloc[0]["cell_id"] is not None


def test_add_overlapping_cells_multiple_results(sample_gdf, sample_aoi, sample_grid):
    gdf_multiple = gpd.GeoDataFrame(
        {
            "id": ["test1", "test2"],
            "collection": ["test", "test"],
            "geometry": [
                Polygon([(0.1, 0.1), (0.1, 0.2), (0.2, 0.2), (0.2, 0.1)]),
                Polygon([(1.1, 1.1), (1.1, 1.2), (1.2, 1.2), (1.2, 1.1)]),
            ],
            "start_time": [datetime(2020, 1, 1), datetime(2020, 1, 1)],
            "end_time": [datetime(2020, 1, 2), datetime(2020, 1, 2)],
            "href": ["http://test.com", "http://test.com"],
        },
        crs="EPSG:4326",
    )
    result = add_overlapping_cells(
        gdf_multiple,  # pyright: ignore[reportArgumentType]
        sample_aoi,
        sample_grid,
        OverlapMode.INTERSECTS,
    )
    assert len(result) > 2
    assert "test1" in result["id"].values
    assert "test2" in result["id"].values


def test_add_overlapping_cells_within_mode(sample_gdf, sample_aoi, sample_grid):
    result = add_overlapping_cells(
        sample_gdf, sample_aoi, sample_grid, OverlapMode.WITHIN
    )
    assert "cell_id" in result.columns
    assert len(result) > 0


def test_add_overlapping_cells_contains_mode(sample_gdf, sample_aoi, sample_grid):
    result = add_overlapping_cells(
        sample_gdf, sample_aoi, sample_grid, OverlapMode.CONTAINS
    )
    assert "cell_id" in result.columns
