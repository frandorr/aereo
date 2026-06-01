"""Tests for per-stage plugin discovery (aereo.discovery)."""

from types import ModuleType
from unittest.mock import MagicMock

import pytest
from aereo.discovery import StagePlugins, discover_plugins, resolve_plugin


# ---------------------------------------------------------------------------
# StagePlugins
# ---------------------------------------------------------------------------


def test_stage_plugins_register() -> None:
    """Registering a module indexes its supported_collections."""
    sp = StagePlugins()
    mod = MagicMock(spec=ModuleType)
    mod.supported_collections = ("S3OLCI", "S3SLSTR")

    sp.register("satpy", mod)

    assert sp.name_to_module["satpy"] is mod
    assert sp.name_to_collections["satpy"] == ("S3OLCI", "S3SLSTR")
    assert sp.collection_to_names["s3olci"] == ["satpy"]
    assert sp.collection_to_names["s3slstr"] == ["satpy"]


def test_stage_plugins_register_no_collections() -> None:
    """Modules without supported_collections default to empty tuple."""
    sp = StagePlugins()
    mod = MagicMock(spec=ModuleType)
    # No supported_collections attribute

    sp.register("generic", mod)

    assert sp.name_to_collections["generic"] == ()
    assert sp.collection_to_names == {}


def test_stage_plugins_register_single_collection() -> None:
    """A single non-sequence supported_collections is wrapped in a tuple."""
    sp = StagePlugins()
    mod = MagicMock(spec=ModuleType)
    mod.supported_collections = "S3OLCI"

    sp.register("single", mod)

    assert sp.name_to_collections["single"] == ("S3OLCI",)


def test_stage_plugins_list_supported_collections() -> None:
    """list_supported_collections returns original-cased, sorted names."""
    sp = StagePlugins()
    mod_a = MagicMock(spec=ModuleType)
    mod_a.supported_collections = ("S3OLCI",)
    mod_b = MagicMock(spec=ModuleType)
    mod_b.supported_collections = ("goes16",)

    sp.register("a", mod_a)
    sp.register("b", mod_b)

    assert sp.list_supported_collections() == ["S3OLCI", "goes16"]


def test_stage_plugins_case_insensitive_indexing() -> None:
    """Collections are indexed case-insensitively by lower-cased key."""
    sp = StagePlugins()
    mod = MagicMock(spec=ModuleType)
    mod.supported_collections = ("DummyCollection",)

    sp.register("dummy", mod)

    assert sp.collection_to_names["dummycollection"] == ["dummy"]


# ---------------------------------------------------------------------------
# discover_plugins
# ---------------------------------------------------------------------------


def test_discover_plugins_loads_modules(monkeypatch) -> None:
    """discover_plugins loads modules from entry points."""
    mock_mod = MagicMock(spec=ModuleType)
    mock_mod.supported_collections = ("*",)

    ep = MagicMock()
    ep.name = "earthaccess"
    ep.load.return_value = mock_mod

    def mock_entry_points(*, group):
        if group == "aereo.search":
            return [ep]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_entry_points)

    plugins = discover_plugins("aereo.search")
    assert "earthaccess" in plugins.name_to_module
    assert plugins.name_to_module["earthaccess"] is mock_mod


def test_discover_plugins_skips_broken_plugins(monkeypatch) -> None:
    """Broken entry points are logged and skipped."""
    good_mod = MagicMock(spec=ModuleType)
    good_mod.supported_collections = ("*",)

    ep_good = MagicMock()
    ep_good.name = "good"
    ep_good.load.return_value = good_mod

    ep_bad = MagicMock()
    ep_bad.name = "bad"
    ep_bad.load.side_effect = Exception("load error")

    def mock_entry_points(*, group):
        if group == "aereo.search":
            return [ep_good, ep_bad]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_entry_points)

    plugins = discover_plugins("aereo.search")
    assert "good" in plugins.name_to_module
    assert "bad" not in plugins.name_to_module


def test_discover_plugins_class_entry_point(monkeypatch) -> None:
    """Entry points that resolve to classes use the class's module."""

    class DummyPlugin:
        supported_collections = ("*",)

    ep = MagicMock()
    ep.name = "dummy"
    ep.load.return_value = DummyPlugin

    def mock_entry_points(*, group):
        if group == "aereo.read":
            return [ep]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_entry_points)

    plugins = discover_plugins("aereo.read")
    assert "dummy" in plugins.name_to_module
    # Should be the module where DummyPlugin was defined, i.e. this test module
    assert plugins.name_to_module["dummy"].__name__ == __name__


def test_discover_plugins_non_module_no_module_attr(monkeypatch) -> None:
    """Entry points without __module__ are skipped with a warning."""
    ep = MagicMock()
    ep.name = "weird"
    ep.load.return_value = 42  # int has no __module__

    def mock_entry_points(*, group):
        if group == "aereo.search":
            return [ep]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_entry_points)

    plugins = discover_plugins("aereo.search")
    assert "weird" not in plugins.name_to_module


# ---------------------------------------------------------------------------
# resolve_plugin
# ---------------------------------------------------------------------------


def test_resolve_by_hint() -> None:
    """Explicit plugin hint takes highest priority."""
    sp = StagePlugins()
    mock_mod = MagicMock(spec=ModuleType)
    mock_mod.supported_collections = ("*",)
    sp.register("earthaccess", mock_mod)

    result = resolve_plugin("search", "S3OLCI", {"search": "earthaccess"}, sp)
    assert result is mock_mod


def test_resolve_by_collection() -> None:
    """Auto-discovery by collection name when no hint is given."""
    sp = StagePlugins()
    mock_mod = MagicMock(spec=ModuleType)
    mock_mod.supported_collections = ("S3OLCI",)
    sp.register("earthaccess", mock_mod)

    result = resolve_plugin("search", "S3OLCI", {}, sp)
    assert result is mock_mod


def test_resolve_by_wildcard() -> None:
    """Wildcard fallback when collection is unknown."""
    sp = StagePlugins()
    wildcard_mod = MagicMock(spec=ModuleType)
    wildcard_mod.supported_collections = ("*",)
    sp.register("generic", wildcard_mod)

    result = resolve_plugin("search", "UNKNOWN", {}, sp)
    assert result is wildcard_mod


def test_resolve_hint_not_found() -> None:
    """A hint that does not match any discovered plugin raises ValueError."""
    sp = StagePlugins()

    with pytest.raises(ValueError, match="Plugin hint 'missing'"):
        resolve_plugin("search", "S3OLCI", {"search": "missing"}, sp)


def test_resolve_no_match_and_no_wildcard() -> None:
    """When no collection match and no wildcard exists, raise ValueError."""
    sp = StagePlugins()
    mod = MagicMock(spec=ModuleType)
    mod.supported_collections = ("S3OLCI",)
    sp.register("earthaccess", mod)

    with pytest.raises(ValueError, match="No plugin found for stage 'search'"):
        resolve_plugin("search", "UNKNOWN", {}, sp)


def test_resolve_case_insensitive_collection() -> None:
    """Collection matching is case-insensitive."""
    sp = StagePlugins()
    mock_mod = MagicMock(spec=ModuleType)
    mock_mod.supported_collections = ("S3OLCI",)
    sp.register("earthaccess", mock_mod)

    result = resolve_plugin("search", "s3olci", {}, sp)
    assert result is mock_mod
