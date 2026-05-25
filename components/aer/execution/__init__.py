"""Execution backends and task runner for AER extraction tasks."""

from aer.execution.backends import LambdaBackend, RetryableLambdaError
from aer.execution.core import (
    ExecutionBackend,
    LocalProcessBackend,
    TaskRunner,
    TaskStaging,
    ThreadBackend,
)
from aer.gdal_env import configure_gdal, setup_gdal_worker

__all__ = [
    "ExecutionBackend",
    "LambdaBackend",
    "LocalProcessBackend",
    "RetryableLambdaError",
    "TaskRunner",
    "TaskStaging",
    "ThreadBackend",
    "configure_gdal",
    "setup_gdal_worker",
]
