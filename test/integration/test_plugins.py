"""Integration tests for plugin registration.

Verifies that plugins are correctly registered and discoverable
through the plugin registry.
"""

from typing import Any

import pytest

from aer.plugin import plugin, plugin_registry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry to avoid test pollution."""
    original_plugins = plugin_registry.plugins.copy()
    original_graph = {k: v.copy() for k, v in plugin_registry.graph.items()}
    yield
    plugin_registry.plugins = original_plugins
    plugin_registry.graph = original_graph


def register_test_plugin():
    """Register a test plugin within this test context."""

    @plugin(name="integration-test-search", category="search")
    class IntegrationTestSearchPlugin:
        """A test search plugin for integration tests."""

        def search(self, query: Any, **kwargs: Any) -> dict[str, Any]:
            return {"query": query, "result": "search_ok"}

    return IntegrationTestSearchPlugin


@pytest.mark.integration
def test_plugin_registered():
    """Verify that a plugin can be registered and discovered."""
    # Register the plugin
    register_test_plugin()

    # Verify it's in the registry
    names = {m.name for m in plugin_registry.all()}
    assert "integration-test-search" in names
