"""Base Hamilton nodes for the search pipeline stage.

In a composed pipeline, a search plugin upstream provides
``search_assets`` as a function of ``aoi``, ``start_datetime``,
``end_datetime``, etc.  This module acts as the output boundary of the
search stage, giving downstream drivers a stable node name to depend on.
"""

from __future__ import annotations

import geopandas as gpd


def search_results(search_assets: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return validated search results.

    Args:
        search_assets: GeoDataFrame produced by the upstream search plugin.

    Returns:
        The same GeoDataFrame, forwarded as the canonical search output.
    """
    return search_assets
