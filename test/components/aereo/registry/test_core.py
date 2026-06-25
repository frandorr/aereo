from typing import Any, Mapping, Sequence, cast
from unittest.mock import MagicMock

import pytest
from aereo.interfaces import ExtractionTask
from aereo.registry import AereoRegistry
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# Dummy functional plugins
def dummy_search(
    collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
    intersects: Any,
    start_datetime: Any,
    end_datetime: Any,
    bbox: str = "",
    limit: int = 10,
    search_params: dict[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]:
    """Dummy search function."""
    import geopandas as gpd

    columns = list(AssetSchema.to_schema().columns.keys())
    if "geometry" not in columns:
        columns.append("geometry")
    gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry")
    return cast(GeoDataFrame[AssetSchema], gdf)


dummy_search.supported_collections = ["DummyCollection1", "SharedCollection"]  # type: ignore[attr-defined]


def dummy_read(
    task: ExtractionTask, output_dir: str = "", compress: bool = False
) -> Any:
    """Dummy read function."""
    import xarray as xr

    return xr.Dataset()


dummy_read.supported_collections = ["SharedCollection", "DummyCollection2"]  # type: ignore[attr-defined]


class InvalidPlugin:
    pass


@pytest.fixture
def mock_entry_points(monkeypatch):
    def mock_ep(group):
        if group == "aereo.plugins":
            ep1 = MagicMock()
            ep1.name = "dummy_searcher"
            ep1.load.return_value = dummy_search

            ep2 = MagicMock()
            ep2.name = "invalid_plugin"
            ep2.load.return_value = InvalidPlugin

            ep3 = MagicMock()
            ep3.name = "dummy_reader"
            ep3.load.return_value = dummy_read

            ep4 = MagicMock()
            ep4.name = "failing_plugin"
            ep4.load.side_effect = Exception("Failed to load")

            return [ep1, ep2, ep3, ep4]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_ep)


def test_registry_discovery(mock_entry_points):
    registry = AereoRegistry()
    assert "dummy_searcher" in registry._searchers
    assert "dummy_reader" in registry._registries["reader"].plugins

    assert "invalid_plugin" not in registry._searchers
    assert "failing_plugin" not in registry._registries["reader"].plugins


def test_list_supported_collections(mock_entry_points):
    registry = AereoRegistry()
    collections = registry.list_supported_collections()
    assert collections == ["DummyCollection1", "DummyCollection2", "SharedCollection"]


def test_find_searchers_for(mock_entry_points):
    registry = AereoRegistry()
    assert registry.find_searchers_for("DummyCollection1") == ["dummy_searcher"]
    assert registry.find_searchers_for("SharedCollection") == ["dummy_searcher"]
    assert registry.find_searchers_for("Unknown") == []


def test_find_readers_for(mock_entry_points):
    registry = AereoRegistry()
    assert registry.find_for("reader", "DummyCollection2") == ["dummy_reader"]
    assert registry.find_for("reader", "SharedCollection") == ["dummy_reader"]
    assert registry.find_for("reader", "Unknown") == []


def test_case_insensitive_searcher_lookup(mock_entry_points):
    """Test that find_searchers_for matches collections case-insensitively."""
    registry = AereoRegistry()
    assert registry.find_searchers_for("DummyCollection1") == ["dummy_searcher"]
    assert registry.find_searchers_for("dummycollection1") == ["dummy_searcher"]
    assert registry.find_searchers_for("DUMMYCOLLECTION1") == ["dummy_searcher"]
    assert registry.find_searchers_for("dummyCollection1") == ["dummy_searcher"]


def test_case_insensitive_reader_lookup(mock_entry_points):
    """Test that find_for matches collections case-insensitively for readers."""
    registry = AereoRegistry()
    assert registry.find_for("reader", "DummyCollection2") == ["dummy_reader"]
    assert registry.find_for("reader", "dummycollection2") == ["dummy_reader"]
    assert registry.find_for("reader", "DUMMYCOLLECTION2") == ["dummy_reader"]
    assert registry.find_for("reader", "DummyCollection2") == ["dummy_reader"]


