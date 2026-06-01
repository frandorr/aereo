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

__all__ = [
    "Composite",
    "NDVI",
    "Normalize",
    "QAMask",
    "ReprojectODC",
    "SelectBands",
    "WriteGeoTIFF",
]
