from typing import Any, Sequence, cast

import geopandas as gpd
import pytest
from aer.interfaces import (
    AerPlugin,
    ExtractionTask,
    Extractor,
    GridConfig,
    SearchProvider,
    merge_params,
)
from aer.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ValidationError
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


def test_extractor_no_longer_requires_target_grid_d():
    """Instantiating an extractor should not require target_grid_d."""
    import pandas as pd

    class DummyExtractor(Extractor, plugin_abstract=False):
        supported_collections = ["test"]

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return cast(GeoDataFrame[ArtifactSchema], pd.DataFrame())

    extractor = DummyExtractor()
    assert hasattr(extractor, "extract")


def test_extractor_prepare_for_extraction():
    class LargeGridExtractor(Extractor):
        supported_collections = ["GOES"]

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

    grid_config = GridConfig(target_grid_dist=1_000_000)
    profile = AerProfile(name="test_profile", resolution=10.0)

    # Should raise error if uri not provided
    with pytest.raises(
        ValueError, match="Default prepare_for_extraction requires uri to be defined"
    ):
        extractor.prepare_for_extraction(cast(Any, df), grid_config=grid_config)

    # Should raise error if profiles not provided
    with pytest.raises(
        ValueError,
        match="Default prepare_for_extraction requires at least one profile to be defined",
    ):
        extractor.prepare_for_extraction(
            cast(Any, df), grid_config=grid_config, uri="test_uri"
        )

    tasks = extractor.prepare_for_extraction(
        cast(Any, df),
        grid_config=grid_config,
        profiles=[profile],
        uri="test_uri",
        cells_per_chunk=1,
    )

    assert len(tasks) > 0
    assert tasks[0].profile.resolution == 10.0
    assert tasks[0].profile.name == "test_profile"
    assert tasks[0].uri == "test_uri"
    assert tasks[0].grid_config == grid_config
    assert tasks[0].aoi is None
    assert len(tasks[0].assets) == 2  # Both assets have same start_time and collection
    assert "start_time" in tasks[0].task_context
    assert "extractor_hint" in tasks[0].task_context
    assert tasks[0].task_context["extractor_hint"] is None


def test_aer_profile_has_all_fields():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(
        name="goes_16_abi",
        resolution=1000.0,
        collections={"ABI-L1b-RadC": ["C01", "C02"]},
        plugin_hints={
            "search": "aer-search-aws-goes",
            "extract": "aer-extract-aws-goes",
        },
    )
    assert profile.collections == {"ABI-L1b-RadC": ["C01", "C02"]}
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
    assert profile.collections == {}
    assert profile.plugin_hints == {}
    assert profile.conform_to is None


def test_aer_profile_accepts_conform_to():
    from aer.interfaces.core import AerProfile

    profile = AerProfile(name="test", resolution=100.0, conform_to=(256, 256))
    assert profile.conform_to == (256, 256)


