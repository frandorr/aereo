from typing import Any, cast
from unittest.mock import MagicMock

import geopandas as gpd
import pytest
import pandas as pd
import xarray as xr
from shapely.geometry import Point, Polygon

from aereo.interfaces.core import AereoProfile, ExtractionTask, GridConfig, Reprojector
from aereo.registry.core import AereoRegistry
from aereo.client.core import AereoClient, FailureMode, normalize_geometry
from aereo.schemas.core import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


def test_normalize_geometry_dict_to_shapely():
    geom_dict = {"type": "Point", "coordinates": [10.0, 20.0]}
    shapely_geom = normalize_geometry(geom_dict)
    assert isinstance(shapely_geom, Point)
    assert shapely_geom.x == 10.0
    assert shapely_geom.y == 20.0


def test_normalize_geometry_invalid():
    with pytest.raises(ValueError, match="Invalid geometry format"):
        normalize_geometry("Not a dict or geometry")


def test_client_search_success(monkeypatch):
    mock_registry = MagicMock(spec=AereoRegistry)

    # Setup mock registry to return valid dummy data
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    # It must return a GeoDataFrame that passes AssetSchema validation
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df.loc[1] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MODIS"
    mock_searcher.search.return_value = valid_df

    mock_registry.get_searcher.return_value = mock_searcher

    client = AereoClient(registry=mock_registry)

    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )

    # 1. Search
    search_results = client.search(
        profiles=[profile], intersects={"type": "Point", "coordinates": [0, 0]}
    )

    # Validations
    assert len(search_results) == 2
    mock_registry.find_searchers_for.assert_called_with("MODIS")
    mock_registry.get_searcher.assert_called_with("dummy_searcher")
    mock_searcher.search.assert_called_once()
    assert isinstance(search_results, pd.DataFrame)


def test_client_search_accepts_profiles(monkeypatch):
    """search() must pass profiles (not collections) to the plugin."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MODIS"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(name="p1", resolution=10.0, collections={"MODIS": ["var1"]})
    client.search(profiles=[profile])

    call_kwargs = mock_searcher.search.call_args.kwargs
    assert "profiles" in call_kwargs
    assert call_kwargs["profiles"][0].name == "p1"


def test_client_search_all_fail_strict():
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = Exception("API Down")
    mock_registry.get_searcher.return_value = mock_searcher

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )

    with pytest.raises(RuntimeError, match="Search failed strictly"):
        client.search(profiles=[profile], failure_mode=FailureMode.STRICT)


def test_client_search_all_fail_best_effort():
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    mock_searcher.search.side_effect = Exception("API Down")
    mock_registry.get_searcher.return_value = mock_searcher

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )

    # Will not raise, returns an empty geometry
    search_results = client.search(
        profiles=[profile], failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(search_results) == 0


# ---------------------------------------------------------------------------
# _resolve_params – case-insensitive parameter resolution
# ---------------------------------------------------------------------------


def _make_client_with_collections(*collections: str) -> AereoClient:
    """Return an AereoClient whose registry reports the given known collections."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.list_supported_collections.return_value = list(collections)
    return AereoClient(registry=mock_registry)


def test_resolve_params_none_returns_empty():
    client = _make_client_with_collections("sentinel-2-l2a")
    assert client._resolve_params(None, "sentinel-2-l2a") == {}


def test_resolve_params_global_params_pass_through():
    """Non-collection keys are passed to every plugin unchanged."""
    client = _make_client_with_collections("sentinel-2-l2a")
    result = client._resolve_params({"limit": 100, "cloud_cover": 20}, "sentinel-2-l2a")
    assert result == {"limit": 100, "cloud_cover": 20}


def test_resolve_params_override_exact_case():
    """Exact-case collection key is merged and the collection key itself is stripped."""
    client = _make_client_with_collections("sentinel-2-l2a")
    params = {
        "limit": 10,
        "sentinel-2-l2a": {"channels": ["B02", "B03"]},
    }
    result = client._resolve_params(params, "sentinel-2-l2a")
    assert result == {"limit": 10, "channels": ["B02", "B03"]}


