"""Tests for the plugin core module.

Verifies that the pluggy-based hookspec system is correctly configured.
"""

import pytest

import pluggy

from aer.plugin import core
from aer.plugin.core import (
    AerSpec,
    get_plugin_type,
    get_supported_collections,
    hookimpl,
)


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


class TestPluginTypeInference:
    """Tests for get_plugin_type using pluggy's get_hookcallers."""

    @pytest.fixture
    def pm(self):
        """Create a PluginManager with AerSpec registered."""
        pm = pluggy.PluginManager(core.PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        return pm

    def test_get_plugin_type_search(self, pm):
        """get_plugin_type returns set with 'search' for search plugins."""

        class SearchPlugin:
            supported_collections = ["goes-16"]

            @hookimpl
            def search(self, collections, intersects, time_range, search_params):
                pass

        plugin = SearchPlugin()
        pm.register(plugin, "search-plugin")
        assert get_plugin_type(pm, plugin) == {"search"}

    def test_get_plugin_type_extract(self, pm):
        """get_plugin_type returns set with 'extract' for extract plugins."""

        class ExtractPlugin:
            supported_collections = ["goes-16"]

            @hookimpl
            def extract(self, task):
                pass

        plugin = ExtractPlugin()
        pm.register(plugin, "extract-plugin")
        assert get_plugin_type(pm, plugin) == {"extract"}

    def test_get_plugin_type_both(self, pm):
        """get_plugin_type returns set with both for plugins with both hooks."""

        class BothPlugin:
            supported_collections = ["goes-16"]

            @hookimpl
            def search(self, collections, intersects, time_range, search_params):
                pass

            @hookimpl
            def extract(self, task):
                pass

        plugin = BothPlugin()
        pm.register(plugin, "both-plugin")
        assert get_plugin_type(pm, plugin) == {"search", "extract"}

    def test_get_plugin_type_no_hooks_returns_empty(self, pm):
        """get_plugin_type returns empty set when plugin has no hooks."""

        class NoHooksPlugin:
            supported_collections = ["goes-16"]

        plugin = NoHooksPlugin()
        pm.register(plugin, "no-hooks-plugin")
        assert get_plugin_type(pm, plugin) == set()

    def test_get_plugin_type_unregistered_returns_empty(self, pm):
        """get_plugin_type returns empty set for unregistered plugin."""

        class SearchPlugin:
            supported_collections = ["goes-16"]

            @hookimpl
            def search(self, collections, intersects, time_range, search_params):
                pass

        plugin = SearchPlugin()
        assert get_plugin_type(pm, plugin) == set()


class TestSupportedProductsAttribute:
    """Tests for supported_collections attribute and get_supported_collections function."""

    def test_supported_collections_attr_constant(self):
        """SUPPORTED_COLLECTIONS_ATTR constant is defined."""
        assert core.SUPPORTED_COLLECTIONS_ATTR == "supported_collections"

    def test_collection_type_alias(self):
        """Collection type alias is str."""
        assert core.Collection is str

    def test_get_supported_collections_single(self):
        """get_supported_collections returns list for single collection."""

        class SingleCollectionPlugin:
            supported_collections = ["goes-16"]

        assert get_supported_collections(SingleCollectionPlugin()) == ["goes-16"]

    def test_get_supported_collections_multiple(self):
        """get_supported_collections returns list for multiple collections."""

        class MultiCollectionPlugin:
            supported_collections = ["goes-16", "goes-18", "modis"]

        assert get_supported_collections(MultiCollectionPlugin()) == [
            "goes-16",
            "goes-18",
            "modis",
        ]

    def test_get_supported_collections_missing_raises(self):
        """get_supported_collections raises ValueError when attribute missing."""

        class NoCollectionsPlugin:
            pass

        with pytest.raises(ValueError, match="must declare 'supported_collections'"):
            get_supported_collections(NoCollectionsPlugin())
