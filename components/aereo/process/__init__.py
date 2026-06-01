"""Built-in processor functions for the AEREO Hamilton pipeline.

Re-exports function-based processors discovered via the
``aereo.process`` entry-point group.
"""

from aereo.process.core import (
    composite,
    compute_ndvi,
    compute_ndwi,
    mask_clouds,
    normalize,
    select_bands,
    supported_collections,
)

__all__ = [
    "composite",
    "compute_ndvi",
    "compute_ndwi",
    "mask_clouds",
    "normalize",
    "select_bands",
    "supported_collections",
]
