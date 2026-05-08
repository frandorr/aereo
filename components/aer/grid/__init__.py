"""
Grid module built on the Major TOM grid (via ``majortom_eg``).

``GridCell.area_def()`` returns an :class:`odc.geo.geobox.GeoBox` aligned to the
cell's UTM footprint.  ``GridDefinition.max_shape()`` builds real GeoBox
instances to determine the largest pixel dimensions across a batch of cells.

The legacy ``AreaDef`` dataclass has been removed — downstream code that needs
pyresample YAML should construct it locally with ``_geobox_to_pyresample_yaml()``
(or equivalent) using the GeoBox returned by ``area_def()``.
"""

from aer.grid.core import GridCell, GridDefinition

__all__ = ["GridCell", "GridDefinition"]
