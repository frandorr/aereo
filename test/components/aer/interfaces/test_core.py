from typing import Any, Sequence, cast

import geopandas as gpd
import pytest
from aer.interfaces import (
    AerPlugin,
    ExtractionTask,
    Extractor,
    SearchProvider,
    merge_params,
)
from aer.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ValidationError
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


def test_search_provider_signature_has_profiles():
    """The abstract search() signature must accept profiles parameter."""
    import inspect

    sig = inspect.signature(SearchProvider.search)
    assert "profiles" in sig.parameters
    assert "collections" not in sig.parameters


def test_search_provider_accepts_profiles_signature():
    """A concrete searcher using the new profiles signature can be instantiated."""
    from aer.interfaces.core import AerProfile

    class GoodSearcher(SearchProvider):
        supported_collections = ["X"]

        def search(
            self,
            profiles: Sequence[AerProfile],
            intersects: Any,
            start_datetime: Any,
            end_datetime: Any,
            search_params: Any,
        ) -> Any: ...

    # Should instantiate without error
    searcher = GoodSearcher()
    assert searcher is not None


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

    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="default", resolution=10.0)

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

    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="default", resolution=10.0)

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

    from aer.interfaces.core import AerProfile

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

    profile = AerProfile(name="test_profile", resolution=10.0)

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


def test_aer_profile_has_all_fields():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(
        name="goes_16_abi",
        resolution=1000.0,
        collections=["ABI-L1b-RadC"],
        channels=["C01", "C02"],
        satellite="GOES-16",
        plugin_hints={
            "search": "aer-search-aws-goes",
            "extract": "aer-extract-aws-goes",
        },
    )
    assert profile.collections == ["ABI-L1b-RadC"]
    assert profile.channels == ["C01", "C02"]
    assert profile.satellite == "GOES-16"
    assert profile.plugin_hints["search"] == "aer-search-aws-goes"


def test_aer_profile_accepts_downloader():
    from pathlib import Path

    from aer.interfaces.core import AerProfile

    def my_dl(url: str, local_path: Path) -> None:
        pass

    profile = AerProfile(name="test", resolution=100.0, downloader=my_dl)
    assert profile.downloader is my_dl


def test_aer_profile_downloader_defaults_to_none():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="test", resolution=100.0)
    assert profile.downloader is None


def test_aer_profile_defaults():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="minimal", resolution=100.0)
    assert profile.collections == ()
    assert profile.channels is None
    assert profile.satellite is None
    assert profile.plugin_hints == {}
    assert profile.conform_to_max_shape is False


def test_aer_profile_accepts_conform_to_max_shape():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="test", resolution=100.0, conform_to_max_shape=True)
    assert profile.conform_to_max_shape is True


def test_extraction_task_accepts_aer_profile():
    import geopandas as gpd
    from shapely.geometry import Polygon

    from aer.interfaces.core import AerProfile, ExtractionTask
    from pandera.typing.geopandas import GeoDataFrame

    df = gpd.GeoDataFrame(
        {"collection": ["GOES"], "start_time": ["2023-01-01"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    profile = AerProfile(name="test", resolution=10.0, collections=["GOES"])
    task = ExtractionTask(
        assets=cast(GeoDataFrame, df),
        profile=profile,
        uri="test",
        grid_cells=[],
    )
    assert task.profile.name == "test"


def test_aer_profile_is_frozen():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="test", resolution=100.0)
    with pytest.raises(ValidationError):
        profile.resolution = 200.0


def test_aer_profile_forbids_extra_fields():
    from aer.interfaces.core import AerProfile

    with pytest.raises(ValidationError):
        AerProfile(name="test", resolution=100.0, unknown_field=42)  # pyright: ignore[reportCallIssue]


def test_aer_profile_import_string_downloader():
    from aer.interfaces.core import AerProfile

    # Use a stdlib callable as a stand-in for a real downloader
    profile = AerProfile(
        name="test",
        resolution=100.0,
        downloader="os.path.join",  # pyright: ignore[reportArgumentType]
    )
    assert callable(profile.downloader)


def test_aer_profile_invalid_import_string():
    from aer.interfaces.core import AerProfile

    with pytest.raises(ValidationError):
        AerProfile(
            name="test",
            resolution=100.0,
            downloader="this.does.not.exist",  # pyright: ignore[reportArgumentType]
        )


def test_aer_profile_has_search_and_extract_params():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(
        name="test",
        resolution=100.0,
        search_params={"version": "061"},
        extract_params={"calibration": "reflectance"},
    )
    assert profile.search_params["version"] == "061"
    assert profile.extract_params["calibration"] == "reflectance"


def test_aer_profile_rejects_extra_params():
    from aer.interfaces.core import AerProfile

    with pytest.raises(ValidationError):
        AerProfile(name="test", resolution=100.0, extra_params={"foo": "bar"})  # pyright: ignore[reportCallIssue]


_captured_extract_params: list[dict[str, Any] | None] = []


def test_extract_batches_merges_profile_extract_params(monkeypatch):
    """Profile extract_params should override batch extract_params."""
    _captured_extract_params.clear()

    class _CapturingExtractor(Extractor):
        supported_collections = ["GOES"]

        @property
        def target_grid_d(self) -> int:
            return 10000

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            _captured_extract_params.append(extract_params)
            return cast(GeoDataFrame[ArtifactSchema], extraction_task.assets)

    extractor = _CapturingExtractor()
    monkeypatch.setattr("aer.schemas.ArtifactSchema.validate", lambda x: x)

    df = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )

    from aer.interfaces.core import AerProfile

    profile = AerProfile(
        name="test",
        resolution=10.0,
        extract_params={"calibration": "reflectance"},
    )
    task = ExtractionTask(
        assets=cast(Any, df),
        grid_cells=[],
        profile=profile,
        uri="test1",
    )

    extractor.extract_batches([task], extract_params={"calibration": "radiance"})

    assert len(_captured_extract_params) == 1
    assert _captured_extract_params[0] == {"calibration": "reflectance"}


def test_merge_params_batch_only():
    assert merge_params({"a": 1}, {}) == {"a": 1}


def test_merge_params_profile_overrides():
    assert merge_params({"a": 1}, {"a": 2}) == {"a": 2}


def test_merge_params_combined():
    assert merge_params({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merge_params_none_batch():
    assert merge_params(None, {"a": 1}) == {"a": 1}