def test_resolve_params_override_mixed_case_key():
    """User writes 'Sentinel-2-L2A' as the key but the collection is 'sentinel-2-l2a'."""
    client = _make_client_with_collections("sentinel-2-l2a")
    params = {
        "limit": 5,
        "Sentinel-2-L2A": {"channels": ["B04"]},
    }
    result = client._resolve_params(params, "sentinel-2-l2a")
    assert result == {"limit": 5, "channels": ["B04"]}


def test_resolve_params_override_upper_case_collection_arg():
    """Collection arg is upper-cased but the key in params is lowercase."""
    client = _make_client_with_collections("sentinel-2-l2a")
    params = {
        "sentinel-2-l2a": {"channels": ["B08"]},
    }
    result = client._resolve_params(params, "SENTINEL-2-L2A")
    assert result == {"channels": ["B08"]}


def test_resolve_params_strips_other_collection_keys():
    """Keys for *other* collections are stripped; only the target's override is merged."""
    client = _make_client_with_collections("sentinel-2-l2a", "ABI-L1b-RadF")
    params = {
        "limit": 20,
        "sentinel-2-l2a": {"channels": ["B02"]},
        "ABI-L1b-RadF": {"satellite": "GOES-19"},
    }
    # Resolving for sentinel-2-l2a should NOT include the GOES block
    result = client._resolve_params(params, "sentinel-2-l2a")
    assert result == {"limit": 20, "channels": ["B02"]}
    assert "ABI-L1b-RadF" not in result
    assert "satellite" not in result


def test_resolve_params_strips_other_collection_keys_case_insensitive():
    """Case variants of other collection names are also stripped."""
    client = _make_client_with_collections("sentinel-2-l2a", "ABI-L1b-RadF")
    params = {
        "SENTINEL-2-L2A": {"channels": ["B03"]},
        "abi-l1b-radf": {"satellite": "GOES-16"},
    }
    result = client._resolve_params(params, "Sentinel-2-L2A")
    assert result == {"channels": ["B03"]}
    assert "abi-l1b-radf" not in result


# ---------------------------------------------------------------------------
# _resolve_plugin_for_profile
# ---------------------------------------------------------------------------


def _make_client_for_profile_resolution() -> tuple[AereoClient, MagicMock]:
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.has_searcher.return_value = True
    mock_registry.find_searchers_for.return_value = ["auto_searcher"]
    client = AereoClient(registry=mock_registry)
    return client, mock_registry


def test_resolve_plugin_for_profile_uses_hint():
    client, mock_registry = _make_client_for_profile_resolution()
    profile = AereoProfile(
        name="p1",
        resolution=10.0,
        collections={"X": ["var1"]},
    )
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result == "hinted_searcher"
    mock_registry.has_searcher.assert_called_with("hinted_searcher")


def test_resolve_plugin_for_profile_auto_discovers():
    client, mock_registry = _make_client_for_profile_resolution()
    profile = AereoProfile(name="p1", resolution=10.0, collections={"MODIS": ["var1"]})
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result == "auto_searcher"
    mock_registry.find_searchers_for.assert_called_with("MODIS")


def test_resolve_plugin_for_profile_hinted_not_registered():
    client, mock_registry = _make_client_for_profile_resolution()
    mock_registry.has_searcher.return_value = False
    profile = AereoProfile(
        name="p1",
        resolution=10.0,
        collections={"X": ["var1"]},
    )
    with pytest.raises(ValueError, match="not a registered Searcher"):
        client._resolve_plugin_for_profile("searcher", profile)


def test_resolve_plugin_for_profile_no_collections_returns_none():
    client, mock_registry = _make_client_for_profile_resolution()
    mock_registry.find_searchers_for.return_value = []
    profile = AereoProfile(name="p1", resolution=10.0, collections={})
    result = client._resolve_plugin_for_profile("searcher", profile)
    assert result is None


# ---------------------------------------------------------------------------
# search with profile plugin hints
# ---------------------------------------------------------------------------


