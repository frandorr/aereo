"""Built-in reproject plugin for AEREO.

Exports :func:`reproject_to_grid` and ``supported_collections`` for
registration under the ``aereo.reproject`` entry-point group.
"""

from __future__ import annotations

from aereo.reproject.core import reproject_to_grid, supported_collections

__all__ = ["reproject_to_grid", "supported_collections"]
