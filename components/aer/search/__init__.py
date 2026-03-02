"""
Pure domain model for satellite search intent. Defines typed search queries (GOES, VIIRS, MODIS, Sentinel-3), temporal and spatial constraints, and constellation-specific parameters, without infrastructure concerns such as APIs, STAC, or S3.
"""

from aer.search.core import EARTHACCESS, SearchMethod, search_earthaccess

__all__ = ["search_earthaccess", "SearchMethod", "EARTHACCESS"]