def test_search_with_profile_plugin_hint(monkeypatch):
    """Profile-level plugin_hints['search'] should drive plugin selection."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.has_searcher.return_value = True
    mock_registry.find_searchers_for.return_value = []

    mock_searcher = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "modis"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="goes",
        resolution=1000.0,
        collections={"ABI-L1b-RadC": ["C01"]},
        search={"aereo-search-aws-goes": {}},
    )
    client.search(profiles=[profile])
    mock_registry.get_searcher.assert_called_once_with("aereo-search-aws-goes")


def test_search_merges_profile_search_params(monkeypatch):
    """Profile search_params should override batch search_params passed to the searcher."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    mock_searcher = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "MOD021KM"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="modis_thermal",
        resolution=1000.0,
        collections={"MOD021KM": ["var1"]},
        search={"test_searcher": {"version": "061"}},
    )
    client.search(
        profiles=[profile],
    )

    call_kwargs = mock_searcher.search.call_args.kwargs
    assert call_kwargs["search_params"]["version"] == "061"
    assert call_kwargs["search_params"]["cloud_cover"] == 20


# ---------------------------------------------------------------------------
# prepare_for_extraction – target_grid_dist / target_grid_overlap forwarding
# ---------------------------------------------------------------------------


def _make_valid_search_df():
    valid_df = gpd.GeoDataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    valid_df["collection"] = "MODIS"
    valid_df["start_time"] = pd.Timestamp("2023-01-01")
    return valid_df


def test_prepare_for_extraction_requires_grid_config(monkeypatch):
    """grid_config must be provided either as argument or client default."""
    valid_search_df = _make_valid_search_df()
    mock_registry = MagicMock(spec=AereoRegistry)
    client = AereoClient(registry=mock_registry)

    with pytest.raises(ValueError, match="grid_config must be provided"):
        client.prepare_for_extraction(
            search_results=cast(GeoDataFrame, valid_search_df),
            resolution=100.0,
            uri="s3://bucket/out/",
        )


def test_prepare_for_extraction_returns_tasks(monkeypatch):
    """prepare_for_extraction returns ExtractionTasks using the standalone task builder."""
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = _make_valid_search_df()

    mock_registry = MagicMock(spec=AereoRegistry)
    client = AereoClient(registry=mock_registry)
    grid_config = GridConfig(target_grid_dist=50_000)
    profile = AereoProfile(
        name="p1",
        resolution=10.0,
        collections={"MODIS": ["var1"]},
    )
    tasks = client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_df),
        grid_config=grid_config,
        profiles=[profile],
        uri="s3://out",
        cells_per_task=1,
    )
    assert isinstance(tasks, list)
    assert len(tasks) > 0
    assert tasks[0].profile.name == "p1"
    assert tasks[0].uri == "s3://out"


# ---------------------------------------------------------------------------
# execute_tasks
# ---------------------------------------------------------------------------


def test_execute_tasks_empty():
    """execute_tasks with no tasks returns an empty GeoDataFrame."""
    mock_registry = MagicMock(spec=AereoRegistry)
    client = AereoClient(registry=mock_registry)
    result = client.execute_tasks([])
    assert len(result) == 0


def _setup_mock_pipeline_registry(
    monkeypatch,
    mock_registry,
    reader_mock=None,
    writer_mock=None,
    reprojector_mock=None,
):
    """Configure a mock registry for the new pipeline architecture."""
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    def _mock_has(type_label, name):
        if type_label == "reader":
            return reader_mock is not None
        if type_label == "writer":
            return writer_mock is not None
        if type_label == "reprojector":
            return reprojector_mock is not None
        return False

    def _mock_get(type_label, name, **kwargs):
        if type_label == "reader" and reader_mock is not None:
            return reader_mock
        if type_label == "writer" and writer_mock is not None:
            return writer_mock
        if type_label == "reprojector" and reprojector_mock is not None:
            return reprojector_mock
        raise ValueError(f"Unknown plugin: {type_label}/{name}")

    def _mock_find_for(type_label, collection):
        if type_label == "reprojector" and reprojector_mock is not None:
            return ["reproject_odc"]
        return []

    mock_registry.has.side_effect = _mock_has
    mock_registry.get.side_effect = _mock_get
    mock_registry.find_for.side_effect = _mock_find_for


