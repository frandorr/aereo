"""Built-in plugins for the AEREO pipeline.

Provides default implementations for Reprojector, Writer, and Processor stages.
"""

from aereo.builtins.core import (
    Composite,
    NDVI,
    Normalize,
    QAMask,
    ReprojectODC,
    SelectBands,
    WriteGeoTIFF,
)
from aereo.builtins.search import SearchSTAC

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
