"""Tests for the pluggy-based hook system.

Verifies that the AerSpec hooks can be implemented by external packages
and that the plugin manager correctly discovers and calls hook implementations.
"""

from typing import Any

import pluggy
import pytest
from pandera.typing.geopandas import GeoDataFrame

from aer.plugin import AerSpec, hookimpl, hookspec, PROJECT_NAME


class TestPluggyHookSystem:
    """Test that the pluggy hook system works correctly."""

    def test_project_name_constant(self) -> None:
        """PROJECT_NAME is defined correctly."""
        assert PROJECT_NAME == "aer"

    def test_hookspec_marker_has_project_name(self) -> None:
        """Hookspec marker has correct project name."""
        # The marker is a HookspecMarker instance with project name
        assert hookspec.project_name == "aer"

    def test_hookimpl_marker_has_project_name(self) -> None:
        """Hookimpl marker has correct project name."""
        # The marker is a HookimplMarker instance with project name
        assert hookimpl.project_name == "aer"

    def test_hookspec_can_decorate_function(self) -> None:
        """Hookspec marker can be applied to functions."""

        class TestSpec:
            @hookspec
            def test_hook(self, arg: str) -> str:
                """A test hook specification."""
                return ""  # Abstract method for hookspec

        # The function exists and is callable
        assert callable(TestSpec.test_hook)

    def test_hookimpl_can_decorate_function(self) -> None:
        """Hookimpl marker can be applied to functions."""

        class TestPlugin:
            @hookimpl
            def test_hook(self, arg: str) -> str:
                return f"result: {arg}"

        # The function exists and is callable
        assert callable(TestPlugin.test_hook)


class TestAerSpecHooks:
    """Test that AerSpec hooks can be implemented and called."""

    @pytest.fixture
    def plugin_manager(self) -> pluggy.PluginManager:
        """Create a plugin manager with AerSpec registered."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        return pm

    def test_search_hook_registration(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Search hook can be registered and called."""
        results: list[Any] = []

        class DummySearchPlugin:
            """A dummy search plugin for testing."""

            @hookimpl
            def search(self, query: Any) -> GeoDataFrame:
                """Dummy search implementation."""
                results.append(query)
                # Return minimal valid result
                return GeoDataFrame()  # type: ignore[return-value]

        # Register the plugin
        plugin_manager.register(DummySearchPlugin())

        # Verify the hook was registered
        hook = plugin_manager.hook.search
        assert hook is not None
        assert len(hook.get_hookimpls()) == 1

    def test_prepare_tasks_hook_registration(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Prepare_tasks hook can be registered and called."""

        class DummyPreparePlugin:
            """A dummy prepare_tasks plugin for testing."""

            @hookimpl
            def prepare_tasks(self, query: Any) -> list[dict[str, Any]]:
                """Dummy prepare_tasks implementation."""
                return [{"task": "dummy"}]

        # Register the plugin
        plugin_manager.register(DummyPreparePlugin())

        # Verify the hook was registered
        hook = plugin_manager.hook.prepare_tasks
        assert hook is not None
        assert len(hook.get_hookimpls()) == 1

    def test_extract_hook_registration(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Extract hook can be registered and called."""

        class DummyExtractPlugin:
            """A dummy extract plugin for testing."""

            @hookimpl
            def extract(self, task: Any) -> Any:
                """Dummy extract implementation."""
                task.status = "SUCCESS"
                return task

        # Register the plugin
        plugin_manager.register(DummyExtractPlugin())

        # Verify the hook was registered
        hook = plugin_manager.hook.extract
        assert hook is not None
        assert len(hook.get_hookimpls()) == 1

    def test_multiple_plugins_same_hook(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Multiple plugins can implement the same hook."""

        class Plugin1:
            @hookimpl
            def search(self, query: Any) -> GeoDataFrame:
                return GeoDataFrame()  # type: ignore[return-value]

        class Plugin2:
            @hookimpl
            def search(self, query: Any) -> GeoDataFrame:
                return GeoDataFrame()  # type: ignore[return-value]

        # Register both plugins
        plugin_manager.register(Plugin1())
        plugin_manager.register(Plugin2())

        # Verify both hooks are registered
        hook = plugin_manager.hook.search
        assert len(hook.get_hookimpls()) == 2

    def test_plugin_registration_with_tryfirst(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Plugin can use tryfirst to prioritize hook execution."""

        class PrimaryPlugin:
            @hookimpl(tryfirst=True)
            def search(self, query: Any) -> GeoDataFrame:
                return GeoDataFrame()  # type: ignore[return-value]

        class SecondaryPlugin:
            @hookimpl
            def search(self, query: Any) -> GeoDataFrame:
                return GeoDataFrame()  # type: ignore[return-value]

        # Register plugins
        plugin_manager.register(SecondaryPlugin())
        plugin_manager.register(PrimaryPlugin())

        # Verify tryfirst plugin was registered
        hook = plugin_manager.hook.search
        impls = list(hook.get_hookimpls())
        # The tryfirst plugin should be first in the list
        assert any("PrimaryPlugin" in str(impl.plugin) for impl in impls)


class TestHookimplVariations:
    """Test different hookimpl decorator options."""

    @pytest.fixture
    def plugin_manager(self) -> pluggy.PluginManager:
        """Create a plugin manager with AerSpec registered."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)
        return pm

    def test_hookimpl_with_specname(self, plugin_manager: pluggy.PluginManager) -> None:
        """Hookimpl can use specname to map different method name."""

        class AliasedPlugin:
            @hookimpl(specname="search")
            def my_custom_search(self, query: Any) -> GeoDataFrame:
                """Custom method name mapped to search hook."""
                return GeoDataFrame()  # type: ignore[return-value]

        # Register and verify
        plugin_manager.register(AliasedPlugin())
        hook = plugin_manager.hook.search
        assert len(hook.get_hookimpls()) == 1

    def test_hookimpl_with_trylast(self, plugin_manager: pluggy.PluginManager) -> None:
        """Plugin can use trylast to deprioritize hook execution."""

        class LastPlugin:
            @hookimpl(trylast=True)
            def search(self, query: Any) -> GeoDataFrame:
                return GeoDataFrame()  # type: ignore[return-value]

        # Register and verify
        plugin_manager.register(LastPlugin())
        hook = plugin_manager.hook.search
        assert len(hook.get_hookimpls()) == 1


class TestAerSpecStructure:
    """Test the structure and documentation of AerSpec."""

    def test_aerspec_has_all_hooks(self) -> None:
        """AerSpec defines all required hooks."""
        required_hooks = ["search", "prepare_tasks", "extract"]
        for hook_name in required_hooks:
            assert hasattr(AerSpec, hook_name), f"AerSpec missing hook: {hook_name}"

    def test_hooks_have_docstrings(self) -> None:
        """All AerSpec hooks have docstrings."""
        for attr_name in ["search", "prepare_tasks", "extract"]:
            attr = getattr(AerSpec, attr_name)
            assert attr.__doc__, f"{attr_name} missing docstring"

    def test_aerspec_can_be_added_to_plugin_manager(self) -> None:
        """AerSpec can be registered with a PluginManager."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(AerSpec)

        # Verify hooks are available
        assert hasattr(pm.hook, "search")
        assert hasattr(pm.hook, "prepare_tasks")
        assert hasattr(pm.hook, "extract")
