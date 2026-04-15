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
from typing import TYPE_CHECKING, Any

import pluggy
from aer.hookspecs import (
    extract,
    prepare_for_extraction,
    search,
    supported_collections,
)
from aer.hookspecs import core as hookspecs_core
from aer.plugin.core import PROJECT_NAME
from aer.plugin.selector import (
    NoMatchingPluginError,
    PluginConflictError,
    PluginSelector,
)
from aer.temporal import TimeRange

if TYPE_CHECKING:
    from pandera.typing.geopandas import GeoDataFrame
    from shapely.geometry import MultiPolygon, Polygon

# Global plugin manager and selector instances
_plugin_manager: pluggy.PluginManager | None = None
_plugin_selector: PluginSelector | None = None


def _get_plugin_manager() -> pluggy.PluginManager:
    """Get or create the global plugin manager.

    Returns:
        Configured PluginManager with loaded plugins.
    """
    global _plugin_manager

    if _plugin_manager is None:
        _plugin_manager = pluggy.PluginManager(PROJECT_NAME)
        _plugin_manager.add_hookspecs(hookspecs_core)
        _plugin_manager.load_setuptools_entrypoints("aer.plugins")

    return _plugin_manager


def _get_selector() -> PluginSelector:
    """Get or create the global plugin selector.

    Returns:
        Configured PluginSelector.
    """
    global _plugin_selector
    pm = _get_plugin_manager()

    if _plugin_selector is None:
        _plugin_selector = PluginSelector(pm)

    _plugin_selector.index_plugins()
    return _plugin_selector


