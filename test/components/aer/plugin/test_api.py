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


class TestPluginTypeAPI:
    """Tests for plugin_type related exports."""

    def test_plugin_type_attr_exported(self):
        """PLUGIN_TYPE_ATTR is exported from aer.plugin."""
        from aer.plugin import PLUGIN_TYPE_ATTR

        assert PLUGIN_TYPE_ATTR == "plugin_type"

    def test_get_plugin_type_exported(self):
        """get_plugin_type is exported from aer.plugin."""
        from aer.plugin import get_plugin_type

        assert callable(get_plugin_type)


class TestSelectorAPI:
    """Tests for PluginSelector in public API."""

    def test_selector_exported(self):
        """PluginSelector is exported from aer.plugin."""
        from aer.plugin import PluginSelector

        assert PluginSelector is not None

    def test_selector_exceptions_exported(self):
        """Selector exceptions are exported."""
        from aer.plugin import NoMatchingPluginError, PluginConflictError

        assert issubclass(NoMatchingPluginError, Exception)
        assert issubclass(PluginConflictError, Exception)
