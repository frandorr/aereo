"""Integration tests for the pluggy-based plugin system.

Verifies that plugins are correctly registered and discoverable
through the pluggy PluginManager.
"""

from typing import Any

import pluggy
import pytest
from pandera.typing.geopandas import GeoDataFrame

from aer.plugin import AerSpec, hookimpl, PROJECT_NAME


@pytest.fixture
def plugin_manager() -> pluggy.PluginManager:
    """Create a plugin manager with AerSpec registered."""
    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(AerSpec)
    return pm


def create_test_plugin(name: str):
    """Factory to create a test plugin class."""

    class TestPlugin:
        """A test plugin for integration tests."""

        def __init__(self, plugin_name: str):
            self.name = plugin_name
            self.search_calls: list[Any] = []

        @hookimpl
        def search(self, query: Any) -> GeoDataFrame:
            """Search implementation."""
            self.search_calls.append(query)
            return GeoDataFrame()  # type: ignore[return-value]

    # Set class name dynamically for clarity
    TestPlugin.__name__ = name
    return TestPlugin


@pytest.mark.integration
def test_plugin_registration_via_hookimpl(plugin_manager: pluggy.PluginManager) -> None:
    """Verify that a plugin can be registered using @hookimpl."""
    # Create and register a test plugin
    PluginClass = create_test_plugin("IntegrationTestPlugin")
    plugin = PluginClass("integration-test-search")

    plugin_manager.register(plugin)

    # Verify it's in the registry
    hook = plugin_manager.hook.search
    impls = list(hook.get_hookimpls())
    assert len(impls) == 1


@pytest.mark.integration
def test_plugin_hook_is_callable(plugin_manager: pluggy.PluginManager) -> None:
    """Verify that registered hooks are callable."""

    class CallableTestPlugin:
        @hookimpl
        def search(self, query: Any) -> GeoDataFrame:
            return GeoDataFrame()  # type: ignore[return-value]

    plugin_manager.register(CallableTestPlugin())

    # Verify we can access the hook
    assert hasattr(plugin_manager.hook, "search")


@pytest.mark.integration
def test_multiple_plugin_registration(plugin_manager: pluggy.PluginManager) -> None:
    """Verify multiple plugins can be registered."""

    class Plugin1:
        @hookimpl
        def search(self, query: Any) -> GeoDataFrame:
            return GeoDataFrame()  # type: ignore[return-value]

    class Plugin2:
        @hookimpl
        def search(self, query: Any) -> GeoDataFrame:
            return GeoDataFrame()  # type: ignore[return-value]

    plugin_manager.register(Plugin1())
    plugin_manager.register(Plugin2())

    # Verify both are registered
    hook = plugin_manager.hook.search
    assert len(list(hook.get_hookimpls())) == 2


@pytest.mark.integration
def test_all_aerspec_hooks_available(plugin_manager: pluggy.PluginManager) -> None:
    """Verify all AerSpec hooks are available in the manager."""
    expected_hooks = ["search", "prepare_tasks", "extract"]

    for hook_name in expected_hooks:
        assert hasattr(plugin_manager.hook, hook_name), (
            f"Hook {hook_name} not available"
        )


@pytest.mark.integration
def test_plugin_unregister(plugin_manager: pluggy.PluginManager) -> None:
    """Verify plugins can be unregistered."""

    class TempPlugin:
        @hookimpl
        def search(self, query: Any) -> GeoDataFrame:
            return GeoDataFrame()  # type: ignore[return-value]

    plugin = TempPlugin()
    plugin_manager.register(plugin)

    # Verify registration
    assert len(list(plugin_manager.hook.search.get_hookimpls())) == 1

    # Unregister
    plugin_manager.unregister(plugin)

    # Verify unregistration
    assert len(list(plugin_manager.hook.search.get_hookimpls())) == 0
