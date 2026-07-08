"""
Grid module built on the Major TOM grid (via ``majortom_eg``).

``GridCell`` represents a raw MajorTOM grid cell. Use
``cell.to_geobox(resolution=..., ...)`` to obtain an extraction-ready GeoBox.
"""

from aereo.grid.core import (
    GridCell,
    GridDefinition,
    build_grid_cells,
    cells_bounds,
    intersect_cells,
)

__all__ = [
    "GridCell",
    "GridDefinition",
    "build_grid_cells",
    "cells_bounds",
    "intersect_cells",
]
