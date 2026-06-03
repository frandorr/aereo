from typing import Any, Sequence, cast

import geopandas as gpd
import pytest
from aereo.interfaces import (
    AereoDataset,
    AereoPlugin,
    GridConfig,
    SearchProvider,
    merge_params,
    validate_aereo_dataset,
)
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ValidationError
from shapely.geometry import Polygon


def test_plugin_missing_supported_collections():
    with pytest.raises(
        TypeError, match="must define the 'supported_collections' attribute"
    ):

        class InvalidPlugin(AereoPlugin):
            pass


def test_plugin_supported_collections_is_string():
    with pytest.raises(
        TypeError, match="must be a Sequence of strings .* got a single string"
    ):

        class InvalidPlugin(AereoPlugin):
            supported_collections = "GOES-16"


def test_plugin_supported_collections_is_not_sequence():
    with pytest.raises(TypeError, match="must be a Sequence .* got int"):

        class InvalidPlugin(AereoPlugin):
            supported_collections = 123  # pyright: ignore[reportAssignmentType]


def test_plugin_supported_collections_is_empty():
    class InvalidPlugin(AereoPlugin):
        supported_collections = []

    assert InvalidPlugin.supported_collections == []


def test_plugin_valid_supported_collections():
    class ValidPlugin(AereoPlugin):
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
    from aereo.interfaces.core import AereoProfile

    class GoodSearcher(SearchProvider):
        supported_collections = ["X"]

        def search(
            self,
            profiles: Sequence[AereoProfile],
            intersects: Any,
            start_datetime: Any,
            end_datetime: Any,
            search_params: Any,
        ) -> Any: ...

    # Should instantiate without error
    searcher = GoodSearcher()
    assert searcher is not None


def test_aereo_profile_has_all_fields():
    from aereo.interfaces.core import AereoProfile

    profile = AereoProfile(
        name="goes_16_abi",
        resolution=1000.0,
        collections={"ABI-L1b-RadC": ["C01", "C02"]},
        search={
            "aereo-search-aws-goes": {},
        },
    )
    assert profile.collections == {"ABI-L1b-RadC": ["C01", "C02"]}
    assert profile.search is not None
    assert "aereo-search-aws-goes" in profile.search


def test_aereo_profile_defaults():
    from aereo.interfaces.core import AereoProfile

    profile = AereoProfile(name="minimal", resolution=100.0)
    assert profile.collections == {}
    assert profile.search is None
    assert profile.read is None
    assert profile.reproject is None
    assert profile.write is None
    assert profile.pre_processors == []
    assert profile.post_processors == []
    assert profile.conform_to is None


def test_aereo_profile_accepts_conform_to():
    from aereo.interfaces.core import AereoProfile

    profile = AereoProfile(name="test", resolution=100.0, conform_to=(256, 256))
    assert profile.conform_to == (256, 256)


def test_extraction_task_accepts_aereo_profile():

    from aereo.interfaces.core import AereoProfile, ExtractionTask

    df = gpd.GeoDataFrame(
        {"collection": ["GOES"], "start_time": ["2023-01-01"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    profile = AereoProfile(name="test", resolution=10.0, collections={"GOES": ["var1"]})
    grid_config = GridConfig(target_grid_dist=10_000)
    task = ExtractionTask(
        assets=cast(GeoDataFrame, df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    assert task.profile.name == "test"


def test_aereo_profile_is_frozen():
    from aereo.interfaces.core import AereoProfile

    profile = AereoProfile(name="test", resolution=100.0)
    with pytest.raises(ValidationError):
        profile.resolution = 200.0


def test_aereo_profile_forbids_extra_fields():
    from aereo.interfaces.core import AereoProfile

    with pytest.raises(ValidationError):
        AereoProfile(name="test", resolution=100.0, unknown_field=42)  # pyright: ignore[reportCallIssue]


def test_aereo_profile_rejects_extra_params():
    from aereo.interfaces.core import AereoProfile

    with pytest.raises(ValidationError):
        AereoProfile(name="test", resolution=100.0, extra_params={"foo": "bar"})  # pyright: ignore[reportCallIssue]


def test_merge_params_batch_only():
    assert merge_params({"a": 1}, {}) == {"a": 1}


def test_merge_params_profile_overrides():
    assert merge_params({"a": 1}, {"a": 2}) == {"a": 2}


def test_merge_params_combined():
    assert merge_params({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merge_params_none_batch():
    assert merge_params(None, {"a": 1}) == {"a": 1}


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


# ---------------------------------------------------------------------------
# AereoDataset (Phase 0)
# ---------------------------------------------------------------------------


def test_aereo_dataset_is_xarray_dataset():
    """AereoDataset must be an xarray.Dataset at runtime."""
    import xarray as xr

    assert AereoDataset is xr.Dataset


def test_validate_aereo_dataset_accepts_valid():
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {"B04": (["y", "x"], np.ones((4, 4)))},
        coords={"y": range(4), "x": range(4)},
    )
    # rioxarray crs is None by default, so we set require_crs=False
    validate_aereo_dataset(ds, require_crs=False)


def test_validate_aereo_dataset_rejects_non_dataset():
    with pytest.raises(ValueError, match="Expected xarray.Dataset"):
        validate_aereo_dataset("not a dataset", require_crs=False)


def test_validate_aereo_dataset_checks_required_dims():
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {"B04": (["y", "x"], np.ones((4, 4)))},
        coords={"y": range(4), "x": range(4)},
    )
    validate_aereo_dataset(ds, require_crs=False, require_dims=["y", "x"])

    with pytest.raises(ValueError, match="missing required dimensions"):
        validate_aereo_dataset(ds, require_crs=False, require_dims=["time"])


def test_validate_aereo_dataset_checks_crs_when_required():
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {"B04": (["y", "x"], np.ones((4, 4)))},
        coords={"y": range(4), "x": range(4)},
    )
    # Without rioxarray crs, require_crs=True should fail
    with pytest.raises(ValueError, match="must have a CRS"):
        validate_aereo_dataset(ds, require_crs=True)