def test_get_searcher(mock_entry_points):
    registry = AereoRegistry()

    searcher = registry.get_searcher("dummy_searcher")
    assert searcher is dummy_search

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get_searcher("missing_searcher")


def test_get_reader(mock_entry_points):
    registry = AereoRegistry()

    reader = registry.get("reader", "dummy_reader")
    assert reader is dummy_read

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get("reader", "missing_reader")


def test_get_collection_mapping_for_searcher(mock_entry_points):
    """Test that collection names are mapped to plugin's declared format."""
    registry = AereoRegistry()

    result = registry.get_collection_mapping_for_searcher(
        "dummy_searcher", ["DummyCollection1"]
    )
    assert result == ["DummyCollection1"]

    result = registry.get_collection_mapping_for_searcher(
        "dummy_searcher", ["DUMMYCOLLECTION1"]
    )
    assert result == ["DummyCollection1"]

    result = registry.get_collection_mapping_for_searcher(
        "dummy_searcher", ["dummycollection1"]
    )
    assert result == ["DummyCollection1"]


def test_get_collection_mapping_for_searcher_unknown_plugin(mock_entry_points):
    """Test fallback when plugin is not found in mapping."""
    registry = AereoRegistry()

    result = registry.get_collection_mapping_for_searcher(
        "unknown_plugin", ["SomeCollection"]
    )
    assert result == ["somecollection"]


def test_get_collection_mapping_for_reader(mock_entry_points):
    """Test collection mapping for readers."""
    registry = AereoRegistry()

    result = registry.find_for("reader", "DUMMYCOLLECTION2")
    assert result == ["dummy_reader"]


def test_get_plugin_params_detailed(mock_entry_points):
    """Test get_plugin_params returns full metadata."""
    registry = AereoRegistry()

    params = registry.get_plugin_params("dummy_searcher", detailed=True)
    names = {p["name"] for p in params["required"]} | {
        p["name"] for p in params["optional"]
    }
    assert names == {
        "collections",
        "intersects",
        "start_datetime",
        "end_datetime",
        "search_params",
        "bbox",
        "limit",
    }


def test_get_plugin_params_unknown_plugin(mock_entry_points):
    """Test get_plugin_params raises for unknown plugin."""
    registry = AereoRegistry()

    with pytest.raises(KeyError, match="Unknown plugin"):
        registry.get_plugin_params("nonexistent_plugin")


# ---------------------------------------------------------------------------
# Generic API
# ---------------------------------------------------------------------------


def test_generic_find_for(mock_entry_points):
    """Test generic find_for works for all plugin types."""
    registry = AereoRegistry()
    assert registry.find_for("searcher", "DummyCollection1") == ["dummy_searcher"]
    assert registry.find_for("reader", "DummyCollection2") == ["dummy_reader"]
    assert registry.find_for("writer", "Anything") == []


def test_generic_has(mock_entry_points):
    """Test generic has works for all plugin types."""
    registry = AereoRegistry()
    assert registry.has("searcher", "dummy_searcher") is True
    assert registry.has("reader", "dummy_reader") is True
    assert registry.has("reader", "dummy_searcher") is False
    assert registry.has("unknown_type", "dummy_searcher") is False


def test_generic_get(mock_entry_points):
    """Test generic get returns plugins by type label."""
    registry = AereoRegistry()
    searcher = registry.get("searcher", "dummy_searcher")
    assert searcher is dummy_search

    reader = registry.get("reader", "dummy_reader")
    assert reader is dummy_read

    with pytest.raises(ValueError, match="Unknown plugin type"):
        registry.get("unknown_type", "dummy_searcher")

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get("searcher", "missing")
