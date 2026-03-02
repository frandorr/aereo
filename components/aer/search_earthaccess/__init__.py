"""
Search implementation for NASA Earthdata using earthaccess.
"""

from aer.search_earthaccess.core import NoSpatialMetadataError, search_earthaccess

__all__ = ["search_earthaccess", "NoSpatialMetadataError"]
