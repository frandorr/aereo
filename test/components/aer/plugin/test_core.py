"""Tests for the plugin core module.

Verifies that the pluggy-based hookspec system is correctly configured.
"""

import pytest

from aer.plugin import core
from aer.plugin.core import get_plugin_type, get_supported_products


def test_core_exports():
    """Core module exports required pluggy components."""
    assert hasattr(core, "PROJECT_NAME")
    assert hasattr(core, "hookspec")
    assert hasattr(core, "hookimpl")
    assert hasattr(core, "AerSpec")


def test_project_name():
    """PROJECT_NAME is correctly set."""
    assert core.PROJECT_NAME == "aer"


def test_aerspec_has_all_hooks():
    """AerSpec defines all required hooks."""
    required_hooks = ["search", "prepare_tasks", "extract"]
    for hook_name in required_hooks:
        assert hasattr(core.AerSpec, hook_name), f"AerSpec missing hook: {hook_name}"


def test_all_hooks_are_callable():
    """All AerSpec hooks are callable methods."""
    for attr_name in ["search", "prepare_tasks", "extract"]:
        attr = getattr(core.AerSpec, attr_name)
        assert callable(attr), f"{attr_name} is not callable"


class TestPluginTypeAttribute:
    """Tests for plugin_type attribute and get_plugin_type function."""

    def test_plugin_type_attr_constant(self):
        """PLUGIN_TYPE_ATTR constant is defined."""
        assert core.PLUGIN_TYPE_ATTR == "plugin_type"

    def test_get_plugin_type_search(self):
        """get_plugin_type returns 'search' for search plugins."""

        class SearchPlugin:
            plugin_type = "search"

        assert get_plugin_type(SearchPlugin()) == "search"

    def test_get_plugin_type_extract(self):
        """get_plugin_type returns 'extract' for extract plugins."""

        class ExtractPlugin:
            plugin_type = "extract"

        assert get_plugin_type(ExtractPlugin()) == "extract"

    def test_get_plugin_type_missing_raises(self):
        """get_plugin_type raises ValueError when attribute missing."""

        class NoTypePlugin:
            pass

        with pytest.raises(ValueError, match="must declare plugin_type"):
            get_plugin_type(NoTypePlugin())

    def test_get_plugin_type_invalid_value_raises(self):
        """get_plugin_type raises ValueError for invalid value."""

        class InvalidTypePlugin:
            plugin_type = "invalid"

        with pytest.raises(ValueError, match="must be 'search' or 'extract'"):
            get_plugin_type(InvalidTypePlugin())


class TestSupportedProductsAttribute:
    """Tests for supported_products attribute and get_supported_products function."""

    def test_supported_products_attr_constant(self):
        """SUPPORTED_PRODUCTS_ATTR constant is defined."""
        assert core.SUPPORTED_PRODUCTS_ATTR == "supported_products"

    def test_product_type_alias(self):
        """Product type alias is str."""
        assert core.Product is str

    def test_get_supported_products_single(self):
        """get_supported_products returns list for single product."""

        class SingleProductPlugin:
            supported_products = ["goes-16"]

        assert get_supported_products(SingleProductPlugin()) == ["goes-16"]

    def test_get_supported_products_multiple(self):
        """get_supported_products returns list for multiple products."""

        class MultiProductPlugin:
            supported_products = ["goes-16", "goes-18", "modis"]

        assert get_supported_products(MultiProductPlugin()) == [
            "goes-16",
            "goes-18",
            "modis",
        ]

    def test_get_supported_products_missing_raises(self):
        """get_supported_products raises ValueError when attribute missing."""

        class NoProductsPlugin:
            pass

        with pytest.raises(ValueError, match="must declare supported_products"):
            get_supported_products(NoProductsPlugin())

    def test_get_supported_products_not_list_raises(self):
        """get_supported_products raises ValueError when not a list."""

        class NotListPlugin:
            supported_products = "goes-16"

        with pytest.raises(ValueError, match="must be a list"):
            get_supported_products(NotListPlugin())