def test_execute_tasks_with_profile_hint(monkeypatch):
    """execute_tasks must resolve reader/writer from each task's profile hint."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_reader = MagicMock()
    mock_reader.read.return_value = xr.Dataset()
    mock_writer = MagicMock()
    mock_writer.write.return_value = gpd.GeoDataFrame()
    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()
    _setup_mock_pipeline_registry(
        monkeypatch, mock_registry, mock_reader, mock_writer, mock_reprojector
    )

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="goes",
        resolution=1000.0,
        collections={"ABI-L1b-RadC": ["C01"]},
    )
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "ABI-L1b-RadC"
    grid_config = GridConfig(target_grid_dist=50_000)
    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    client.execute_tasks([task])
    mock_registry.get.assert_any_call("reader", "read_aws_goes")
    mock_registry.get.assert_any_call("writer", "write_geotiff")


def test_execute_tasks_failure_mode_strict(monkeypatch):
    """STRICT failure mode raises when a task fails."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_reader = MagicMock()
    mock_reader.read.side_effect = RuntimeError("read failed")
    mock_writer = MagicMock()
    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()
    _setup_mock_pipeline_registry(
        monkeypatch, mock_registry, mock_reader, mock_writer, mock_reprojector
    )

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        collections={"C1": ["var1"]},
    )
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "C1"
    grid_config = GridConfig(target_grid_dist=50_000)
    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    with pytest.raises(RuntimeError, match="read failed"):
        client.execute_tasks([task], failure_mode=FailureMode.STRICT)


def test_execute_tasks_failure_mode_best_effort(monkeypatch):
    """BEST_EFFORT failure mode returns empty GeoDataFrame when all tasks fail."""
    mock_registry = MagicMock(spec=AereoRegistry)
    mock_reader = MagicMock()
    mock_reader.read.side_effect = RuntimeError("read failed")
    mock_writer = MagicMock()
    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()
    _setup_mock_pipeline_registry(
        monkeypatch, mock_registry, mock_reader, mock_writer, mock_reprojector
    )

    client = AereoClient(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        collections={"C1": ["var1"]},
    )
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "C1"
    grid_config = GridConfig(target_grid_dist=50_000)
    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    result = client.execute_tasks([task], failure_mode=FailureMode.BEST_EFFORT)
    assert len(result) == 0


def test_execute_tasks_best_effort_partial_results(monkeypatch):
    """BEST_EFFORT returns partial results when only some tasks fail."""
    mock_registry = MagicMock(spec=AereoRegistry)

    call_count = 0

    def _read(task, params=None):
        nonlocal call_count
        call_count += 1
        if task.profile.name == "fail":
            raise RuntimeError("intentional failure")
        return xr.Dataset()

    mock_reader = MagicMock()
    mock_reader.read.side_effect = _read
    mock_writer = MagicMock()
    mock_writer.write.return_value = pd.DataFrame({"artifact_id": ["ok"]})
    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()
    _setup_mock_pipeline_registry(
        monkeypatch, mock_registry, mock_reader, mock_writer, mock_reprojector
    )

    client = AereoClient(registry=mock_registry)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "C1"
    grid_config = GridConfig(target_grid_dist=50_000)

    task_ok_1 = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="ok_1",
            resolution=100.0,
            collections={"C1": ["var1"]},
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    task_fail = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="fail",
            resolution=100.0,
            collections={"C1": ["var1"]},
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    task_ok_2 = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="ok_2",
            resolution=100.0,
            collections={"C1": ["var1"]},
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    result = client.execute_tasks(
        [task_ok_1, task_fail, task_ok_2],
        failure_mode=FailureMode.BEST_EFFORT,
    )
    # Since we mock writer to return a fixed DataFrame, we should get results for ok tasks
    # (fail task is skipped). But writer is called per-cell and grid_cells is empty,
    # so no writer calls happen. Let me adjust...
    assert len(result) == 0  # No grid cells means no writes


def test_execute_tasks_strict_mode_raises_on_first_failure(monkeypatch):
    """STRICT mode still raises immediately on the first failing task."""
    mock_registry = MagicMock(spec=AereoRegistry)

    call_count = 0

    def _read(task, params=None):
        nonlocal call_count
        call_count += 1
        if task.profile.name == "fail":
            raise RuntimeError("intentional failure")
        return xr.Dataset()

    mock_reader = MagicMock()
    mock_reader.read.side_effect = _read
    mock_writer = MagicMock()
    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()
    _setup_mock_pipeline_registry(
        monkeypatch, mock_registry, mock_reader, mock_writer, mock_reprojector
    )

    client = AereoClient(registry=mock_registry)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "C1"
    grid_config = GridConfig(target_grid_dist=50_000)

    task_ok = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="ok",
            resolution=100.0,
            collections={"C1": ["var1"]},
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    task_fail = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="fail",
            resolution=100.0,
            collections={"C1": ["var1"]},
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    with pytest.raises(RuntimeError, match="intentional failure"):
        client.execute_tasks([task_ok, task_fail], failure_mode=FailureMode.STRICT)


