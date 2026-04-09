"""Plugin selector for product-based plugin dispatch.

This module provides the PluginSelector class that enables automatic
selection of plugins based on the products they support. It handles:
- Indexing all registered plugins by their supported products
- Selecting a single plugin based on requested products
- Detecting and resolving conflicts when multiple plugins match
"""

from __future__ import annotations

from typing import Any

import pluggy

from aer.plugin.core import get_supported_products


class PluginConflictError(Exception):
    """Raised when multiple plugins match the requested products.

    Attributes:
        products: The products that caused the conflict.
        plugins: List of plugin names that match the requested products.
    """

    def __init__(self, products: list[str], plugins: list[str]) -> None:
        self.products = products
        self.plugins = plugins
        plugin_list = ", ".join(plugins)
        super().__init__(
            f"Multiple plugins support {products}: {plugin_list}. "
            f"Use plugin_name parameter to explicitly select one."
        )


class NoMatchingPluginError(Exception):
    """Raised when no plugin supports the requested products.

    Attributes:
        products: The products that were requested.
    """

    def __init__(self, products: list[str]) -> None:
        self.products = products
        super().__init__(
            f"No plugins found supporting any of: {products}. "
            f"Ensure plugins declare supported_products class attribute."
        )


class PluginSelector:
    """Selects plugins based on supported products.

    This class indexes all registered plugins and provides methods
    to select a single plugin based on product matching.

    Example::

        from aer.plugin import AerSpec, PROJECT_NAME
        import pluggy

        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        pm.load_setuptools_entrypoints("aer.plugins")

        selector = PluginSelector(pm)
        selector.index_plugins()

        # Auto-select plugin for "goes-16" product
        plugin = selector.select(products=["goes-16"])

        # Explicit selection (bypasses product matching)
        plugin = selector.select(products=["goes-16"], plugin_name="my_plugin")
    """

    def __init__(self, plugin_manager: pluggy.PluginManager) -> None:
        """Initialize the selector with a pluggy PluginManager.

        Args:
            plugin_manager: The pluggy PluginManager instance containing
                registered plugins.
        """
        self._pm = plugin_manager
        self._product_index: dict[str, list[str]] = {}
        self._plugin_names: dict[int, str] = {}

    def index_plugins(self) -> None:
        """Scan all registered plugins and build product index.

        Builds a mapping from product identifiers to the list of
        plugin names that support each product.

        Raises:
            ValueError: If a plugin lacks the supported_products attribute.
        """
        self._product_index.clear()
        self._plugin_names.clear()

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

            # Get supported products
            try:
                products = get_supported_products(plugin)
            except ValueError:
                # Skip plugins that don't declare supported_products
                # (they may not be intended for product-based dispatch)
                continue

            # Index each product
            for product in products:
                if product not in self._product_index:
                    self._product_index[product] = []
                self._product_index[product].append(plugin_name)

    def select(
        self,
        products: list[str],
        plugin_name: str | None = None,
    ) -> Any:
        """Select a plugin based on products or explicit name.

        Args:
            products: List of product identifiers to match against.
            plugin_name: Optional explicit plugin name. If provided,
                product matching is skipped and this plugin is used directly.

        Returns:
            The selected plugin instance.

        Raises:
            PluginConflictError: If multiple plugins match the products
                and no explicit plugin_name is provided.
            NoMatchingPluginError: If no plugins support the requested products.
        """
        if not self._product_index:
            raise RuntimeError("No plugins indexed. Call index_plugins() first.")

        # Explicit plugin selection bypasses product matching
        if plugin_name:
            plugin = self._pm.get_plugin(plugin_name)
            if plugin is None:
                raise ValueError(f"Plugin '{plugin_name}' not found")
            return plugin

        # Find plugins supporting ANY of the requested products
        matching_plugins: set[str] = set()
        for product in products:
            if product in self._product_index:
                matching_plugins.update(self._product_index[product])

        # Handle results
        if len(matching_plugins) == 0:
            raise NoMatchingPluginError(products)
        elif len(matching_plugins) == 1:
            plugin_name = next(iter(matching_plugins))
            return self._pm.get_plugin(plugin_name)
        else:
            raise PluginConflictError(products, list(matching_plugins))

    def get_matching_plugins(self, products: list[str]) -> list[str]:
        """Get list of plugin names that support any of the given products.

        Args:
            products: List of product identifiers to match.

        Returns:
            List of plugin names that support at least one of the products.
        """
        if not self._product_index:
            return []

        matching: set[str] = set()
        for product in products:
            if product in self._product_index:
                matching.update(self._product_index[product])

        return list(matching)

    def list_index(self) -> dict[str, list[str]]:
        """Return a copy of the product-to-plugins index.

        Returns:
            Dictionary mapping product identifiers to list of plugin names.
        """
        return dict(self._product_index)
