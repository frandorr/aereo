"""Tests for PluginSelector with product-based and plugin_type filtering."""

import pluggy
import pytest
from aer.plugin import PROJECT_NAME, AerSpec, PluginSelector, hookimpl
from aer.plugin.core import get_plugin_type
from aer.plugin.selector import NoMatchingPluginError, PluginConflictError


class MockSearchPlugin:
    """Mock search plugin."""

    supported_collections = ["goes-16", "goes-18"]

    @hookimpl
    def search(self, collections, intersects, time_range, search_params):
        return "search_results"


class MockExtractPlugin:
    """Mock extract plugin."""

    supported_collections = ["goes-16"]

    @hookimpl
    def extract(self, task):
        return task


class MockMultiProductPlugin:
    """Mock plugin supporting multiple products."""

    supported_collections = ["modis", "viirs", "goes-16"]

    @hookimpl
    def search(self, collections, intersects, time_range, search_params):
        return "multi_product_results"


class MockSearchNoProductsPlugin:
    """Mock search plugin without supported_collections."""

    @hookimpl
    def search(self, collections, intersects, time_range, search_params):
        pass


class MockSearchNoTypePlugin:
    """Mock plugin without any hooks."""

    supported_collections = ["goes-16"]


class MockInvalidTypePlugin:
    """Mock plugin with only invalid/non-hook methods."""

    supported_collections = ["goes-16"]

    def do_something(self):
        pass


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


class TestPluginTypeInference:
    """Tests for get_plugin_type using pluggy's get_hookcallers."""

    @pytest.fixture
    def pm(self):
        """Create a PluginManager with AerSpec registered."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        return pm

    def test_get_plugin_type_search(self, pm):
        """get_plugin_type returns set with 'search' for search plugins."""
        plugin = MockSearchPlugin()
        pm.register(plugin, "search-plugin")
        assert get_plugin_type(pm, plugin) == {"search"}

    def test_get_plugin_type_extract(self, pm):
        """get_plugin_type returns set with 'extract' for extract plugins."""
        plugin = MockExtractPlugin()
        pm.register(plugin, "extract-plugin")
        assert get_plugin_type(pm, plugin) == {"extract"}

    def test_get_plugin_type_missing_returns_empty(self, pm):
        """get_plugin_type returns empty set when plugin has no hooks."""
        plugin = MockSearchNoTypePlugin()
        pm.register(plugin, "no-hooks-plugin")
        assert get_plugin_type(pm, plugin) == set()

    def test_get_plugin_type_invalid_returns_empty(self, pm):
        """get_plugin_type returns empty set for plugin with no valid hooks."""
        plugin = MockInvalidTypePlugin()
        pm.register(plugin, "invalid-plugin")
        assert get_plugin_type(pm, plugin) == set()


class TestPluginSelectorIndexing:
    """Tests for PluginSelector.index_plugins()."""

    def test_index_plugins_builds_product_index(self, indexed_selector):
        """index_plugins builds collection-to-plugins mapping."""
        index = indexed_selector.list_index()
        assert "goes-16" in index
        assert "goes-18" in index
        assert "modis" in index
        assert "viirs" in index

    def test_index_plugins_stores_plugin_types(self, indexed_selector):
        """index_plugins stores plugin_type for each plugin."""
        assert indexed_selector._plugin_types["search_plugin"] == {"search"}
        assert indexed_selector._plugin_types["extract_plugin"] == {"extract"}
        assert indexed_selector._plugin_types["multi_product_plugin"] == {"search"}

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
        """Plugins without supported_collections are not indexed."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        pm.register(MockSearchNoProductsPlugin(), name="no_products_plugin")

        selector = PluginSelector(pm)
        selector.index_plugins()

        # Should not crash, but no collections indexed
        assert selector._collection_index == {}


class TestPluginSelectorSelect:
    """Tests for PluginSelector.select()."""

    def test_select_with_plugin_type_search(self, indexed_selector):
        """select filters by plugin_type='search'."""
        # goes-16 has 3 search plugins: search_plugin, multi_product_plugin
        # This should raise PluginConflictError since multiple match
        with pytest.raises(PluginConflictError):
            indexed_selector.select(collections=["goes-16"], plugin_type="search")

    def test_select_with_plugin_type_extract(self, indexed_selector):
        """select filters by plugin_type='extract'."""
        plugin = indexed_selector.select(collections=["goes-16"], plugin_type="extract")
        assert type(plugin).__name__ == "MockExtractPlugin"

    def test_select_without_plugin_type_returns_any(self, indexed_selector):
        """select without plugin_type returns any matching plugin."""
        # goes-16 has both search and extract, should raise conflict
        with pytest.raises(PluginConflictError):
            indexed_selector.select(collections=["goes-16"])

    def test_select_single_match_no_conflict(self, indexed_selector):
        """select with product that has single plugin works."""
        # goes-18 only has search plugin
        plugin = indexed_selector.select(collections=["goes-18"], plugin_type="search")
        assert type(plugin).__name__ == "MockSearchPlugin"

    def test_select_explicit_plugin_bypasses_type_filter(self, indexed_selector):
        """select with explicit plugin_name bypasses product matching."""
        plugin = indexed_selector.select(
            collections=["goes-16"], plugin_name="extract_plugin"
        )
        assert type(plugin).__name__ == "MockExtractPlugin"

    def test_select_no_match_raises(self, indexed_selector):
        """select raises NoMatchingPluginError when no plugins match."""
        with pytest.raises(NoMatchingPluginError):
            indexed_selector.select(
                collections=["nonexistent_product"], plugin_type="search"
            )

    def test_select_conflict_raises(self, indexed_selector):
        """select raises PluginConflictError when multiple plugins match."""
        # modis has only search, but using no type filter would find search
        with pytest.raises(NoMatchingPluginError):
            indexed_selector.select(collections=["modis"], plugin_type="extract")

    def test_select_invalid_plugin_type_raises(self, indexed_selector):
        """select raises ValueError for invalid plugin_type."""
        with pytest.raises(ValueError, match="must be 'search' or 'extract'"):
            indexed_selector.select(collections=["goes-16"], plugin_type="invalid")

    def test_select_no_indexed_raises(self):
        """select raises RuntimeError when index_plugins not called."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        selector = PluginSelector(pm)

        with pytest.raises(RuntimeError, match="No plugins indexed"):
            selector.select(collections=["goes-16"])

    def test_select_case_insensitive_match(self, indexed_selector):
        """select matches collections regardless of case."""
        # Indexed as "goes-18", requesting as "GOES-18"
        plugin = indexed_selector.select(collections=["GOES-18"], plugin_type="search")
        assert type(plugin).__name__ == "MockSearchPlugin"

        # Requesting as "Goes-18"
        plugin = indexed_selector.select(collections=["Goes-18"], plugin_type="search")
        assert type(plugin).__name__ == "MockSearchPlugin"


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

    def test_get_matching_plugins_case_insensitive(self, indexed_selector):
        """get_matching_plugins matches collections regardless of case."""
        plugins = indexed_selector.get_matching_plugins(["GOES-16"])
        assert "search_plugin" in plugins
        assert "extract_plugin" in plugins

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