def test_extraction_task_accepts_aer_profile():
    import geopandas as gpd
    from shapely.geometry import Polygon

    from aer.interfaces.core import AerProfile, ExtractionTask
    from pandera.typing.geopandas import GeoDataFrame

    df = gpd.GeoDataFrame(
        {"collection": ["GOES"], "start_time": ["2023-01-01"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    profile = AerProfile(name="test", resolution=10.0, collections={"GOES": ["var1"]})
    grid_config = GridConfig(target_grid_dist=10_000)
    task = ExtractionTask(
        assets=cast(GeoDataFrame, df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
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


def test_merge_params_batch_only():
    assert merge_params({"a": 1}, {}) == {"a": 1}


def test_merge_params_profile_overrides():
    assert merge_params({"a": 1}, {"a": 2}) == {"a": 2}


def test_merge_params_combined():
    assert merge_params({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merge_params_none_batch():
    assert merge_params(None, {"a": 1}) == {"a": 1}


def test_prepare_computes_common_shape_when_conform_enabled():
    """When profile has conform_to set, conform_to is read from profile, not task_context."""
    from datetime import datetime

    from aer.interfaces.core import AerProfile

    class ConformExtractor(Extractor):
        supported_collections = ["C1"]

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return cast(GeoDataFrame[ArtifactSchema], extraction_task.assets)

    extractor = ConformExtractor()

    df = gpd.GeoDataFrame(
        {
            "id": [1],
            "collection": ["C1"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
        ],
    )

    profile = AerProfile(
        name="test",
        resolution=100.0,
        collections={"C1": ["var1"]},
        conform_to=(256, 256),
    )

    grid_config = GridConfig(target_grid_dist=100_000)
    tasks = extractor.prepare_for_extraction(
        cast(Any, df),
        grid_config=grid_config,
        profiles=[profile],
        uri="test_uri",
    )

    assert len(tasks) > 0
    assert tasks[0].profile.conform_to == (256, 256)


def test_prepare_does_not_compute_common_shape_when_conform_disabled():
    """When profile has conform_to=None, profile.conform_to is None."""
    from datetime import datetime

    from aer.interfaces.core import AerProfile

    class NoConformExtractor(Extractor):
        supported_collections = ["C1"]

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return cast(GeoDataFrame[ArtifactSchema], extraction_task.assets)

    extractor = NoConformExtractor()

    df = gpd.GeoDataFrame(
        {
            "id": [1],
            "collection": ["C1"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
        ],
    )

    profile = AerProfile(
        name="test",
        resolution=100.0,
        collections={"C1": ["var1"]},
        conform_to=None,
    )

    grid_config = GridConfig(target_grid_dist=100_000)
    tasks = extractor.prepare_for_extraction(
        cast(Any, df),
        grid_config=grid_config,
        profiles=[profile],
        uri="test_uri",
    )

    assert len(tasks) > 0
    assert tasks[0].profile.conform_to is None


def test_prepare_for_extraction_includes_extractor_hint():
    class HintExtractor(Extractor):
        supported_collections = ["C1"]

        def extract(
            self,
            extraction_task: ExtractionTask,
            extract_params: dict[str, Any] | None,
        ) -> GeoDataFrame[ArtifactSchema]:
            return cast(GeoDataFrame[ArtifactSchema], extraction_task.assets)

    extractor = HintExtractor()

    from datetime import datetime
    from aer.interfaces.core import AerProfile

    df = gpd.GeoDataFrame(
        {
            "id": [1],
            "collection": ["C1"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
        ],
    )

    grid_config = GridConfig(target_grid_dist=1_000_000)
    profile = AerProfile(name="test_profile", resolution=10.0)

    tasks = extractor.prepare_for_extraction(
        cast(Any, df),
        grid_config=grid_config,
        profiles=[profile],
        uri="test_uri",
        extractor_hint="aer-extract-dummy",
    )

    assert len(tasks) > 0
    assert tasks[0].task_context["extractor_hint"] == "aer-extract-dummy"


def test_grid_config_defaults_require_explicit_dist():
    gc = GridConfig(target_grid_dist=50_000)
    assert gc.target_grid_dist == 50_000
    assert gc.target_grid_overlap is False
    assert gc.target_grid_margin == 0.0
    assert gc.grid_filter_mode == "intersection"


def test_grid_config_literal_validation():
    with pytest.raises(ValidationError):
        GridConfig(grid_filter_mode="invalid")  # pyright: ignore[reportArgumentType]


def test_grid_config_from_yaml_string():
    yaml_text = """
    target_grid_dist: 100000
    target_grid_margin: 6.8
    """
    gc = GridConfig.from_yaml_string(yaml_text)
    assert gc.target_grid_dist == 100_000
    assert gc.target_grid_margin == 6.8


def test_grid_config_is_frozen():
    gc = GridConfig(target_grid_dist=50_000)
    with pytest.raises(ValidationError):
        gc.target_grid_dist = 100_000


def test_grid_config_forbids_extra_fields():
    with pytest.raises(ValidationError):
        GridConfig(target_grid_dist=50_000, unknown_field=42)  # pyright: ignore[reportCallIssue]


def test_grid_config_from_yaml_with_wrapper():
    yaml_text = """
    grid_config:
      target_grid_dist: 50000
      target_grid_overlap: false
      target_grid_margin: 6.8
      grid_filter_mode: intersection
      min_coverage: 0.0
    """
    gc = GridConfig.from_yaml_string(yaml_text)
    assert gc.target_grid_dist == 50_000
    assert gc.target_grid_overlap is False
    assert gc.target_grid_margin == 6.8
    assert gc.grid_filter_mode == "intersection"
    assert gc.min_coverage == 0.0


def test_grid_config_from_json(tmp_path):
    import json

    path = tmp_path / "grid.json"
    path.write_text(json.dumps({"target_grid_dist": 25000, "min_coverage": 0.5}))
    gc = GridConfig.from_json(path)
    assert gc.target_grid_dist == 25_000
    assert gc.min_coverage == 0.5


@pytest.mark.parametrize(
    "config_file",
    [
        "goes_512km.json",
        "goes_256km.json",
        "sentinel2_50km.json",
        "ml_patch_2_56km.json",
    ],
)
def test_example_grid_configs_load(config_file):
    from pathlib import Path

    grid_configs_dir = Path(__file__).parents[4] / "examples" / "grid_configs"
    path = grid_configs_dir / config_file
    assert path.exists(), f"Example grid config not found: {path}"
    gc = GridConfig.from_json(path)
    assert gc.target_grid_dist is not None
    assert isinstance(gc.target_grid_overlap, bool)


def test_prepare_for_extraction_spatial_filtering():
    """Verify that prepare_for_extraction filters assets to only those intersecting chunk grid cells."""
    from datetime import datetime
    from aer.interfaces.core import AerProfile
    from shapely.geometry import Polygon

    class DummyExtractor(Extractor):
        supported_collections = ["C1"]

        def extract(self, extraction_task, extract_params):
            return cast(Any, extraction_task.assets)

    # Asset 1 at coordinates (0, 0)
    # Asset 2 at coordinates (10, 10) - very far away
    df = gpd.GeoDataFrame(
        {
            "id": ["asset_1", "asset_2"],
            "collection": ["C1", "C1"],
            "start_time": [datetime(2023, 1, 1, 12, 0), datetime(2023, 1, 1, 12, 0)],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
            Polygon([[10, 10], [11, 10], [11, 11], [10, 11]]),
        ],
    )

    profile = AerProfile(name="test", resolution=1000.0, collections={"C1": ["var1"]})
    grid_config = GridConfig(target_grid_dist=100_000)
    extractor = DummyExtractor()

    tasks = extractor.prepare_for_extraction(
        cast(Any, df),
        grid_config=grid_config,
        profiles=[profile],
        uri="test_uri",
        cells_per_chunk=1,
    )

    # Check that every task only contains 1 asset (either asset_1 or asset_2) because
    # the cells in each chunk only intersect one of the two far-apart assets.
    for task in tasks:
        assert len(task.assets) == 1

    # Check that both assets are represented across all tasks
    all_assigned = set()
    for task in tasks:
        all_assigned.update(task.assets["id"])
    assert all_assigned == {"asset_1", "asset_2"}
