"""
Plugin component providing pluggy-based hookspec architecture.

External packages implement AerSpec hooks using @hookimpl to provide
custom search, task preparation, and extraction operations.
"""

from aer.plugin.core import (
    AerSpec,
    hookspec,
    hookimpl,
    PROJECT_NAME,
)
from aer.plugin.search import SearchPlugin
from aer.plugin.extract import ExtractSpec
from aer.plugin.prepare_tasks import PrepareTasksSpec

__all__ = [
    "AerSpec",
    "SearchPlugin",
    "ExtractSpec",
    "PrepareTasksSpec",
    "hookspec",
    "hookimpl",
    "PROJECT_NAME",
]
