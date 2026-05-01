from typing import Any, cast

import geopandas as gpd
import pytest
from aer.interfaces import AerPlugin, ExtractionTask, Extractor, SearchProvider
from aer.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


class _PicklableExtractor(Extractor):
    """Module-level extractor so ProcessPoolExecutor can pickle it."""

    supported_collections = ["GOES"]

    @property
    def target_grid_d(self) -> int:
        return 10000

    def extract(
        self,
        extraction_task: ExtractionTask,
        extract_params: dict[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(GeoDataFrame[ArtifactSchema], extraction_task.assets)


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
    class InvalidPlugin(AerPlugin):
        supported_collections = []

    assert InvalidPlugin.supported_collections == []


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
    extractor = _PicklableExtractor()
    monkeypatch.setattr("aer.schemas.ArtifactSchema.validate", lambda x: x)

    df1 = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )
    df2 = gpd.GeoDataFrame(
        {"id": [2]}, geometry=[Polygon([[1, 1], [2, 1], [2, 2], [1, 2]])]
    )

    from aer.interfaces.core import ExtractionProfile

    profile = ExtractionProfile(name="default", resolution=10.0)

    task1 = ExtractionTask(
        assets=cast(Any, df1),
        grid_cells=[],
        profile=profile,
        uri="test1",
    )
    task2 = ExtractionTask(
        assets=cast(Any, df2),
        grid_cells=[],
        profile=profile,
        uri="test2",
    )

    result = extractor.extract_batches([task1, task2])

    assert len(result) == 2
    assert list(result["id"]) == [1, 2]


def test_extractor_extract_batches_parallel(monkeypatch):
    """Parallel path uses forkserver/spawn and succeeds with picklable objects."""
    extractor = _PicklableExtractor()
    monkeypatch.setattr("aer.schemas.ArtifactSchema.validate", lambda x: x)

    df1 = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )
    df2 = gpd.GeoDataFrame(
        {"id": [2]}, geometry=[Polygon([[1, 1], [2, 1], [2, 2], [1, 2]])]
    )

    from aer.interfaces.core import ExtractionProfile

    profile = ExtractionProfile(name="default", resolution=10.0)

    task1 = ExtractionTask(
        assets=cast(Any, df1),
        grid_cells=[],
        profile=profile,
        uri="test1",
    )
    task2 = ExtractionTask(
        assets=cast(Any, df2),
        grid_cells=[],
        profile=profile,
        uri="test2",
    )

    result = extractor.extract_batches([task1, task2], max_batch_workers=2)

    assert len(result) == 2
    assert sorted(result["id"].tolist()) == [1, 2]


def test_extractor_prepare_for_extraction():
    class LargeGridExtractor(Extractor):
        supported_collections = ["GOES"]

        @property
        def target_grid_d(self) -> int:
            return 1000000  # Large grid to keep cell count low

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return cast(GeoDataFrame[ArtifactSchema], extraction_task.assets)

    extractor = LargeGridExtractor()

    from datetime import datetime

    from aer.interfaces.core import ExtractionProfile

    # Needs a GeoDataFrame with collection and start_time
    df = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "collection": ["GOES", "GOES"],
            "start_time": [datetime(2023, 1, 1, 12, 0), datetime(2023, 1, 1, 12, 0)],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
            Polygon([[1, 1], [2, 1], [2, 2], [1, 2]]),
        ],
    )

    # Should raise error if uri not provided
    with pytest.raises(
        ValueError, match="Default prepare_for_extraction requires uri to be defined"
    ):
        extractor.prepare_for_extraction(cast(Any, df))

    profile = ExtractionProfile(name="test_profile", resolution=10.0)

    # Should raise error if profiles not provided
    with pytest.raises(
        ValueError,
        match="Default prepare_for_extraction requires at least one profile to be defined",
    ):
        extractor.prepare_for_extraction(cast(Any, df), uri="test_uri")

    tasks = extractor.prepare_for_extraction(
        cast(Any, df),
        profiles=[profile],
        uri="test_uri",
        prepare_params={"cells_per_chunk": 1},
    )

    assert len(tasks) > 0
    assert tasks[0].profile.resolution == 10.0
    assert tasks[0].profile.name == "test_profile"
    assert tasks[0].uri == "test_uri"
    assert tasks[0].prepare_params == {"cells_per_chunk": 1}
    assert tasks[0].aoi is None
    assert len(tasks[0].assets) == 2  # Both assets have same start_time and collection
    assert "start_time" in tasks[0].task_context
