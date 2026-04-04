"""
Plugin component providing the plugin registry, capability-based routing,
pipeline orchestration, and decorators for registering search and extract plugins.
"""

from aer.plugin.core import (
    PluginRegistry,
    plugin,
    plugin_registry,
    Pipeline,
    PluginInfo,
    run_search,
    run_extract,
)
from aer.plugin.search import SearchPlugin

__all__ = [
    "PluginRegistry",
    "plugin",
    "plugin_registry",
    "Pipeline",
    "PluginInfo",
    "run_search",
    "run_extract",
    "SearchPlugin",
]
