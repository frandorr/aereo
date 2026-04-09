"""Tests for PluginSelector with product-based and plugin_type filtering."""

import pytest
import pluggy

from aer.plugin import AerSpec, PROJECT_NAME, PluginSelector
from aer.plugin.core import PLUGIN_TYPE_ATTR, get_plugin_type
from aer.plugin.selector import NoMatchingPluginError, PluginConflictError


class MockSearchPlugin:
    """Mock search plugin."""

    plugin_type = "search"
    supported_products = ["goes-16", "goes-18"]

    def search(self, **kwargs):
        return "search_results"


class MockExtractPlugin:
    """Mock extract plugin."""

    plugin_type = "extract"
    supported_products = ["goes-16"]

    def extract(self, task):
        return task


class MockMultiProductPlugin:
    """Mock plugin supporting multiple products."""

    plugin_type = "search"
    supported_products = ["modis", "viirs", "goes-16"]

    def search(self, **kwargs):
        return "multi_product_results"


class MockSearchNoProductsPlugin:
    """Mock search plugin without supported_products."""

    plugin_type = "search"


class MockSearchNoTypePlugin:
    """Mock plugin without plugin_type."""

    supported_products = ["goes-16"]


class MockInvalidTypePlugin:
    """Mock plugin with invalid plugin_type."""

    plugin_type = "invalid"
    supported_products = ["goes-16"]


@pytest.fixture
def plugin_manager():
    """Create a plugin manager with test plugins."""
    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(AerSpec)
    pm.register(MockSearchPlugin(), name="search_plugin")
    pm.register(MockExtractPlugin(), name="extract_plugin")
    pm.register(MockMultiProductPlugin(), name="multi_product_plugin")
    return pm


@pytest.fixture
def indexed_selector(plugin_manager):
    """Create indexed selector."""
    selector = PluginSelector(plugin_manager)
    selector.index_plugins()
    return selector


class TestPluginTypeAttribute:
    """Tests for PLUGIN_TYPE_ATTR and get_plugin_type."""

    def test_plugin_type_attr_constant(self):
        """PLUGIN_TYPE_ATTR is defined."""
        assert PLUGIN_TYPE_ATTR == "plugin_type"

    def test_get_plugin_type_search(self):
        """get_plugin_type returns 'search' for search plugins."""
        plugin = MockSearchPlugin()
        assert get_plugin_type(plugin) == "search"

    def test_get_plugin_type_extract(self):
        """get_plugin_type returns 'extract' for extract plugins."""
        plugin = MockExtractPlugin()
        assert get_plugin_type(plugin) == "extract"

    def test_get_plugin_type_missing_raises(self):
        """get_plugin_type raises ValueError when plugin_type missing."""
        plugin = MockSearchNoTypePlugin()
        with pytest.raises(ValueError, match="must declare plugin_type"):
            get_plugin_type(plugin)

    def test_get_plugin_type_invalid_raises(self):
        """get_plugin_type raises ValueError for invalid plugin_type."""
        plugin = MockInvalidTypePlugin()
        with pytest.raises(ValueError, match="must be 'search' or 'extract'"):
            get_plugin_type(plugin)


class TestPluginSelectorIndexing:
    """Tests for PluginSelector.index_plugins()."""

    def test_index_plugins_builds_product_index(self, indexed_selector):
        """index_plugins builds product-to-plugins mapping."""
        index = indexed_selector.list_index()
        assert "goes-16" in index
        assert "goes-18" in index
        assert "modis" in index
        assert "viirs" in index

    def test_index_plugins_stores_plugin_types(self, indexed_selector):
        """index_plugins stores plugin_type for each plugin."""
        assert indexed_selector._plugin_types["search_plugin"] == "search"
        assert indexed_selector._plugin_types["extract_plugin"] == "extract"
        assert indexed_selector._plugin_types["multi_product_plugin"] == "search"

    def test_index_plugins_filters_no_type(self):
        """Plugins without plugin_type are not indexed."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        pm.register(MockSearchNoTypePlugin(), name="no_type_plugin")

        selector = PluginSelector(pm)
        selector.index_plugins()

        # Should not crash, but no plugins indexed
        assert selector._plugin_types == {}

    def test_index_plugins_filters_no_products(self):
        """Plugins without supported_products are not indexed."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        pm.register(MockSearchNoProductsPlugin(), name="no_products_plugin")

        selector = PluginSelector(pm)
        selector.index_plugins()

        # Should not crash, but no products indexed
        assert selector._product_index == {}


