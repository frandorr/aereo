"""
Spatial component for storing geometry features, AOI types, and other spatial abstractions.
"""

from aer.spatial.core import (
    GridCell,
    GridCellOri,
    GridDefinition,
    OverlapMode,
    add_overlapping_cells,
    find_overlapping_cells,
)
from aer.spatial.majortom import Grid
from aer.spatial.utils import (
    get_utm_epsg_from_geometry,
    get_utm_zone_from_latlng,
    reproject_geom,
)

__all__ = [
    "GridDefinition",
    "GridCellOri",
    "GridCell",
    "OverlapMode",
    "Grid",
    "add_overlapping_cells",
    "get_utm_epsg_from_geometry",
    "get_utm_zone_from_latlng",
    "reproject_geom",
    "find_overlapping_cells",
]
