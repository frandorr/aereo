import pytest
from typing import cast
from aereo.spatial.utils import (
    get_utm_epsg_from_geometry,
    get_utm_zone_from_latlng,
    reproject_geom,
)
from shapely.geometry import Point


def test_reproject_geom():
    # Point at (0, 0) in EPSG:4326
    point = Point(0, 0)
    # Reproject to EPSG:3857 (Web Mercator)
    reprojected = cast(Point, reproject_geom(point, "EPSG:4326", "EPSG:3857"))
    assert reprojected.x == pytest.approx(0.0)
    assert reprojected.y == pytest.approx(0.0)


def test_get_utm_epsg_from_geometry():
    # Point in London (approx 51.5N, 0.1W) -> UTM 30N
    point = Point(-0.1, 51.5)
    epsg = get_utm_epsg_from_geometry(point)
    assert epsg == "32630"

    # Point in Sydney (approx 33.8S, 151.2E) -> UTM 56S
    point_sydney = Point(151.2, -33.8)
    epsg_sydney = get_utm_epsg_from_geometry(point_sydney)
    assert epsg_sydney == "32756"


def test_get_utm_zone_from_latlng():
    # London
    epsg = get_utm_zone_from_latlng((51.5, -0.1))
    assert epsg == "32630"

    # Sydney
    epsg_sydney = get_utm_zone_from_latlng((-33.8, 151.2))
    assert epsg_sydney == "32756"


def test_get_utm_epsg_unsupported_geometry():
    with pytest.raises(ValueError, match="Unsupported geometry type"):
        get_utm_epsg_from_geometry("not a geometry")  # type: ignore
