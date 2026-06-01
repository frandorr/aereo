"""Tests for the Hamilton-based AereoDriver."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from unittest.mock import MagicMock

import geopandas as gpd
import pytest

from aereo.discovery import StagePlugins
from aereo.driver import AereoDriver
from aereo.interfaces import PipelineProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_search_module(name: str = "mock_search") -> ModuleType:
    """Create a dynamically-typed Hamilton module with a ``search_results`` node."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    setattr(mod, "supported_collections", ("*",))

    code = compile(
        """
from __future__ import annotations

import geopandas as gpd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry


def search_results(
    aoi: BaseGeometry | None,
    start_datetime: str | None,
    end_datetime: str | None,
) -> GeoDataFrame:
    return gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Point(0, 0)], crs="EPSG:4326"
    )
""",
        name,
        "exec",
    )
    exec(code, mod.__dict__)  # noqa: S102
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Construction / discovery
# ---------------------------------------------------------------------------


def test_driver_init_discovers_plugins(monkeypatch) -> None:
    """AereoDriver discovers plugins for every stage on construction."""
    calls: list[tuple[str, str]] = []

    def fake_discover(group: str) -> StagePlugins:
        calls.append(("discover", group))
        sp = StagePlugins()
        # Register a dummy module so the driver has something for each stage.
        mod = MagicMock(spec=ModuleType)
        mod.supported_collections = ("*",)
        sp.register("dummy", mod)
        return sp

    monkeypatch.setattr("aereo.driver.core.discover_plugins", fake_discover)

    driver = AereoDriver()

    groups = {call[1] for call in calls}
    assert groups == {
        "aereo.search",
        "aereo.download",
        "aereo.read",
        "aereo.reproject",
        "aereo.write",
        "aereo.process",
    }
    assert driver._search_plugins.name_to_module["dummy"] is not None


# ---------------------------------------------------------------------------
# _resolve_plugin
# ---------------------------------------------------------------------------


def test_driver_resolve_plugin_by_hint() -> None:
    """Explicit plugin hint takes highest priority."""
    driver = AereoDriver()
    mock_mod = MagicMock(spec=ModuleType)
    mock_mod.supported_collections = ("*",)
    driver._search_plugins.register("earthaccess", mock_mod)

    profile = PipelineProfile(
        name="test", resolution=100.0, plugin_hints={"search": "earthaccess"}
    )
    result = driver._resolve_plugin("search", profile)
    assert result is mock_mod


def test_driver_resolve_plugin_by_collection() -> None:
    """Auto-discovery by collection name when no hint is given."""
    driver = AereoDriver()
    mock_mod = MagicMock(spec=ModuleType)
    mock_mod.supported_collections = ("S3OLCI",)
    driver._search_plugins.register("earthaccess", mock_mod)

    profile = PipelineProfile(
        name="test", resolution=100.0, collections={"S3OLCI": ["Oa01"]}
    )
    result = driver._resolve_plugin("search", profile)
    assert result is mock_mod


def test_driver_resolve_plugin_by_wildcard() -> None:
    """Wildcard fallback when collection is unknown."""
    driver = AereoDriver()
    wildcard_mod = MagicMock(spec=ModuleType)
    wildcard_mod.supported_collections = ("*",)
    driver._search_plugins.register("generic", wildcard_mod)

    profile = PipelineProfile(name="test", resolution=100.0)
    result = driver._resolve_plugin("search", profile)
    assert result is wildcard_mod


def test_driver_resolve_plugin_hint_not_found() -> None:
    """A hint that does not match any discovered plugin raises ValueError."""
    driver = AereoDriver()
    profile = PipelineProfile(
        name="test", resolution=100.0, plugin_hints={"search": "missing"}
    )
    with pytest.raises(ValueError, match="Plugin hint 'missing'"):
        driver._resolve_plugin("search", profile)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_driver_search_builds_hamilton_driver(monkeypatch) -> None:
    """search() builds a Hamilton driver from the resolved plugin and returns a GeoDataFrame."""
    driver = AereoDriver()
    mock_mod = _make_mock_search_module("mock_search_for_test")
    driver._search_plugins.register("mock", mock_mod)

    profile = PipelineProfile(
        name="test", resolution=100.0, plugin_hints={"search": "mock"}
    )
    result = driver.search(
        profile,
        aoi=None,
        start_datetime="2024-01-01",
        end_datetime="2024-01-02",
    )
    assert isinstance(result, gpd.GeoDataFrame)


# ---------------------------------------------------------------------------
# prepare / extract — deferred to later tasks
# ---------------------------------------------------------------------------


def test_driver_prepare_not_implemented() -> None:
    """prepare() raises NotImplementedError until Task 1.6."""
    driver = AereoDriver()
    profile = PipelineProfile(name="test", resolution=100.0)
    with pytest.raises(NotImplementedError, match="Task 1.6"):
        driver.prepare(
            assets=gpd.GeoDataFrame(),  # type: ignore[arg-type]
            profile=profile,
            grid_config=MagicMock(),
            aoi=None,
        )


def test_driver_extract_compiler_import_succeeds() -> None:
    """extract() no longer raises NotImplementedError for Task 1.5.

    The compiler module now exists, so the method proceeds to plugin
    resolution. With no download plugin available it falls through to
    ValueError, proving the compiler import succeeded.
    """
    driver = AereoDriver()
    mock_task = MagicMock()
    mock_task.profile = PipelineProfile(name="test", resolution=100.0)
    with pytest.raises(ValueError, match="No plugin found"):
        driver.extract(mock_task)
