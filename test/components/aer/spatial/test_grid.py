"""Tests for the spatial Grid class and UTM utilities.

Verifies grid initialization, lat/lon to row/col conversion,
and UTM EPSG code derivation from geometries.
"""

import pytest
from shapely.geometry import Point, Polygon, GeometryCollection
from aer.spatial import Grid, get_utm_epsg_from_geometry, get_utm_zone_from_latlng


def test_get_utm_epsg_from_geometry_point():
    # Berlin (Northern Hemisphere)
    pt1 = Point(13.4050, 52.5200)
    epsg1 = get_utm_epsg_from_geometry(pt1)
    assert epsg1 == "32633"

    # Sydney (Southern Hemisphere)
    pt2 = Point(151.2093, -33.8688)
    epsg2 = get_utm_epsg_from_geometry(pt2)
    assert epsg2 == "32756"


def test_get_utm_epsg_from_geometry_polygon():
    # A small triangle near Berlin
    poly = Polygon([(13.0, 52.0), (13.5, 52.0), (13.5, 52.5)])
    epsg = get_utm_epsg_from_geometry(poly)
    assert epsg == "32633"


def test_get_utm_epsg_from_geometry_invalid_type():
    with pytest.raises(ValueError, match="Unsupported geometry type"):
        get_utm_epsg_from_geometry(GeometryCollection())


def test_get_utm_zone_from_latlng():
    # Berlin
    latlng = [52.5200, 13.4050]
    epsg = get_utm_zone_from_latlng(latlng)
    assert epsg == "32633"


def test_grid_initialization():
    grid = Grid(
        name="test_grid",
        dist=2000000,
        latitude_range=(-30, 30),
        longitude_range=(-50, 50),
    )
    assert grid.name == "test_grid"
    assert grid.dist == 2000000
    assert not grid.points.empty
    assert "utm_footprint" in grid.points.columns
    assert len(grid.rows) > 0


def test_grid_latlon2rowcol():
    grid = Grid(
        name="test_grid",
        dist=2000000,
        latitude_range=(-80, 80),
        longitude_range=(-180, 180),
    )
    lats = [0, 45, -45]
    lons = [0, 10, -10]
    out = grid.latlon2rowcol(lats, lons)
    assert len(out[0]) == 3
    assert len(out[1]) == 3


def test_grid_rowcol2latlon():
    grid = Grid(
        name="test_grid",
        dist=2000000,
        latitude_range=(-80, 80),
        longitude_range=(-180, 180),
    )
    lats = [0, 45, -45]
    lons = [0, 10, -10]
    out = grid.latlon2rowcol(lats, lons)
    row_back, col_back = grid.rowcol2latlon(out[0], out[1])
    assert len(row_back) == 3
    assert len(col_back) == 3
