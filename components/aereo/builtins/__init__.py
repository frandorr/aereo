"""Built-in plugins for the AEREO pipeline.

Provides default implementations for Reprojector, Writer, and Processor stages.
"""

from aereo.builtins.processor import (
    Composite,
    NDVI,
    Normalize,
    QAMask,
    SelectBands,
)
from aereo.builtins.reproject import ReprojectODC
from aereo.builtins.search import SearchSTAC
from aereo.builtins.write import WriteGeoTIFF

__all__ = [
    "Composite",
    "NDVI",
    "Normalize",
    "QAMask",
    "ReprojectODC",
    "SelectBands",
    "WriteGeoTIFF",
    "SearchSTAC",
]
