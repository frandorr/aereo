"""
Pure domain model for satellite search intent. Defines typed search queries (GOES, VIIRS, MODIS, Sentinel-3), temporal and spatial constraints, and constellation-specific parameters, without infrastructure concerns such as APIs, STAC, or S3.
"""

from aer.search import core

__all__ = ["core"]
