"""
Grid module built on the Major TOM grid (via ``majortom_eg``).

``GridCell`` represents a raw MajorTOM grid cell. Use
``cell.to_extract_patch(resolution=..., ...)`` to obtain an extraction-ready
patch with a GeoBox.
"""

from aereo.grid.core import (
    ExtractionPatch,
    ExtractPatch,
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
    "ExtractPatch",
    "ExtractionPatch",
]
