from typing import Any

import pandas as pd
import pytest
from aer.interfaces import AerPlugin, Extractor, SearchProvider
from aer.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


def test_plugin_missing_supported_collections():
    with pytest.raises(
        TypeError, match="must define the 'supported_collections' attribute"
    ):

        class InvalidPlugin(AerPlugin):
            pass


def test_plugin_supported_collections_is_string():
    with pytest.raises(
        TypeError, match="must be a Sequence of strings .* got a single string"
    ):

        class InvalidPlugin(AerPlugin):
            supported_collections = "GOES-16"


def test_plugin_supported_collections_is_not_sequence():
    with pytest.raises(TypeError, match="must be a Sequence .* got int"):

        class InvalidPlugin(AerPlugin):
            supported_collections = 123  # pyright: ignore[reportAssignmentType]


def test_plugin_supported_collections_is_empty():
    with pytest.raises(ValueError, match="cannot be empty"):

        class InvalidPlugin(AerPlugin):
            supported_collections = []


def test_plugin_valid_supported_collections():
    class ValidPlugin(AerPlugin):
        supported_collections = ["GOES-16", "GOES-17"]

    assert ValidPlugin.supported_collections == ["GOES-16", "GOES-17"]


def test_search_provider_abstract():
    class DummySearcher(SearchProvider):
        supported_collections = ["GOES"]

    with pytest.raises(
        TypeError, match="Can't instantiate abstract class DummySearcher"
    ):
        DummySearcher()  # pyright: ignore[reportAbstractUsage]


def test_extractor_abstract():
    class DummyExtractor(Extractor):
        supported_collections = ["GOES"]

    with pytest.raises(
        TypeError, match="Can't instantiate abstract class DummyExtractor"
    ):
        DummyExtractor()  # pyright: ignore[reportAbstractUsage]


def test_extractor_extract_batches(monkeypatch):
    class ValidExtractor(Extractor):
        supported_collections = ["GOES"]

        def prepare_for_extraction(
            self,
            search_results: GeoDataFrame[AssetSchema],
            prepare_params: dict[str, Any] | None,
        ) -> list[GeoDataFrame[AssetSchema]]:
            return [search_results]

        def extract(
            self,
            assets_batch: GeoDataFrame[AssetSchema],
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return assets_batch  # pyright: ignore[reportReturnType]

    extractor = ValidExtractor()
    monkeypatch.setattr("aer.schemas.ArtifactSchema.validate", lambda x: x)

    df1 = pd.DataFrame({"id": [1]})
    df2 = pd.DataFrame({"id": [2]})

    result = extractor.extract_batches([df1, df2])  # pyright: ignore[reportArgumentType]

    assert len(result) == 2
    assert list(result["id"]) == [1, 2]
