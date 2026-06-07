"""
Grid module built on the Major TOM grid (via ``majortom_eg``).

``GridCell.area_def()`` returns an :class:`odc.geo.geobox.GeoBox` centred on the
cell's grid point with a fixed size of ``D * (1 + margin/100)`` metres.

The legacy ``AreaDef`` dataclass has been removed — downstream code that needs
pyresample YAML should construct it locally with ``_geobox_to_pyresample_yaml()``
(or equivalent) using the GeoBox returned by ``area_def()``.
"""

from aereo.grid.core import GridCell, GridDefinition

__all__ = ["GridCell", "GridDefinition"]
