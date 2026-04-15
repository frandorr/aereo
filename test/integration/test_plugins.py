"""Integration tests for the pluggy-based plugin system.

Verifies that plugins are correctly registered and discoverable
through the pluggy PluginManager.
"""

from typing import Any

import pluggy
import pytest
from aer.hookspecs import (
    PROJECT_NAME,
    hookimpl,
)
from aer.hookspecs import core as hookspecs_core
from aer.plugin import PluginSelector
from aer.plugin.api import run_search
from pandera.typing.geopandas import GeoDataFrame


@pytest.fixture
def selector(plugin_manager: pluggy.PluginManager) -> PluginSelector:
    """Create a PluginSelector for the manager."""
    return PluginSelector(plugin_manager)


@pytest.fixture
def plugin_manager() -> pluggy.PluginManager:
    """Create a plugin manager with hookspecs registered."""
    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(hookspecs_core)
    return pm


@pytest.mark.integration
def test_plugin_selection_by_collection(
    plugin_manager: pluggy.PluginManager, selector: PluginSelector
) -> None:
    """Verify plugins can be selected by supported collections."""

    class CollectionPlugin:
        supported_collections = ["my-collection"]

        @hookimpl
        def search(
            self, collections, intersects, start_datetime, end_datetime, search_params
        ) -> GeoDataFrame:
            return GeoDataFrame()

    plugin = CollectionPlugin()
    plugin_manager.register(plugin, name="my-plugin")
    selector.index_plugins(force=True)

    selected = selector.select(collections=["my-collection"], plugin_type="search")
    assert selected == plugin


@pytest.mark.integration
def test_run_search_with_collection_dispatch(
    monkeypatch: pytest.MonkeyPatch, plugin_manager: pluggy.PluginManager
) -> None:
    """Verify run_search uses collection-based dispatch."""

    class MockSearchPlugin:
        supported_collections = ["goes-16"]

        @hookimpl
        def search(
            self,
            collections: list[str],
            intersects: Any | None,
            start_datetime: Any | None,
            end_datetime: Any | None,
            search_params: dict[str, Any] | None,
        ) -> GeoDataFrame:
            import pandas as pd

            return pd.DataFrame({"called": [True]})

    plugin = MockSearchPlugin()
    plugin_manager.register(plugin, name="goes-plugin")

    import aer.plugin.api

    monkeypatch.setattr(aer.plugin.api, "_get_plugin_manager", lambda: plugin_manager)
    monkeypatch.setattr(aer.plugin.api, "_plugin_selector", None)

    results = run_search(collections=["goes-16"])
    assert results is not None
    assert not results.empty
    assert results.iloc[0]["called"]


def create_test_plugin(name: str):
    """Factory to create a test plugin class."""

    class TestPlugin:
        """A test plugin for integration tests."""

        supported_collections = ["test-collection"]

        def __init__(self, plugin_name: str):
            self.name = plugin_name
            self.search_calls: list[Any] = []

        @hookimpl
        def search(
            self,
            collections: list[str],
            intersects: Any | None,
            start_datetime: Any | None,
            end_datetime: Any | None,
            search_params: dict[str, Any] | None,
        ) -> GeoDataFrame:
            """Search implementation."""
            self.search_calls.append(collections)
            return GeoDataFrame()

    TestPlugin.__name__ = name
    return TestPlugin


@pytest.mark.integration
def test_plugin_registration_via_hookimpl(plugin_manager: pluggy.PluginManager) -> None:
    """Verify that a plugin can be registered using @hookimpl."""
    PluginClass = create_test_plugin("IntegrationTestPlugin")
    plugin = PluginClass("integration-test-search")

    plugin_manager.register(plugin)

    hook = plugin_manager.hook.search
    impls = list(hook.get_hookimpls())
    assert len(impls) == 1


@pytest.mark.integration
def test_plugin_hook_is_callable(plugin_manager: pluggy.PluginManager) -> None:
    """Verify that registered hooks are callable."""

    class CallableTestPlugin:
        supported_collections = ["test-collection"]

        @hookimpl
        def search(
            self,
            collections: list[str],
            intersects: Any | None,
            start_datetime: Any | None,
            end_datetime: Any | None,
            search_params: dict[str, Any] | None,
        ) -> GeoDataFrame:
            return GeoDataFrame()

    plugin_manager.register(CallableTestPlugin())

    assert hasattr(plugin_manager.hook, "search")


@pytest.mark.integration
def test_multiple_plugin_registration(plugin_manager: pluggy.PluginManager) -> None:
    """Verify multiple plugins can be registered."""

    class Plugin1:
        supported_collections = ["test-collection"]

        @hookimpl
        def search(
            self,
            collections: list[str],
            intersects: Any | None,
            start_datetime: Any | None,
            end_datetime: Any | None,
            search_params: dict[str, Any] | None,
        ) -> GeoDataFrame:
            return GeoDataFrame()

    class Plugin2:
        supported_collections = ["test-collection"]

        @hookimpl
        def search(
            self,
            collections: list[str],
            intersects: Any | None,
            start_datetime: Any | None,
            end_datetime: Any | None,
            search_params: dict[str, Any] | None,
        ) -> GeoDataFrame:
            return GeoDataFrame()

    plugin_manager.register(Plugin1())
    plugin_manager.register(Plugin2())

    hook = plugin_manager.hook.search
    assert len(list(hook.get_hookimpls())) == 2


@pytest.mark.integration
def test_all_hooks_available(plugin_manager: pluggy.PluginManager) -> None:
    """Verify all hookspecs are available in the manager."""
    expected_hooks = [
        "supported_collections",
        "search",
        "prepare_for_extraction",
        "extract",
    ]

    for hook_name in expected_hooks:
        assert hasattr(plugin_manager.hook, hook_name), (
            f"Hook {hook_name} not available"
        )


@pytest.mark.integration
def test_plugin_unregister(plugin_manager: pluggy.PluginManager) -> None:
    """Verify plugins can be unregistered."""

    class TempPlugin:
        supported_collections = ["test-collection"]

        @hookimpl
        def search(
            self,
            collections: list[str],
            intersects: Any | None,
            start_datetime: Any | None,
            end_datetime: Any | None,
            search_params: dict[str, Any] | None,
        ) -> GeoDataFrame:
            return GeoDataFrame()

    plugin = TempPlugin()
    plugin_manager.register(plugin)

    assert len(list(plugin_manager.hook.search.get_hookimpls())) == 1

    plugin_manager.unregister(plugin)

    assert len(list(plugin_manager.hook.search.get_hookimpls())) == 0