def run_search(
    collections: list[str],
    plugin_name: str | None = None,
    intersects: "Polygon | MultiPolygon | None" = None,
    time_range: TimeRange | None = None,
    search_params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> GeoDataFrame:
    """Search for satellite data using collection-based plugin dispatch.

    This function automatically selects the appropriate plugin based on
    the requested collections. If multiple plugins match, a conflict is
    raised unless an explicit plugin_name is provided.

    Args:
        collections: List of collection identifiers to search for
            (e.g., ["ABI-L1b-RadF", "VJ102IMG"]).
        plugin_name: Optional explicit plugin name. If provided,
            collection matching is skipped and this plugin is used.
        intersects: Optional spatial geometry to intersect with.
        time_range: Optional temporal range filter.
        search_params: Optional dictionary of search parameters.
        **kwargs: Additional keyword arguments passed to the search hook.

    Returns:
        GeoDataFrame: Search results from the selected plugin.

    Raises:
        PluginConflictError: If multiple plugins match and no explicit
            plugin_name is provided.
        NoMatchingPluginError: If no plugins support the requested collections.
        RuntimeError: If plugin initialization fails.
    """
    pm = _get_plugin_manager()
    selector = _get_selector()

    # Warn if explicit selection bypasses collection matching
    if plugin_name:
        warnings.warn(
            f"Explicit plugin '{plugin_name}' provided, collection-based "
            f"matching skipped for collections: {collections}",
            UserWarning,
            stacklevel=2,
        )

    try:
        plugin = selector.select(
            collections=collections, plugin_type="search", plugin_name=plugin_name
        )
    except (PluginConflictError, NoMatchingPluginError):
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to select plugin: {e}") from e

    # Find the hook implementation for this specific plugin
    hook_impls = [
        impl for impl in pm.hook.search.get_hookimpls() if impl.plugin == plugin
    ]
    if not hook_impls:
        raise RuntimeError(
            f"Plugin '{pm.get_name(plugin)}' has no search implementation"
        )

    name = hook_impls[0].function.__name__
    results = []
    for impl in hook_impls:
        plugin_ref = impl.plugin
        if isinstance(plugin_ref, type):
            plugin_instance = plugin_ref()
        else:
            plugin_instance = plugin_ref
        func = getattr(plugin_instance, name)
        start_datetime = time_range.start if time_range else None
        end_datetime = time_range.end if time_range else None
        result = func(
            collections=collections,
            intersects=intersects,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            search_params=search_params,
        )
        results.append(result)

    return results[0] if results else GeoDataFrame()


def create_tasks(
    search_results: GeoDataFrame,
    intersects: Any,
    output_path: str,
    plugin_name: str | None = None,
) -> list:
    """Create extraction tasks from search results.

    Transforms search results into discrete extraction tasks that can be
    processed independently. The actual implementation is delegated to
    the plugin's prepare_for_extraction hook.

    Args:
        search_results: GeoDataFrame returned from run_search.
        intersects: Spatial geometry to intersect with for task preparation.
        output_path: Base output path for extracted files.
        plugin_name: Optional explicit plugin name for task creation.

    Returns:
        List of GeoDataFrames ready for processing.

    Raises:
        ValueError: If no search_results provided.
        PluginConflictError: If multiple plugins can prepare tasks.
    """
    if search_results is None or (
        hasattr(search_results, "__len__") and len(search_results) == 0
    ):
        raise ValueError("create_tasks requires non-empty search_results")

    pm = _get_plugin_manager()

    # Determine which plugin to use for task preparation.
    # If a plugin_name is provided, use it.
    # Otherwise, try to find a plugin that supports 'extract' or 'search'
    # that also implements prepare_for_extraction.
    selected_plugin = None

    if plugin_name:
        selected_plugin = pm.get_plugin(plugin_name)
        if selected_plugin is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")
    else:
        # Find all plugins that implement prepare_for_extraction
        plugins_with_prepare = [
            p for p in pm.get_plugins() if hasattr(p, "prepare_for_extraction")
        ]

        if not plugins_with_prepare:
            raise RuntimeError("No plugins have prepare_for_extraction implemented")

        if len(plugins_with_prepare) == 1:
            selected_plugin = plugins_with_prepare[0]
        else:
            # Multiple plugins can prepare tasks - we need a better heuristic
            # or explicit choice. For now, we take the first but log a warning.
            selected_plugin = plugins_with_prepare[0]
            warnings.warn(
                f"Multiple plugins implement prepare_for_extraction. Using "
                f"'{pm.get_name(selected_plugin)}'. Use plugin_name to be explicit.",
                UserWarning,
                stacklevel=2,
            )

    # Call the prepare_for_extraction hook via the targeted plugin
    hook_impls = [
        impl
        for impl in pm.hook.prepare_for_extraction.get_hookimpls()
        if impl.plugin == selected_plugin
    ]
    if not hook_impls:
        raise RuntimeError(
            f"Plugin '{pm.get_name(selected_plugin)}' has no prepare_for_extraction implementation"
        )

    name = hook_impls[0].function.__name__
    tasks_list = []
    for impl in hook_impls:
        plugin_ref = impl.plugin
        if isinstance(plugin_ref, type):
            plugin_instance = plugin_ref()
        else:
            plugin_instance = plugin_ref
        func = getattr(plugin_instance, name)
        result = func(
            search_results=search_results,
            prepare_params={"intersects": intersects, "output_path": output_path},
        )
        tasks_list.append(result)

    return tasks_list[0] if tasks_list else []


def run_extract(
    assets_batch: GeoDataFrame,
    plugin_name: str | None = None,
    extract_params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> GeoDataFrame:
    """Extract data for a batch of assets.

    Processes a batch of assets to download and process the satellite data.
    The actual implementation is delegated to the plugin's extract hook.

    Args:
        assets_batch: GeoDataFrame of assets to extract.
        plugin_name: Optional explicit plugin name to use.
        extract_params: Optional dictionary of extraction parameters.
        **kwargs: Additional keyword arguments passed to the extract hook.

    Returns:
        GeoDataFrame: Extracted artifacts.

    Raises:
        ValueError: If no assets_batch is provided.
    """
    if assets_batch is None:
        raise ValueError("run_extract requires an assets_batch")

    pm = _get_plugin_manager()

    if plugin_name:
        plugin = pm.get_plugin(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin '{plugin_name}' not found")
    else:
        # Future enhancement: In the future, we could infer the plugin from task metadata
        # For now, we look for any plugin implementing 'extract'
        extract_plugins = [p for p in pm.get_plugins() if hasattr(p, "extract")]
        if not extract_plugins:
            raise ValueError("No extraction plugins found. Provide plugin_name.")

        plugin = extract_plugins[0]

    # Call the extract hook
    hook_impls = [
        impl for impl in pm.hook.extract.get_hookimpls() if impl.plugin == plugin
    ]
    if not hook_impls:
        raise RuntimeError(
            f"Plugin '{pm.get_name(plugin)}' has no extract implementation"
        )

    name = hook_impls[0].function.__name__
    results = []
    for impl in hook_impls:
        plugin_ref = impl.plugin
        if isinstance(plugin_ref, type):
            plugin_instance = plugin_ref()
        else:
            plugin_instance = plugin_ref
        func = getattr(plugin_instance, name)
        result = func(
            assets_batch=assets_batch, extract_params=extract_params, **kwargs
        )
        results.append(result)

    return results[0] if results else GeoDataFrame()


def list_available_collections(plugin_type: str | None = None) -> list[str]:
    """List all collections that have registered plugins.

    Args:
        plugin_type: Optional filter for plugin type ("search" or "extract").

    Returns:
        List of collection identifiers with available plugins.
    """
    selector = _get_selector()

    collections = list(selector.list_index().keys())

    if plugin_type:
        matching_plugins = selector.get_matching_plugins(
            collections, plugin_type=plugin_type
        )
        collections_with_type = set()
        for collection, plugins in selector.list_index().items():
            if any(p in matching_plugins for p in plugins):
                collections_with_type.add(collection)
        return list(collections_with_type)

    return collections


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
