"""
Abstract classes that should be used as contract. Includes SearchProvider, Reader, etc.

It is important to note that these are abstract classes and should not be instantiated directly.
They serve as a blueprint for the actual implementations of readers, search providers, processors,
reprojectors, and writers that will be used in the AEREO framework.
By defining these interfaces, we ensure that all implementations adhere to a consistent structure and can be easily integrated into the system.
"""

from aereo.interfaces.core import (
    AereoPlugin,
    BatchWriter,
    ExecutionBackend,
    ExtractConfig,
    ExtractionTask,
    GridConfig,
    PatchConfig,
    GridFilterMode,
    PipelineCallback,
    Processor,
    Reader,
    Reprojector,
    SearchProvider,
    TaskStaging,
    Writer,
    build_collection_asset_filters,
)
from aereo.interfaces.core import (
    DEFAULT_CELLS_PER_TASK as DEFAULT_CELLS_PER_TASK,
)
from aereo.interfaces.utils import (
    infer_dataset_time_bounds,
    normalize_geometry_input,
    set_dataset_time_bounds,
    validate_aereo_dataset,
)


__all__ = [
    "AereoPlugin",
    "BatchWriter",
    "ExecutionBackend",
    "ExtractConfig",
    "ExtractionTask",
    "GridConfig",
    "PatchConfig",
    "GridFilterMode",
    "PipelineCallback",
    "Processor",
    "Reader",
    "Reprojector",
    "SearchProvider",
    "TaskStaging",
    "Writer",
    "build_collection_asset_filters",
    "infer_dataset_time_bounds",
    "normalize_geometry_input",
    "set_dataset_time_bounds",
    "validate_aereo_dataset",
    "DEFAULT_CELLS_PER_TASK",
]
