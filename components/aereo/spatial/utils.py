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
    projected_geom = transform(transformer.transform, geom)
    return projected_geom


def get_utm_epsg_from_geometry(geometry: BaseGeometry) -> str:
    """
    Get the UTM EPSG code from a Shapely geometry.

    Args:
        geometry (BaseGeometry): A Shapely geometry object.
    Returns:
        str: The UTM EPSG code as a string.
    Raises:
        ValueError: If the geometry type is not supported.
    """

    if isinstance(geometry, (Polygon, MultiPolygon, LineString)):
        lonlat = (geometry.centroid.x, geometry.centroid.y)
    elif isinstance(geometry, Point):
        lonlat = (geometry.x, geometry.y)
    else:
        # raise an error if the geometry is not supported
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
