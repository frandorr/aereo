"""
Abstract classes that should be used as contract. Includes SearchProvider, Extractor, etc.

It is important to note that these are abstract classes and should not be instantiated directly.
They serve as a blueprint for the actual implementations of extractors and search providers that will be used in the AEREO framework.
By defining these interfaces, we ensure that all implementations adhere to a consistent structure and can be easily integrated into the system.
"""

from aereo.interfaces.core import (
    AereoDataset,
    AereoPlugin,
    AereoProfile,
    Downloader,
    DownloaderCallable,
    ExecutionBackend,
    ExtractionProfile,
    ExtractionTask,
    Extractor,
    GridConfig,
    PipelineCallback,
    PipelineProfile,
    PluginParam,
    Processor,
    Reader,
    Reprojector,
    SearchProvider,
    TaskStaging,
    Writer,
    merge_params,
    validate_aereo_dataset,
)
from aereo.interfaces.core import (
    DEFAULT_RASTER_COMPRESS as DEFAULT_RASTER_COMPRESS,
    DEFAULT_RASTER_DRIVER as DEFAULT_RASTER_DRIVER,
    DEFAULT_RASTER_PREDICTOR as DEFAULT_RASTER_PREDICTOR,
    DEFAULT_RASTER_ZLEVEL as DEFAULT_RASTER_ZLEVEL,
)

__all__ = [
    "AereoDataset",
    "AereoPlugin",
    "AereoProfile",
    "Downloader",
    "DownloaderCallable",
    "ExecutionBackend",
    "ExtractionProfile",
    "ExtractionTask",
    "Extractor",
    "GridConfig",
    "PipelineCallback",
    "PipelineProfile",
    "PluginParam",
    "Processor",
    "Reader",
    "Reprojector",
    "SearchProvider",
    "TaskStaging",
    "Writer",
    "merge_params",
    "validate_aereo_dataset",
    "DEFAULT_RASTER_COMPRESS",
    "DEFAULT_RASTER_DRIVER",
    "DEFAULT_RASTER_PREDICTOR",
    "DEFAULT_RASTER_ZLEVEL",
]
