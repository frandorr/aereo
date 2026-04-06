"""Tests for the public plugin API.

Verifies the pluggy-based plugin system exports work correctly.
"""

import pluggy

from aer.plugin import (
    AerSpec,
    hookimpl,
    hookspec,
    PROJECT_NAME,
)


def test_public_api_exports():
    """Public API exports all required components."""
    # Main hook specification class
    assert AerSpec is not None

    # Decorators for plugin authors
    assert hookimpl is not None
    assert hookspec is not None

    # Project identifier
    assert PROJECT_NAME == "aer"


def test_hookimpl_works_with_plugin_manager():
    """Plugin authors can use hookimpl decorator - works with plugin manager."""
    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(AerSpec)

    class TestPlugin:
        @hookimpl
        def search(self, query):
            return None

    # Should be able to register without errors
    plugin = TestPlugin()
    pm.register(plugin)

    # Verify registration worked
    assert len(list(pm.hook.search.get_hookimpls())) == 1


def test_hookspec_can_be_used():
    """Custom specs can use hookspec decorator."""

    class CustomSpec:
        @hookspec
        def custom_hook(self):
            """A custom hook."""
            ...

    assert callable(CustomSpec.custom_hook)
