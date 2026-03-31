"""Integration tests verifying core-only installation.

Ensures that when only the aer core package is installed (without plugins),
external plugins like earthaccess are not registered in the plugin registry.
"""

from unittest.mock import patch
import pytest
from aer.plugin import plugin_registry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry to avoid test pollution."""
    original_plugins = plugin_registry.plugins.copy()
    original_graph = {k: v.copy() for k, v in plugin_registry.graph.items()}
    plugin_registry.plugins.clear()
    plugin_registry.graph.clear()
    plugin_registry._plugins_loaded = False
    yield
    plugin_registry.plugins = original_plugins
    plugin_registry.graph = original_graph
    plugin_registry._plugins_loaded = True


@pytest.mark.integration
@patch("importlib.metadata.entry_points")
def test_earthaccess_not_registered(mock_entry_points):
    """Verify that earthaccess is NOT registered when only core is installed."""
    mock_entry_points.return_value = []

    names = {m.name for m in plugin_registry.all()}
    assert "earthaccess" not in names
