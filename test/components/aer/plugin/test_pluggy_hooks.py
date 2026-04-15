"""Tests for the pluggy-based hook system.

Verifies that the hookspecs can be implemented by external packages
and that the plugin manager correctly discovers and calls hook implementations.
"""

from typing import Any

import pluggy
import pytest
from pandera.typing.geopandas import GeoDataFrame

from aer.hookspecs import (
    PROJECT_NAME,
    hookimpl,
    hookspec,
)
from aer.hookspecs import core as hookspecs_core


class TestPluggyHookSystem:
    """Test that the pluggy hook system works correctly."""

    def test_project_name_constant(self) -> None:
        """PROJECT_NAME is defined correctly."""
        assert PROJECT_NAME == "aer"

    def test_hookspec_marker_has_project_name(self) -> None:
        """Hookspec marker has correct project name."""
        assert hookspec.project_name == "aer"

    def test_hookimpl_marker_has_project_name(self) -> None:
        """Hookimpl marker has correct project name."""
        assert hookimpl.project_name == "aer"

    def test_hookspec_can_decorate_function(self) -> None:
        """Hookspec marker can be applied to functions."""

        class TestSpec:
            @hookspec
            def test_hook(self, arg: str) -> str:
                """A test hook specification."""
                return ""

        assert callable(TestSpec.test_hook)

    def test_hookimpl_can_decorate_function(self) -> None:
        """Hookimpl marker can be applied to functions."""

        class TestPlugin:
            @hookimpl
            def test_hook(self, arg: str) -> str:
                return f"result: {arg}"

        assert callable(TestPlugin.test_hook)


class TestHookRegistration:
    """Test that hooks can be implemented and called."""

    @pytest.fixture
    def plugin_manager(self) -> pluggy.PluginManager:
        """Create a plugin manager with hookspecs registered."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(hookspecs_core)
        return pm

    def test_search_hook_registration(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Search hook can be registered and called."""

        class DummySearchPlugin:
            """A dummy search plugin for testing."""

            supported_collections = ["test-collection"]

            @hookimpl
            def search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ) -> GeoDataFrame:
                return GeoDataFrame()

        plugin_manager.register(DummySearchPlugin())

        hook = plugin_manager.hook.search
        assert hook is not None
        assert len(hook.get_hookimpls()) == 1

    def test_prepare_for_extraction_hook_registration(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """prepare_for_extraction hook can be registered and called."""

        class DummyPreparePlugin:
            """A dummy prepare_for_extraction plugin for testing."""

            supported_collections = ["test-collection"]

            @hookimpl
            def prepare_for_extraction(
                self,
                search_results,
                prepare_params,
            ) -> list:
                return []

        plugin_manager.register(DummyPreparePlugin())

        hook = plugin_manager.hook.prepare_for_extraction
        assert hook is not None
        assert len(hook.get_hookimpls()) == 1

    def test_extract_hook_registration(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Extract hook can be registered and called."""

        class DummyExtractPlugin:
            """A dummy extract plugin for testing."""

            supported_collections = ["test-collection"]

            @hookimpl
            def extract(self, assets_batch, extract_params):
                return GeoDataFrame()

        plugin_manager.register(DummyExtractPlugin())

        hook = plugin_manager.hook.extract
        assert hook is not None
        assert len(hook.get_hookimpls()) == 1

    def test_multiple_plugins_same_hook(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Multiple plugins can implement the same hook."""

        class Plugin1:
            supported_collections = ["test-collection"]

            @hookimpl
            def search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ):
                return GeoDataFrame()

        class Plugin2:
            supported_collections = ["test-collection"]

            @hookimpl
            def search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ):
                return GeoDataFrame()

        plugin_manager.register(Plugin1())
        plugin_manager.register(Plugin2())

        hook = plugin_manager.hook.search
        assert len(hook.get_hookimpls()) == 2

    def test_plugin_registration_with_tryfirst(
        self, plugin_manager: pluggy.PluginManager
    ) -> None:
        """Plugin can use tryfirst to prioritize hook execution."""

        class PrimaryPlugin:
            supported_collections = ["test-collection"]

            @hookimpl(tryfirst=True)
            def search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ):
                return GeoDataFrame()

        class SecondaryPlugin:
            supported_collections = ["test-collection"]

            @hookimpl
            def search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ):
                return GeoDataFrame()

        plugin_manager.register(SecondaryPlugin())
        plugin_manager.register(PrimaryPlugin())

        hook = plugin_manager.hook.search
        impls = list(hook.get_hookimpls())
        assert any("PrimaryPlugin" in str(impl.plugin) for impl in impls)


class TestHookimplVariations:
    """Test different hookimpl decorator options."""

    @pytest.fixture
    def plugin_manager(self) -> pluggy.PluginManager:
        """Create a plugin manager with hookspecs registered."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(hookspecs_core)
        return pm

    def test_hookimpl_with_specname(self, plugin_manager: pluggy.PluginManager) -> None:
        """Hookimpl can use specname to map different method name."""

        class AliasedPlugin:
            supported_collections = ["test-collection"]

            @hookimpl(specname="search")
            def my_custom_search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ) -> GeoDataFrame:
                return GeoDataFrame()

        plugin_manager.register(AliasedPlugin())
        hook = plugin_manager.hook.search
        assert len(hook.get_hookimpls()) == 1

    def test_hookimpl_with_trylast(self, plugin_manager: pluggy.PluginManager) -> None:
        """Plugin can use trylast to deprioritize hook execution."""

        class LastPlugin:
            supported_collections = ["test-collection"]

            @hookimpl(trylast=True)
            def search(
                self,
                collections,
                intersects,
                start_datetime,
                end_datetime,
                search_params,
            ):
                return GeoDataFrame()

        plugin_manager.register(LastPlugin())
        hook = plugin_manager.hook.search
        assert len(hook.get_hookimpls()) == 1


class TestHookspecsStructure:
    """Test the structure and documentation of hookspecs."""

    def test_hookspecs_defined(self) -> None:
        """Hookspecs module defines all required hooks."""
        required_hooks = [
            "supported_collections",
            "search",
            "prepare_for_extraction",
            "extract",
        ]
        for hook_name in required_hooks:
            assert hasattr(hookspecs_core, hook_name), f"Missing hookspec: {hook_name}"

    def test_hooks_have_docstrings(self) -> None:
        """All hookspecs have docstrings."""
        for attr_name in [
            "supported_collections",
            "search",
            "prepare_for_extraction",
            "extract",
        ]:
            attr = getattr(hookspecs_core, attr_name)
            assert attr.__doc__, f"{attr_name} missing docstring"

    def test_hookspecs_can_be_added_to_plugin_manager(self) -> None:
        """Hookspecs can be registered with a PluginManager."""
        pm = pluggy.PluginManager(PROJECT_NAME)
        pm.add_hookspecs(hookspecs_core)

        assert hasattr(pm.hook, "supported_collections")
        assert hasattr(pm.hook, "search")
        assert hasattr(pm.hook, "prepare_for_extraction")
        assert hasattr(pm.hook, "extract")
