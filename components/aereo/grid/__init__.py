"""
Grid module built on the Major TOM grid (via ``majortom_eg``).

``ExtractionPatch.geobox`` returns an :class:`odc.geo.geobox.GeoBox` centred on the
cell's grid point with a fixed size of ``D * (1 + margin/100)`` metres.
"""

from aereo.grid.core import ExtractionPatch, GridDefinition, generate_extraction_patches

__all__ = ["ExtractionPatch", "GridDefinition", "generate_extraction_patches"]
