"""Built-in plugins for the AEREO pipeline.

Provides default implementations for search, task building, reading, reprojection,
processing, and writing stages as pure functions.
"""

from aereo.builtins.processor import (
    composite,
    ndvi,
    normalize,
    qa_mask,
    select_bands,
)
from aereo.builtins.read import read_odc_stac
from aereo.builtins.reproject import reproject_odc
from aereo.builtins.search import search_earthaccess, search_stac
from aereo.builtins.task_builder import build_grouped_tasks
from aereo.builtins.write import write_geotiff

__all__ = [
    "build_grouped_tasks",
    "composite",
    "ndvi",
    "normalize",
    "qa_mask",
    "read_odc_stac",
    "reproject_odc",
    "search_earthaccess",
    "search_stac",
    "select_bands",
    "write_geotiff",
]
