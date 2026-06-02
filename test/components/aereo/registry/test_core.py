from datetime import datetime
from typing import Any, Mapping, Sequence, cast
from unittest.mock import MagicMock

import pytest
from aereo.interfaces import ExtractionTask, Extractor, PluginParam, SearchProvider
from aereo.registry import AereoRegistry
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry


# Dummy plugins
class DummySearchProvider(SearchProvider):
    supported_collections = ["DummyCollection1", "SharedCollection"]
    required_params = (
        PluginParam(name="bbox", type="str", description="Bounding box"),
    )
    optional_params = (
        PluginParam(name="limit", type="int", description="Result limit", default=10),
    )

    def search(
        self,
        collections: Sequence[str],
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        search_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[AssetSchema]:
        return cast(GeoDataFrame[AssetSchema], AssetSchema.empty())


class DummyExtractor(Extractor):
    supported_collections = ["SharedCollection", "DummyCollection2"]
    required_params = (
        PluginParam(name="output_dir", type="path", description="Output directory"),
    )
    optional_params = (
        PluginParam(
            name="compress", type="bool", description="Compress output", default=False
        ),
    )

    @property
    def target_grid_d(self) -> int:
        return 10000

    def extract(
        self,
        extraction_task: ExtractionTask,
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(GeoDataFrame[ArtifactSchema], ArtifactSchema.empty())


class InvalidPlugin:
    pass


@pytest.fixture
def mock_entry_points(monkeypatch):
    def mock_ep(group):
        if group == "aereo.plugins":
            ep1 = MagicMock()
            ep1.name = "dummy_searcher"
            ep1.load.return_value = DummySearchProvider

            ep2 = MagicMock()
            ep2.name = "invalid_plugin"
            ep2.load.return_value = InvalidPlugin

            ep3 = MagicMock()
            ep3.name = "dummy_extractor"
            ep3.load.return_value = DummyExtractor

            ep4 = MagicMock()
            ep4.name = "failing_plugin"
            ep4.load.side_effect = Exception("Failed to load")

            return [ep1, ep2, ep3, ep4]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_ep)


def test_registry_discovery(mock_entry_points):
    registry = AereoRegistry()
    assert "dummy_searcher" in registry._searchers
    assert "dummy_extractor" in registry._extractors

    # invalid and failing ones shouldn't be added
    assert "invalid_plugin" not in registry._searchers
    assert "failing_plugin" not in registry._extractors


def test_list_supported_collections(mock_entry_points):
    registry = AereoRegistry()
    collections = registry.list_supported_collections()
    assert collections == ["DummyCollection1", "DummyCollection2", "SharedCollection"]


def test_find_searchers_for(mock_entry_points):
    registry = AereoRegistry()
    assert registry.find_searchers_for("DummyCollection1") == ["dummy_searcher"]
    assert registry.find_searchers_for("SharedCollection") == ["dummy_searcher"]
    assert registry.find_searchers_for("Unknown") == []


def test_find_extractors_for(mock_entry_points):
    registry = AereoRegistry()
    assert registry.find_extractors_for("DummyCollection2") == ["dummy_extractor"]
    assert registry.find_extractors_for("SharedCollection") == ["dummy_extractor"]
    assert registry.find_extractors_for("Unknown") == []


def test_case_insensitive_searcher_lookup(mock_entry_points):
    """Test that find_searchers_for matches collections case-insensitively."""
    registry = AereoRegistry()
    # Exact match
    assert registry.find_searchers_for("DummyCollection1") == ["dummy_searcher"]
    # Lowercase
    assert registry.find_searchers_for("dummycollection1") == ["dummy_searcher"]
    # Uppercase
    assert registry.find_searchers_for("DUMMYCOLLECTION1") == ["dummy_searcher"]
    # Mixed case (like the reported bug: "abi-L1b-RadC" vs "ABI-L1b-RadC")
    assert registry.find_searchers_for("dummyCollection1") == ["dummy_searcher"]


def test_case_insensitive_extractor_lookup(mock_entry_points):
    """Test that find_extractors_for matches collections case-insensitively."""
    registry = AereoRegistry()
    # Exact match
    assert registry.find_extractors_for("DummyCollection2") == ["dummy_extractor"]
    # Lowercase
    assert registry.find_extractors_for("dummycollection2") == ["dummy_extractor"]
    # Uppercase
    assert registry.find_extractors_for("DUMMYCOLLECTION2") == ["dummy_extractor"]
    # Mixed case
    assert registry.find_extractors_for("DummyCollection2") == ["dummy_extractor"]


def test_get_searcher(mock_entry_points):
    registry = AereoRegistry()

    searcher = registry.get_searcher("dummy_searcher")
    assert isinstance(searcher, DummySearchProvider)

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get_searcher("missing_searcher")


def test_get_extractor(mock_entry_points):
    registry = AereoRegistry()

    extractor = registry.get_extractor("dummy_extractor")
    assert isinstance(extractor, DummyExtractor)

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get_extractor("missing_extractor")


def test_get_collection_mapping_for_searcher(mock_entry_points):
    """Test that collection names are mapped to plugin's declared format."""
    registry = AereoRegistry()

    # Plugin declares supported_collections = ["DummyCollection1", "SharedCollection"]
    # Should map user input (any case) to plugin's original case

    # Exact match - returns original
    result = registry.get_collection_mapping_for_searcher(
        "dummy_searcher", ["DummyCollection1"]
    )
    assert result == ["DummyCollection1"]

    # Uppercase - maps to original lower/uppercase combo
    result = registry.get_collection_mapping_for_searcher(
        "dummy_searcher", ["DUMMYCOLLECTION1"]
    )
    assert result == ["DummyCollection1"]

    # Lowercase - maps to original
    result = registry.get_collection_mapping_for_searcher(
        "dummy_searcher", ["dummycollection1"]
    )
    assert result == ["DummyCollection1"]


def test_get_collection_mapping_for_searcher_unknown_plugin(mock_entry_points):
    """Test fallback when plugin is not found in mapping."""
    registry = AereoRegistry()

    # Unknown plugin falls back to lowercase
    result = registry.get_collection_mapping_for_searcher(
        "unknown_plugin", ["SomeCollection"]
    )
    assert result == ["somecollection"]


def test_get_collection_mapping_for_extractor(mock_entry_points):
    """Test collection mapping for extractors."""
    registry = AereoRegistry()

    # Plugin declares supported_collections = ["SharedCollection", "DummyCollection2"]
    # Should map user input to plugin's original case

    result = registry.get_collection_mapping_for_extractor(
        "dummy_extractor", ["DUMMYCOLLECTION2"]
    )
    assert result == ["DummyCollection2"]


def test_get_plugin_params_detailed(mock_entry_points):
    """Test get_plugin_params returns full metadata when detailed=True."""
    registry = AereoRegistry()

    params = registry.get_plugin_params("dummy_searcher", detailed=True)
    assert len(params["required"]) == 1
    assert params["required"][0]["name"] == "bbox"
    assert "type" in params["required"][0]
    assert "description" in params["required"][0]

    assert len(params["optional"]) == 1
    assert params["optional"][0]["name"] == "limit"
    assert params["optional"][0]["default"] == 10
    assert "type" in params["optional"][0]


def test_get_plugin_params_not_detailed(mock_entry_points):
    """Test get_plugin_params returns only name and default when detailed=False."""
    registry = AereoRegistry()

    params = registry.get_plugin_params("dummy_searcher", detailed=False)
    assert len(params["required"]) == 1
    assert params["required"][0] == {"name": "bbox", "default": None}

    assert len(params["optional"]) == 1
    assert params["optional"][0] == {"name": "limit", "default": 10}

    # Ensure no extra keys are present
    assert set(params["required"][0].keys()) == {"name", "default"}
    assert set(params["optional"][0].keys()) == {"name", "default"}


def test_list_all_params_detailed(mock_entry_points):
    """Test list_all_params returns full metadata when detailed=True."""
    registry = AereoRegistry()

    all_params = registry.list_all_params(detailed=True)
    assert "dummy_searcher" in all_params
    assert "dummy_extractor" in all_params

    searcher = all_params["dummy_searcher"]
    assert searcher["type"] == "searcher"
    assert len(searcher["required"]) == 1
    assert searcher["required"][0]["name"] == "bbox"
    assert "description" in searcher["required"][0]


def test_list_all_params_not_detailed(mock_entry_points):
    """Test list_all_params returns only name and default when detailed=False."""
    registry = AereoRegistry()

    all_params = registry.list_all_params(detailed=False)
    assert "dummy_searcher" in all_params
    assert "dummy_extractor" in all_params

    extractor = all_params["dummy_extractor"]
    assert extractor["type"] == "extractor"
    assert len(extractor["required"]) == 1
    assert extractor["required"][0] == {"name": "output_dir", "default": None}
    assert set(extractor["required"][0].keys()) == {"name", "default"}

    assert len(extractor["optional"]) == 1
    assert extractor["optional"][0] == {"name": "compress", "default": False}
    assert set(extractor["optional"][0].keys()) == {"name", "default"}


def test_get_plugin_params_unknown_plugin(mock_entry_points):
    """Test get_plugin_params raises for unknown plugin."""
    registry = AereoRegistry()

    with pytest.raises(KeyError, match="Unknown plugin"):
        registry.get_plugin_params("nonexistent_plugin")


# ---------------------------------------------------------------------------
# Generic API (Phase 1)
# ---------------------------------------------------------------------------


def test_generic_find_for(mock_entry_points):
    """Test generic find_for works for all plugin types."""
    registry = AereoRegistry()
    assert registry.find_for("searcher", "DummyCollection1") == ["dummy_searcher"]
    assert registry.find_for("extractor", "DummyCollection2") == ["dummy_extractor"]
    assert registry.find_for("reader", "Anything") == []


def test_generic_has(mock_entry_points):
    """Test generic has works for all plugin types."""
    registry = AereoRegistry()
    assert registry.has("searcher", "dummy_searcher") is True
    assert registry.has("extractor", "dummy_extractor") is True
    assert registry.has("reader", "dummy_searcher") is False
    assert registry.has("unknown_type", "dummy_searcher") is False


def test_generic_get(mock_entry_points):
    """Test generic get instantiates plugins by type label."""
    registry = AereoRegistry()
    searcher = registry.get("searcher", "dummy_searcher")
    assert isinstance(searcher, DummySearchProvider)

    extractor = registry.get("extractor", "dummy_extractor")
    assert isinstance(extractor, DummyExtractor)

    with pytest.raises(ValueError, match="Unknown plugin type"):
        registry.get("unknown_type", "dummy_searcher")

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get("searcher", "missing")
