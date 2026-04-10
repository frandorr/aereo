"""Plugin selector for product-based plugin dispatch.

This module provides the PluginSelector class that enables automatic
selection of plugins based on the collections they support. It handles:
- Indexing all registered plugins by their supported collections
- Selecting a single plugin based on requested collections
- Detecting and resolving conflicts when multiple plugins match
"""

from __future__ import annotations

from typing import Any

import pluggy
from aer.plugin.core import get_plugin_type, get_supported_collections


class PluginConflictError(Exception):
    """Raised when multiple plugins match the requested collections.

    Attributes:
        collections: The collections that caused the conflict.
        plugins: List of plugin names that match the requested collections.
    """

    def __init__(self, collections: list[str], plugins: list[str]) -> None:
        self.collections = collections
        self.plugins = plugins
        plugin_list = ", ".join(plugins)
        super().__init__(
            f"Multiple plugins support {collections}: {plugin_list}. "
            f"Use plugin_name parameter to explicitly select one."
        )


class NoMatchingPluginError(Exception):
    """Raised when no plugin supports the requested collections.

    Attributes:
        collections: The collections that were requested.
    """

    def __init__(self, collections: list[str]) -> None:
        self.collections = collections
        super().__init__(
            f"No plugins found supporting any of: {collections}. "
            f"Ensure plugins declare supported_collections class attribute."
        )


class PluginSelector:
    """Selects plugins based on supported collections.

    This class indexes all registered plugins and provides methods
    to select a single plugin based on collection matching.

    Example::

        from aer.plugin import AerSpec, PROJECT_NAME
        import pluggy

        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        pm.load_setuptools_entrypoints("aer.plugins")

        selector = PluginSelector(pm)
        selector.index_plugins()

        # Auto-select plugin for "ABI-L1b-RadF" collection (search type)
        plugin = selector.select(collections=["ABI-L1b-RadF"], plugin_type="search")

        # Explicit selection (bypasses collection matching)
        plugin = selector.select(collections=["ABI-L1b-RadF"], plugin_name="my_plugin")
    """

    def __init__(self, plugin_manager: pluggy.PluginManager) -> None:
        """Initialize the selector with a pluggy PluginManager.

        Args:
            plugin_manager: The pluggy PluginManager instance containing
                registered plugins.
        """
        self._pm = plugin_manager
        self._collection_index: dict[str, list[str]] = {}
        self._plugin_names: dict[int, str] = {}
        self._plugin_types: dict[str, set[str]] = {}
        self._is_indexed = False

    def index_plugins(self, force: bool = False) -> None:
        """Scan all registered plugins and build collection index.

        Builds a mapping from collection identifiers to the list of
        plugin names that support each collection. Also indexes plugin types.

        Args:
            force: If True, rebuilds the index even if already indexed.

        Raises:
            ValueError: If a plugin lacks the supported_collections attribute.
        """
        if self._is_indexed and not force:
            return

        self._collection_index.clear()
        self._plugin_names.clear()
        self._plugin_types.clear()

        # Get all registered plugins
        plugins = self._pm.get_plugins()

        for plugin in plugins:
            # Skip the hookspecs themselves (not actual plugins)
            if plugin is None:
                continue

            # Get plugin name from pluggy
            plugin_name = self._pm.get_name(plugin)
            if plugin_name is None:
                continue

            # Store plugin name mapping
            self._plugin_names[id(plugin)] = plugin_name

            # Get plugin type (required for collection-based dispatch)
            plugin_type = get_plugin_type(self._pm, plugin)
            if not plugin_type:
                continue
            self._plugin_types[plugin_name] = plugin_type

            # Get supported collections
            try:
                collections = get_supported_collections(plugin)
            except ValueError:
                # Skip plugins that don't declare supported_collections
                continue

            # Index each collection
            for collection in collections:
                if collection not in self._collection_index:
                    self._collection_index[collection] = []
                self._collection_index[collection].append(plugin_name)

        self._is_indexed = True

    def select(
        self,
        collections: list[str],
        plugin_type: str | None = None,
        plugin_name: str | None = None,
    ) -> Any:
        """Select a plugin based on collections or explicit name.

        Args:
            collections: List of collection identifiers to match against.
            plugin_type: Optional plugin type filter ("search" or "extract").
                If provided, only plugins of this type are considered.
            plugin_name: Optional explicit plugin name. If provided,
                collection matching is skipped and this plugin is used directly.

        Returns:
            The selected plugin instance.

        Raises:
            PluginConflictError: If multiple plugins match the collections
                and no explicit plugin_name is provided.
            NoMatchingPluginError: If no plugins support the requested collections.
            ValueError: If plugin_type is not "search" or "extract".
        """
        if not self._collection_index:
            raise RuntimeError("No plugins indexed. Call index_plugins() first.")

        if plugin_type is not None and plugin_type not in ("search", "extract"):
            raise ValueError("plugin_type must be 'search' or 'extract'")

        # Explicit plugin selection bypasses collection matching
        if plugin_name:
            plugin = self._pm.get_plugin(plugin_name)
            if plugin is None:
                raise ValueError(f"Plugin '{plugin_name}' not found")
            return plugin

        # Find plugins supporting ANY of the requested collections
        matching_plugins: set[str] = set()
        for requested_collection in collections:
            req_lower = requested_collection.lower()
            for indexed_collection, plugins in self._collection_index.items():
                if indexed_collection.lower() == req_lower:
                    matching_plugins.update(plugins)

        # Filter by plugin type if specified
        if plugin_type:
            matching_plugins = {
                name
                for name in matching_plugins
                if plugin_type in self._plugin_types.get(name, set())
            }

        # Handle results
        if len(matching_plugins) == 0:
            raise NoMatchingPluginError(collections)
        elif len(matching_plugins) == 1:
            plugin_name = next(iter(matching_plugins))
            return self._pm.get_plugin(plugin_name)
        else:
            raise PluginConflictError(collections, list(matching_plugins))

    def get_matching_plugins(
        self, collections: list[str], plugin_type: str | None = None
    ) -> list[str]:
        """Get list of plugin names that support any of the given collections.

        Args:
            collections: List of collection identifiers to match.
            plugin_type: Optional plugin type filter ("search" or "extract").

        Returns:
            List of plugin names that support at least one of the collections.
        """
        if not self._collection_index:
            return []

        matching: set[str] = set()
        for requested_collection in collections:
            req_lower = requested_collection.lower()
            for indexed_collection, plugins in self._collection_index.items():
                if indexed_collection.lower() == req_lower:
                    matching.update(plugins)

        # Filter by plugin type if specified
        if plugin_type:
            matching = {
                name
                for name in matching
                if plugin_type in self._plugin_types.get(name, set())
            }

        return list(matching)

    def list_index(self) -> dict[str, list[str]]:
        """Return a copy of the collection-to-plugins index.

        Returns:
            Dictionary mapping collection identifiers to list of plugin names.
        """
        return dict(self._collection_index)
