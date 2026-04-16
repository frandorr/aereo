from datetime import datetime
from typing import Any, Mapping, Sequence, cast
from unittest.mock import MagicMock

import pytest
from aer.interfaces import ExtractionTask, Extractor, SearchProvider
from aer.registry import AerRegistry
from aer.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry


# Dummy plugins
class DummySearchProvider(SearchProvider):
    supported_collections = ["DummyCollection1", "SharedCollection"]

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

    @property
    def target_grid_d(self) -> int:
        return 10000

    def extract(
        self,
        extraction_task: ExtractionTask,
        extract_params: dict[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(GeoDataFrame[ArtifactSchema], ArtifactSchema.empty())


class InvalidPlugin:
    pass


@pytest.fixture
def mock_entry_points(monkeypatch):
    def mock_ep(group):
        if group == "aer.search_providers":
            ep1 = MagicMock()
            ep1.name = "dummy_searcher"
            ep1.load.return_value = DummySearchProvider

            ep2 = MagicMock()
            ep2.name = "invalid_searcher"
            ep2.load.return_value = InvalidPlugin

            return [ep1, ep2]

        elif group == "aer.extractors":
            ep3 = MagicMock()
            ep3.name = "dummy_extractor"
            ep3.load.return_value = DummyExtractor

            ep4 = MagicMock()
            ep4.name = "failing_extractor"
            ep4.load.side_effect = Exception("Failed to load")

            return [ep3, ep4]
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", mock_ep)


def test_registry_discovery(mock_entry_points):
    registry = AerRegistry()
    assert "dummy_searcher" in registry._searchers
    assert "dummy_extractor" in registry._extractors

    # invalid and failing ones shouldn't be added
    assert "invalid_searcher" not in registry._searchers
    assert "failing_extractor" not in registry._extractors


def test_list_supported_collections(mock_entry_points):
    registry = AerRegistry()
    collections = registry.list_supported_collections()
    assert collections == ["DummyCollection1", "DummyCollection2", "SharedCollection"]


def test_find_searchers_for(mock_entry_points):
    registry = AerRegistry()
    assert registry.find_searchers_for("DummyCollection1") == ["dummy_searcher"]
    assert registry.find_searchers_for("SharedCollection") == ["dummy_searcher"]
    assert registry.find_searchers_for("Unknown") == []


def test_find_extractors_for(mock_entry_points):
    registry = AerRegistry()
    assert registry.find_extractors_for("DummyCollection2") == ["dummy_extractor"]
    assert registry.find_extractors_for("SharedCollection") == ["dummy_extractor"]
    assert registry.find_extractors_for("Unknown") == []


def test_get_searcher(mock_entry_points):
    registry = AerRegistry()

    searcher = registry.get_searcher("dummy_searcher")
    assert isinstance(searcher, DummySearchProvider)

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get_searcher("missing_searcher")


def test_get_extractor(mock_entry_points):
    registry = AerRegistry()

    extractor = registry.get_extractor("dummy_extractor")
    assert isinstance(extractor, DummyExtractor)

    with pytest.raises(ValueError, match="not found or failed to load"):
        registry.get_extractor("missing_extractor")
