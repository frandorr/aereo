"""
Spatial component for storing geometry features, AOI types, and other spatial abstractions.
"""

from aer.spatial.core import (
    GeomLike,
    GridCell,
    GridDefinition,
    OverlapMode,
    format_intersects,
)
from aer.spatial.majortom import Grid, GridSchema
from aer.spatial.utils import (
    get_utm_epsg_from_geometry,
    get_utm_zone_from_latlng,
    reproject_geom,
)

__all__ = [
    "GridDefinition",
    "GridCell",
    "OverlapMode",
    "Grid",
    "GridSchema",
    "format_intersects",
    "GeomLike",
    "get_utm_epsg_from_geometry",
    "get_utm_zone_from_latlng",
    "reproject_geom",
]
