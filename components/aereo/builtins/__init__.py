"""Built-in plugins for the AEREO pipeline.

Provides default implementations for Reader, Reprojector, Writer, and Processor stages.
"""

from aereo.builtins.processor import (
    Composite,
    NDVI,
    Normalize,
    QAMask,
    SelectBands,
)
from aereo.builtins.read import ReadODCSTAC
from aereo.builtins.reproject import ReprojectODC
from aereo.builtins.search import SearchSTAC, SearchEarthaccess
from aereo.builtins.batch_write import BatchWriteGeoTIFF
from aereo.builtins.write import WriteGeoTIFF

__all__ = [
    "BatchWriteGeoTIFF",
    "Composite",
    "NDVI",
    "Normalize",
    "QAMask",
    "ReadODCSTAC",
    "ReprojectODC",
    "SelectBands",
    "WriteGeoTIFF",
    "SearchSTAC",
    "SearchEarthaccess",
]
