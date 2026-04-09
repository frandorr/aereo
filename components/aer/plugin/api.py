"""High-level API for plugin-based search and extraction.

This module provides user-facing functions for searching and extracting
satellite data using the product-based plugin dispatch system.

Example::

    from aer.plugin.api import run_search

    # Auto-select plugin based on products
    results = run_search(products=["goes-16"])

    # Explicit plugin selection
    results = run_search(products=["goes-16"], plugin_name="goes_plugin")
"""

from __future__ import annotations

import warnings
from typing import Any

import pluggy

from aer.plugin.core import AerSpec, PROJECT_NAME
from aer.plugin.selector import (
    NoMatchingPluginError,
    PluginConflictError,
    PluginSelector,
)

# Global plugin manager instance
_plugin_manager: pluggy.PluginManager | None = None


def _get_plugin_manager() -> pluggy.PluginManager:
    """Get or create the global plugin manager.

    Returns:
        Configured PluginManager with loaded plugins.
    """
    global _plugin_manager

    if _plugin_manager is None:
        _plugin_manager = pluggy.PluginManager(PROJECT_NAME)
        _plugin_manager.add_hookspecs(AerSpec)
        _plugin_manager.load_setuptools_entrypoints("aer.plugins")

    return _plugin_manager


def run_search(
    products: list[str],
    plugin_name: str | None = None,
    collections: list[str] | None = None,
    intersects: Any = None,
    time_range: Any = None,
    search_params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Search for satellite data using product-based plugin dispatch.

    This function automatically selects the appropriate plugin based on
    the requested products. If multiple plugins match, a conflict is
    raised unless an explicit plugin_name is provided.

    Args:
        products: List of product identifiers to search for
            (e.g., ["goes-16", "modis"]).
        plugin_name: Optional explicit plugin name. If provided,
            product matching is skipped and this plugin is used.
        collections: Optional list of collection identifiers.
        intersects: Optional spatial geometry to intersect with.
        time_range: Optional temporal range filter.
        search_params: Optional dictionary of search parameters.
        **kwargs: Additional keyword arguments passed to the search hook.

    Returns:
        GeoDataFrame: Search results from the selected plugin.

    Raises:
        PluginConflictError: If multiple plugins match and no explicit
            plugin_name is provided.
        NoMatchingPluginError: If no plugins support the requested products.
        RuntimeError: If plugin initialization fails.
    """
    pm = _get_plugin_manager()
    selector = PluginSelector(pm)
    selector.index_plugins()

    # Warn if explicit selection bypasses product matching
    if plugin_name:
        warnings.warn(
            f"Explicit plugin '{plugin_name}' provided, product-based "
            f"matching skipped for products: {products}",
            UserWarning,
            stacklevel=2,
        )

    try:
        plugin = selector.select(products=products, plugin_name=plugin_name)
    except (PluginConflictError, NoMatchingPluginError):
        raise
    except RuntimeError as e:
        raise RuntimeError(f"Failed to initialize plugins: {e}") from e

    # Call the search hook
    results = plugin.search(
        collections=collections or [],
        intersects=intersects,
        time_range=time_range,
        search_params=search_params,
        **kwargs,
    )

    return results


def run_extract(
    plugin_name: str | None = None,
    task: Any | None = None,
    **kwargs: Any,
) -> Any:
    """Extract data using plugin-based dispatch.

    This function dispatches to the appropriate plugin's extract method.

    Args:
        plugin_name: Optional explicit plugin name to use.
        task: ExtractionTask to process.
        **kwargs: Additional keyword arguments passed to the extract hook.

    Returns:
        ExtractionTask: The processed task with extraction results.

    Raises:
        ValueError: If no task is provided or plugin not found.
    """
    if task is None:
        raise ValueError("run_extract requires an ExtractionTask")

    # For extract, we typically need explicit plugin or task-based selection
    # This is a placeholder for future implementation
    raise NotImplementedError(
        "run_extract is not yet implemented. "
        "Use explicit plugin selection via PluginSelector."
    )


def list_available_products() -> list[str]:
    """List all products that have registered plugins.

    Returns:
        List of product identifiers with available plugins.
    """
    pm = _get_plugin_manager()
    selector = PluginSelector(pm)
    selector.index_plugins()

    return list(selector.list_index().keys())


def list_plugins() -> list[str]:
    """List all registered plugin names.

    Returns:
        List of registered plugin names.
    """
    pm = _get_plugin_manager()
    plugins = pm.get_plugins()
    names = []

    for plugin in plugins:
        if plugin is not None:
            name = pm.get_name(plugin)
            if name:
                names.append(name)

    return names
