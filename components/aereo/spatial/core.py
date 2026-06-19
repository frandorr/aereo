"""Coordinate-system helpers for aereo.

Small set of pure functions for reprojecting shapely geometries and inferring
the UTM EPSG code that best fits a given geometry or (lat, lng) coordinate.
"""

from __future__ import annotations

import utm
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

_NORTH_EPSG_BASE = 326
_SOUTH_EPSG_BASE = 327


def reproject_geom(geom: BaseGeometry, src_epsg: str, dst_epsg: str) -> BaseGeometry:
    """Reproject a geometry to a different coordinate system.

    Args:
        geom: Shapely geometry in the source coordinate system.
        src_epsg: Source EPSG code.
        dst_epsg: Destination EPSG code.

    Returns:
        The reprojected Shapely geometry.
    """
    transformer = Transformer.from_crs(src_epsg, dst_epsg, always_xy=True)
    return transform(transformer.transform, geom)


def get_utm_epsg_from_geometry(geometry: BaseGeometry) -> str:
    """Get the UTM EPSG code from a Shapely geometry.

    Args:
        geometry: A Shapely geometry object.

    Returns:
        The UTM EPSG code as a string.

    Raises:
        ValueError: If the geometry type is not supported, or if the UTM zone
            cannot be determined from the geometry's centroid.
    """
    if isinstance(geometry, (Polygon, MultiPolygon, LineString)):
        lonlat = (geometry.centroid.x, geometry.centroid.y)
    elif isinstance(geometry, Point):
        lonlat = (geometry.x, geometry.y)
    else:
        raise ValueError(f"Unsupported geometry type: {type(geometry).__name__}")

    _, _, zone_number, zone_letter = utm.from_latlon(lonlat[1], lonlat[0])  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]

    if zone_number and zone_letter:
        epsg = f"{_NORTH_EPSG_BASE if zone_letter >= 'N' else _SOUTH_EPSG_BASE}{zone_number:02d}"
    else:
        raise ValueError("Could not determine UTM zone from geometry")

    return epsg


def get_utm_zone_from_latlng(latlng: list[float] | tuple[float, float]) -> str:
    """Get the UTM zone from a latlng and return the corresponding EPSG code.

    Args:
        latlng: A sequence of (latitude, longitude).

    Returns:
        The EPSG code for the UTM zone.

    Raises:
        TypeError: If latlng is not a list or tuple.
        ValueError: If the UTM zone cannot be determined.
    """
    if not isinstance(latlng, (list, tuple)):
        raise TypeError("latlng must be in the form of a list or tuple.")

    longitude = float(latlng[1])
    latitude = float(latlng[0])

    return get_utm_epsg_from_geometry(Point(longitude, latitude))
