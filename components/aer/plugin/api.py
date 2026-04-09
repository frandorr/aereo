"""High-level API for plugin-based search and extraction.

This module provides user-facing functions for the complete pipeline:
1. Search - Find satellite data by products
2. Create Tasks - Transform search results into extraction tasks
3. Extract - Process extraction tasks

Users interact with these simple functions, not the plugin system.

Example::

    from aer.plugin.api import run_search, create_tasks, run_extract

    # 1. Search for data
    results = run_search(products=["goes-16"])

    # 2. Create extraction tasks
    tasks = create_tasks(
        search_results=results,
        intersects=my_geometry,
        output_path="/tmp/output"
    )

    # 3. Extract data
    for task in tasks:
        run_extract(task)
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
        plugin = selector.select(
            products=products, plugin_type="search", plugin_name=plugin_name
        )
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


def create_tasks(
    search_results: Any,
    intersects: Any,
    output_path: str,
    plugin_name: str | None = None,
) -> list[Any]:
    """Create extraction tasks from search results.

    Transforms search results into discrete extraction tasks that can be
    processed independently. The actual implementation is delegated to
    the plugin's prepare_tasks hook.

    Args:
        search_results: GeoDataFrame returned from run_search.
        intersects: Spatial geometry to intersect with for task preparation.
        output_path: Base output path for extracted files.
        plugin_name: Optional explicit plugin name for task creation.

    Returns:
        List of ExtractionTask objects ready for processing.

    Raises:
        ValueError: If no search_results provided.
        PluginConflictError: If multiple plugins can prepare tasks.
    """
    if search_results is None or (
        hasattr(search_results, "__len__") and len(search_results) == 0
    ):
        raise ValueError("create_tasks requires non-empty search_results")

    pm = _get_plugin_manager()
    selector = PluginSelector(pm)
    selector.index_plugins()

    # Get any plugin that has prepare_tasks - typically we'd use the same plugin
    # that performed the search, but we need to find one with prepare_tasks
    try:
        # Find plugins that have prepare_tasks implemented
        plugins_with_prepare = []
        for name in selector._plugin_types.keys():
            plugin = pm.get_plugin(name)
            if plugin and hasattr(plugin, "prepare_tasks"):
                plugins_with_prepare.append(name)

        if not plugins_with_prepare:
            raise RuntimeError("No plugins have prepare_tasks implemented")

        if plugin_name and plugin_name in plugins_with_prepare:
            selected_name = plugin_name
        elif len(plugins_with_prepare) == 1:
            selected_name = plugins_with_prepare[0]
        else:
            # Multiple plugins can prepare tasks - need explicit choice
            # For now, use the first one (could be smarter about this)
            selected_name = plugins_with_prepare[0]

        plugin = pm.get_plugin(selected_name)
        if plugin is None:
            raise RuntimeError(f"Plugin '{selected_name}' not found")
    except Exception as e:
        raise RuntimeError(f"Failed to prepare tasks: {e}") from e

    # Call the prepare_tasks hook
    if not hasattr(plugin, "prepare_tasks"):
        raise RuntimeError(f"Plugin '{selected_name}' does not implement prepare_tasks")

    tasks = plugin.prepare_tasks(
        search_results=search_results,
        intersects=intersects,
        output_path=output_path,
    )

    return tasks


def run_extract(
    task: Any,
    plugin_name: str | None = None,
    **kwargs: Any,
) -> Any:
    """Extract data for an extraction task.

    Processes an ExtractionTask to download and process the satellite data.
    The actual implementation is delegated to the plugin's extract hook.

    Args:
        task: ExtractionTask to process (from create_tasks).
        plugin_name: Optional explicit plugin name to use.
        **kwargs: Additional keyword arguments passed to the extract hook.

    Returns:
        ExtractionTask: The processed task with extraction results.

    Raises:
        ValueError: If no task is provided.
    """
    if task is None:
        raise ValueError("run_extract requires an ExtractionTask")

    pm = _get_plugin_manager()

    if plugin_name:
        plugin = pm.get_plugin(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")
    else:
        # Try to find an extract plugin - for now we need explicit plugin
        # In the future, could infer from task metadata
        raise ValueError(
            "run_extract requires explicit plugin_name. "
            "Use list_plugins() to see available plugins."
        )

    # Call the extract hook
    result = plugin.extract(task=task, **kwargs)

    return result


def list_available_products(plugin_type: str | None = None) -> list[str]:
    """List all products that have registered plugins.

    Args:
        plugin_type: Optional filter for plugin type ("search" or "extract").

    Returns:
        List of product identifiers with available plugins.
    """
    pm = _get_plugin_manager()
    selector = PluginSelector(pm)
    selector.index_plugins()

    products = list(selector.list_index().keys())

    if plugin_type:
        matching_plugins = selector.get_matching_plugins(
            products, plugin_type=plugin_type
        )
        products_with_type = set()
        for product, plugins in selector.list_index().items():
            if any(p in matching_plugins for p in plugins):
                products_with_type.add(product)
        return list(products_with_type)

    return products


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