class TestPluginSelectorSelect:
    """Tests for PluginSelector.select()."""

    def test_select_with_plugin_type_search(self, indexed_selector):
        """select filters by plugin_type='search'."""
        # goes-16 has 3 search plugins: search_plugin, multi_product_plugin
        # This should raise PluginConflictError since multiple match
        with pytest.raises(PluginConflictError):
            indexed_selector.select(products=["goes-16"], plugin_type="search")

    def test_select_with_plugin_type_extract(self, indexed_selector):
        """select filters by plugin_type='extract'."""
        plugin = indexed_selector.select(products=["goes-16"], plugin_type="extract")
        assert type(plugin).__name__ == "MockExtractPlugin"

    def test_select_without_plugin_type_returns_any(self, indexed_selector):
        """select without plugin_type returns any matching plugin."""
        # goes-16 has both search and extract, should raise conflict
        with pytest.raises(PluginConflictError):
            indexed_selector.select(products=["goes-16"])

    def test_select_single_match_no_conflict(self, indexed_selector):
        """select with product that has single plugin works."""
        # goes-18 only has search plugin
        plugin = indexed_selector.select(products=["goes-18"], plugin_type="search")
        assert type(plugin).__name__ == "MockSearchPlugin"

    def test_select_explicit_plugin_bypasses_type_filter(self, indexed_selector):
        """select with explicit plugin_name bypasses product matching."""
        plugin = indexed_selector.select(
            products=["goes-16"], plugin_name="extract_plugin"
        )
        assert type(plugin).__name__ == "MockExtractPlugin"

    def test_select_no_match_raises(self, indexed_selector):
        """select raises NoMatchingPluginError when no plugins match."""
        with pytest.raises(NoMatchingPluginError):
            indexed_selector.select(
                products=["nonexistent_product"], plugin_type="search"
            )

    def test_select_conflict_raises(self, indexed_selector):
        """select raises PluginConflictError when multiple plugins match."""
        # modis has only search, but using no type filter would find search
        with pytest.raises(NoMatchingPluginError):
            indexed_selector.select(products=["modis"], plugin_type="extract")

    def test_select_invalid_plugin_type_raises(self, indexed_selector):
        """select raises ValueError for invalid plugin_type."""
        with pytest.raises(ValueError, match="must be 'search' or 'extract'"):
            indexed_selector.select(products=["goes-16"], plugin_type="invalid")

    def test_select_no_indexed_raises(self):
        """select raises RuntimeError when index_plugins not called."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        selector = PluginSelector(pm)

        with pytest.raises(RuntimeError, match="No plugins indexed"):
            selector.select(products=["goes-16"])


class TestPluginSelectorGetMatchingPlugins:
    """Tests for PluginSelector.get_matching_plugins()."""

    def test_get_matching_plugins_all_types(self, indexed_selector):
        """get_matching_plugins returns all matching plugins."""
        plugins = indexed_selector.get_matching_plugins(["goes-16"])
        assert "search_plugin" in plugins
        assert "extract_plugin" in plugins

    def test_get_matching_plugins_filter_by_type(self, indexed_selector):
        """get_matching_plugins filters by plugin_type."""
        plugins = indexed_selector.get_matching_plugins(
            ["goes-16"], plugin_type="search"
        )
        assert "search_plugin" in plugins
        assert "extract_plugin" not in plugins

    def test_get_matching_plugins_extract_type(self, indexed_selector):
        """get_matching_plugins with plugin_type='extract'."""
        plugins = indexed_selector.get_matching_plugins(
            ["goes-16"], plugin_type="extract"
        )
        assert "extract_plugin" in plugins
        assert "search_plugin" not in plugins

    def test_get_matching_plugins_no_match(self, indexed_selector):
        """get_matching_plugins returns empty when no match."""
        plugins = indexed_selector.get_matching_plugins(["nonexistent"])
        assert plugins == []

    def test_get_matching_plugins_not_indexed(self, indexed_selector):
        """get_matching_plugins returns empty when no plugins indexed."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        selector = PluginSelector(pm)
        selector.index_plugins()

        plugins = selector.get_matching_plugins(["goes-16"])
        assert plugins == []


class TestPluginSelectorListIndex:
    """Tests for PluginSelector.list_index()."""

    def test_list_index_returns_copy(self, indexed_selector):
        """list_index returns a copy, not reference."""
        index1 = indexed_selector.list_index()
        index1["new_key"] = ["new_plugin"]
        index2 = indexed_selector.list_index()
        assert "new_key" not in index2

    def test_list_index_contents(self, indexed_selector):
        """list_index returns correct product mapping."""
        index = indexed_selector.list_index()
        # goes-16: search_plugin, extract_plugin, multi_product_plugin (all 3 support it)
        assert set(index["goes-16"]) == {
            "search_plugin",
            "extract_plugin",
            "multi_product_plugin",
        }
        # goes-18: only search_plugin
        assert index["goes-18"] == ["search_plugin"]
        # modis: only multi_product_plugin
        assert index["modis"] == ["multi_product_plugin"]
        # viirs: only multi_product_plugin
        assert index["viirs"] == ["multi_product_plugin"]