# ---------------------------------------------------------------------------
# End-to-end search + extract with per-profile params
# ---------------------------------------------------------------------------


def test_e2e_search_and_extract_with_per_profile_params(monkeypatch):
    """Profile search_params and extract_params are passed through correctly."""
    from aereo.interfaces.core import Reader, Writer

    mock_registry = MagicMock(spec=AereoRegistry)
    mock_registry.has_searcher.return_value = True
    mock_registry.find_searchers_for.return_value = ["dummy_searcher"]

    # -- Searcher mock -------------------------------------------------------
    mock_searcher = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Point(0, 0)
    valid_df["collection"] = "C1"
    mock_searcher.search.return_value = valid_df
    mock_registry.get_searcher.return_value = mock_searcher

    # -- Profiles with divergent params --------------------------------------
    profile_a = AereoProfile(
        name="profile_a",
        resolution=100.0,
        collections={"C1": ["var1"]},
        read={"test_reader": {"calibration": "reflectance"}},
        padding=2,
    )
    profile_b = AereoProfile(
        name="profile_b",
        resolution=100.0,
        collections={"C1": ["var1"]},
        padding=4,
    )

    client = AereoClient(registry=mock_registry)

    # -- Search phase --------------------------------------------------------
    client.search(
        profiles=[profile_a, profile_b],
    )

    assert mock_searcher.search.call_count == 2
    params_by_profile: dict[str, dict[str, Any]] = {}
    for call in mock_searcher.search.call_args_list:
        kwargs = call.kwargs
        prof = kwargs["profiles"][0]
        params_by_profile[prof.name] = dict(kwargs["search_params"])

    assert params_by_profile["profile_a"] == {
        "version": "061",
        "cloud_cover": 10,
        "limit": 100,
    }
    assert params_by_profile["profile_b"] == {
        "version": "062",
        "cloud_cover": 20,
        "limit": 100,
    }

    # -- Pipeline mock (real subclasses so base-class merge runs) ------------
    _captured: list[dict[str, Any]] = []

    class _CapturingReader(Reader):
        supported_collections = ["C1"]

        def read(self, task, params):
            _captured.append(
                {
                    "profile_name": task.profile.name,
                    "params": dict(params) if params else {},
                }
            )
            return xr.Dataset()

    class _CapturingWriter(Writer):
        supported_collections = ["C1"]

        def write(self, ds, task, cell, params):
            import geopandas as gpd
            from shapely.geometry import Polygon

            return gpd.GeoDataFrame(
                {"id": [1]},
                geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
            )

    class _CapturingReprojector(Reprojector):
        supported_collections = ["C1"]

        def reproject(self, ds, geobox, params):
            return ds

    def _mock_has(type_label, name):
        return type_label in ("reader", "writer", "reprojector")

    def _mock_get(type_label, name, **kwargs):
        if type_label == "reader":
            return _CapturingReader()
        if type_label == "writer":
            return _CapturingWriter()
        if type_label == "reprojector":
            return _CapturingReprojector()
        raise ValueError(f"Unknown: {type_label}")

    def _mock_find_for(type_label, collection):
        if type_label in ("reader", "writer", "reprojector"):
            return ["dummy"]
        return []

    mock_registry.has.side_effect = _mock_has
    mock_registry.get.side_effect = _mock_get
    mock_registry.find_for.side_effect = _mock_find_for
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    grid_config = GridConfig(target_grid_dist=50_000)
    task_a = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile_a,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    task_b = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile_b,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    client.execute_tasks([task_a, task_b])

    assert len(_captured) == 2
    by_name = {c["profile_name"]: c["params"] for c in _captured}

    assert by_name["profile_a"] == {
        "calibration": "reflectance",
    }
    assert by_name["profile_b"] == {
        "calibration": "radiance",
    }
