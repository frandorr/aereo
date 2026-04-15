"""Plugin management for the aer system.

Provides utilities for discovery, selection, and dispatch
to plugins implementing the hook specifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pluggy
from aer.hookspecs import (
    PROJECT_NAME,
    hookimpl,
    hookspec,
)

if TYPE_CHECKING:
    from aer.plugin.selector import PluginSelector

# Marker for plugin supported_collections attribute
SUPPORTED_COLLECTIONS_ATTR = "supported_collections"

# Marker for plugin type (search vs extract)
PLUGIN_TYPE_ATTR = "plugin_type"


def get_supported_collections(plugin: Any) -> list[str]:
    """Extract supported_collections list from a plugin.

    Plugins SHOULD declare ``supported_collections`` as a class attribute
    containing a list of collection identifier strings, but it can also
    be an instance attribute.

    Args:
        plugin: A plugin instance.

    Returns:
        List of collection identifier strings the plugin supports.

    Raises:
        ValueError: If the plugin does not have a valid supported_collections attribute.
    """
    if not hasattr(plugin, SUPPORTED_COLLECTIONS_ATTR):
        raise ValueError(
            f"Plugin {type(plugin).__name__} must declare '{SUPPORTED_COLLECTIONS_ATTR}' "
            f"attribute as a list of collection identifiers"
        )
    collections = cast(list, getattr(plugin, SUPPORTED_COLLECTIONS_ATTR))
    return collections


def get_plugin_type(pm: pluggy.PluginManager, plugin: object) -> set[str]:
    """Infer plugin type from hook implementations using pluggy's get_hookcallers.

    Args:
        pm: The pluggy PluginManager instance.
        plugin: A plugin instance.

    Returns:
        Set containing all hook names implemented by the plugin.
    """
    hookcallers = pm.get_hookcallers(plugin)
    if not hookcallers:
        return set()

    return {hc.name for hc in hookcallers if hasattr(hc, "name")}


__all__ = [
    "PROJECT_NAME",
    "hookimpl",
    "hookspec",
    "get_supported_collections",
    "get_plugin_type",
    "SUPPORTED_COLLECTIONS_ATTR",
    "PLUGIN_TYPE_ATTR",
]
