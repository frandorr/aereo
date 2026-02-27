"""
Spatial component for storing geometry features, AOI types, and other spatial abstractions.
"""

from aer.spatial.core import (
    GridCell,
    GridDefinition,
    GridSpatialExtent,
    reproject_polygon,
)

__all__ = [
    "GridCell",
    "GridDefinition",
    "GridSpatialExtent",
    "reproject_polygon",
]
