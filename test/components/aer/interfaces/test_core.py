from typing import Any, cast

import geopandas as gpd
import pytest
from aer.interfaces import AerPlugin, ExtractionTask, Extractor, SearchProvider
from aer.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


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

        @property
        def target_grid_d(self) -> int:
            return 10000

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return extraction_task.assets  # pyright: ignore[reportReturnType]

    extractor = ValidExtractor()
    monkeypatch.setattr("aer.schemas.ArtifactSchema.validate", lambda x: x)

    df1 = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )
    df2 = gpd.GeoDataFrame(
        {"id": [2]}, geometry=[Polygon([[1, 1], [2, 1], [2, 2], [1, 2]])]
    )

    task1 = ExtractionTask(
        assets=cast(Any, df1),
        target_grid_d=10000,
        target_grid_overlap=False,
        resolution=10.0,
        uri="test1",
    )
    task2 = ExtractionTask(
        assets=cast(Any, df2),
        target_grid_d=10000,
        target_grid_overlap=False,
        resolution=10.0,
        uri="test2",
    )

    result = extractor.extract_batches([task1, task2])

    assert len(result) == 2
    assert list(result["id"]) == [1, 2]


def test_extractor_prepare_for_extraction():
    class ValidExtractor(Extractor):
        supported_collections = ["GOES"]

        @property
        def target_grid_d(self) -> int:
            return 10000

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return extraction_task.assets  # pyright: ignore[reportReturnType]

    extractor = ValidExtractor()

    # Needs a GeoDataFrame
    df = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
            Polygon([[1, 1], [2, 1], [2, 2], [1, 2]]),
        ],
    )

    # Should raise error if resolution or uri not provided
    with pytest.raises(
        ValueError, match="Default prepare_for_extraction requires resolution and uri"
    ):
        extractor.prepare_for_extraction(cast(Any, df))

    tasks = extractor.prepare_for_extraction(
        cast(Any, df), resolution=10.0, uri="test_uri", prepare_params={"x": 1}
    )

    assert len(tasks) == 2
    assert tasks[0].resolution == 10.0
    assert tasks[0].uri == "test_uri"
    assert tasks[0].task_context == {"prepare_params": {"x": 1}}
    assert len(tasks[0].assets) == 1
    assert list(tasks[0].assets["id"]) == [1]
