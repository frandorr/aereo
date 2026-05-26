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
    ExtractionProfile,
    ExtractionTask,
    Extractor,
    GridConfig,
    PluginParam,
    SearchProvider,
    merge_params,
)

__all__ = [
    "AereoPlugin",
    "AereoProfile",
    "Downloader",
    "ExtractionProfile",
    "ExtractionTask",
    "Extractor",
    "GridConfig",
    "PluginParam",
    "SearchProvider",
    "merge_params",
]
