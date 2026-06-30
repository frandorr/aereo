"""
Grid module built on the Major TOM grid (via ``majortom_eg``).

``GridCell.geobox`` returns an :class:`odc.geo.geobox.GeoBox` centred on the
cell's grid point with a fixed size of ``D * (1 + margin/100)`` metres.
"""

from aereo.grid.core import (
    ExtractionPatch,
    GridCell,
    GridDefinition,
    build_grid_cells,
    intersect_cells,
)

__all__ = [
    "GridCell",
    "GridDefinition",
    "build_grid_cells",
    "intersect_cells",
    "ExtractionPatch",
]
