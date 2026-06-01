"""Base Hamilton nodes for the extract pipeline stage.

In a composed pipeline, download / read / reproject / write plugins
upstream collectively produce ``write_cogs`` (or an equivalent
GeoDataFrame of extracted artifacts).  This module acts as the output
boundary of the extract stage, giving the driver a stable node name to
depend on.
"""

from __future__ import annotations

import geopandas as gpd


def artifacts_gdf(write_cogs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the final artifacts GeoDataFrame.

    Args:
        write_cogs: GeoDataFrame produced by the upstream write plugin.

    Returns:
        The same GeoDataFrame, forwarded as the canonical extract output.
    """
    return write_cogs
