"""
Abstract classes that should be used as contract. Includes SearchProvider, Extractor, etc.

It is important to note that these are abstract classes and should not be instantiated directly.
They serve as a blueprint for the actual implementations of extractors and search providers that will be used in the AEREO framework.
By defining these interfaces, we ensure that all implementations adhere to a consistent structure and can be easily integrated into the system.
"""

from aereo.interfaces.core import (
    AereoPlugin,
    AereoProfile,
    Downloader,
    ExecutionBackend,
    ExtractionProfile,
    ExtractionTask,
    Extractor,
    GridConfig,
    PluginParam,
    SearchProvider,
    TaskStaging,
    merge_params,
)
from aereo.interfaces.core import (
    DEFAULT_RASTER_COMPRESS as DEFAULT_RASTER_COMPRESS,
    DEFAULT_RASTER_DRIVER as DEFAULT_RASTER_DRIVER,
    DEFAULT_RASTER_PREDICTOR as DEFAULT_RASTER_PREDICTOR,
    DEFAULT_RASTER_ZLEVEL as DEFAULT_RASTER_ZLEVEL,
)

__all__ = [
    "AereoPlugin",
    "AereoProfile",
    "Downloader",
    "ExecutionBackend",
    "ExtractionProfile",
    "ExtractionTask",
    "Extractor",
    "GridConfig",
    "PluginParam",
    "SearchProvider",
    "TaskStaging",
    "merge_params",
    "DEFAULT_RASTER_COMPRESS",
    "DEFAULT_RASTER_DRIVER",
    "DEFAULT_RASTER_PREDICTOR",
    "DEFAULT_RASTER_ZLEVEL",
]
