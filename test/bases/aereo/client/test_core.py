from typing import cast
from unittest.mock import MagicMock

import geopandas as gpd
import pytest
import pandas as pd
from shapely.geometry import Point

from aereo.client.core import AereoClient, FailureMode, normalize_geometry
from aereo.interfaces.core import AereoProfile, ExtractionTask, GridConfig
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


def _make_mock_gdf() -> GeoDataFrame:
    cols = list(AssetSchema.to_schema().columns.keys())
    df = pd.DataFrame(columns=cols)
    df.loc[0] = {col: "test" for col in cols}
    df["geometry"] = Point(0, 0)
    df["collection"] = "MODIS"
    return cast(GeoDataFrame, df)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_client_search_uses_hamilton_driver(monkeypatch):
    """search() delegates to AereoDriver.search() for each profile."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    mock_driver.search.return_value = _make_mock_gdf()
    monkeypatch.setattr(client, "_driver", mock_driver)

    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )
    result = client.search(profiles=[profile])
    mock_driver.search.assert_called_once()
    assert len(result) == 1


def test_client_search_passes_profiles_to_driver(monkeypatch):
    """The profile object is forwarded to the driver."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    mock_driver.search.return_value = _make_mock_gdf()
    monkeypatch.setattr(client, "_driver", mock_driver)

    profile = AereoProfile(name="p1", resolution=10.0, collections={"MODIS": ["var1"]})
    client.search(profiles=[profile])
    call_args = mock_driver.search.call_args.args
    assert call_args[0].name == "p1"


def test_client_search_all_fail_strict(monkeypatch):
    """STRICT failure mode raises when the driver fails."""
    client = AereoClient()
    mock_driver = MagicMock()
    mock_driver.search.side_effect = RuntimeError("API Down")
    monkeypatch.setattr(client, "_driver", mock_driver)

    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )
    with pytest.raises(RuntimeError, match="Search failed strictly"):
        client.search(profiles=[profile], failure_mode=FailureMode.STRICT)


def test_client_search_all_fail_best_effort(monkeypatch):
    """BEST_EFFORT returns an empty GeoDataFrame when the driver fails."""
    client = AereoClient()
    mock_driver = MagicMock()
    mock_driver.search.side_effect = RuntimeError("API Down")
    monkeypatch.setattr(client, "_driver", mock_driver)

    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )
    result = client.search(profiles=[profile], failure_mode=FailureMode.BEST_EFFORT)
    assert len(result) == 0


def test_client_search_merges_batch_search_params(monkeypatch):
    """Batch search_params are merged with profile search_params (profile wins)."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    mock_driver.search.return_value = _make_mock_gdf()
    monkeypatch.setattr(client, "_driver", mock_driver)

    profile = AereoProfile(
        name="modis",
        resolution=1000.0,
        collections={"MODIS": ["var1"]},
        search_params={"version": "061"},
    )
    client.search(
        profiles=[profile],
        search_params={"version": "000", "cloud_cover": 20},
    )
    passed_profile = mock_driver.search.call_args.args[0]
    assert passed_profile.search_params == {
        "version": "061",
        "cloud_cover": 20,
    }


def test_client_search_ignores_init_params(monkeypatch):
    """init_params is accepted for backward compatibility but not forwarded."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    mock_driver.search.return_value = _make_mock_gdf()
    monkeypatch.setattr(client, "_driver", mock_driver)

    profile = AereoProfile(
        name="modis", resolution=1000.0, collections={"MODIS": ["var1"]}
    )
    client.search(profiles=[profile], init_params={"timeout": 30})
    mock_driver.search.assert_called_once()


# ---------------------------------------------------------------------------
# prepare_for_extraction
# ---------------------------------------------------------------------------


def test_prepare_for_extraction_empty_search_results():
    """Empty search results yield an empty task list."""
    client = AereoClient()
    result = client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, AssetSchema.empty()),
    )
    assert result == []


def test_prepare_for_extraction_requires_grid_config():
    """grid_config must be provided either as argument or client default."""
    client = AereoClient()
    valid_df = _make_mock_gdf()
    with pytest.raises(ValueError, match="grid_config must be provided"):
        client.prepare_for_extraction(
            search_results=cast(GeoDataFrame, valid_df),
            resolution=100.0,
            uri="s3://bucket/out/",
        )


def test_prepare_for_extraction_uses_driver(monkeypatch):
    """prepare_for_extraction delegates to AereoDriver.prepare()."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)
    profile = AereoProfile(name="p1", resolution=10.0, collections={"MODIS": ["var1"]})
    mock_driver.prepare.return_value = []

    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_df),
        grid_config=grid_config,
        profiles=[profile],
        uri="s3://out",
    )
    mock_driver.prepare.assert_called_once()
    call_args = mock_driver.prepare.call_args.args
    call_kwargs = mock_driver.prepare.call_args.kwargs
    assert call_args[2] == grid_config
    assert call_kwargs["uri"] == "s3://out"


def test_prepare_for_extraction_passes_cells_per_task(monkeypatch):
    """cells_per_task is forwarded to the driver."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)
    profile = AereoProfile(name="p1", resolution=10.0, collections={"MODIS": ["var1"]})
    mock_driver.prepare.return_value = []

    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_df),
        grid_config=grid_config,
        profiles=[profile],
        uri="s3://out",
        cells_per_task=10,
    )
    assert mock_driver.prepare.call_args.kwargs["cells_per_task"] == 10


def test_prepare_for_extraction_with_resolution(monkeypatch):
    """When no profiles are given, a default profile is built from resolution."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)
    mock_driver.prepare.return_value = []

    client.prepare_for_extraction(
        search_results=cast(GeoDataFrame, valid_df),
        grid_config=grid_config,
        resolution=100.0,
        uri="s3://out",
    )
    call_args = mock_driver.prepare.call_args.args
    assert call_args[1].name == "default"
    assert call_args[1].resolution == 100.0


# ---------------------------------------------------------------------------
# execute_tasks
# ---------------------------------------------------------------------------


def test_execute_tasks_empty():
    """execute_tasks with no tasks returns an empty GeoDataFrame."""
    mock_registry = MagicMock()
    client = AereoClient(registry=mock_registry)
    result = client.execute_tasks([])
    assert len(result) == 0


def test_execute_tasks_uses_driver_extract(monkeypatch):
    """execute_tasks delegates to AereoDriver.extract() via the backend."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    mock_driver.extract.return_value = gpd.GeoDataFrame()
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)
    profile = AereoProfile(
        name="test", resolution=100.0, collections={"MODIS": ["var1"]}
    )
    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    client.execute_tasks([task])
    assert mock_driver.extract.call_count == 1
    assert mock_driver.extract.call_args.args[0] is task


def test_execute_tasks_failure_mode_strict(monkeypatch):
    """STRICT failure mode raises when a task fails."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    mock_driver.extract.side_effect = RuntimeError("extract failed")
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)
    profile = AereoProfile(
        name="test", resolution=100.0, collections={"MODIS": ["var1"]}
    )
    task = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=profile,
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    with pytest.raises(RuntimeError, match="extract failed"):
        client.execute_tasks([task], failure_mode=FailureMode.STRICT)


def test_execute_tasks_failure_mode_best_effort(monkeypatch):
    """BEST_EFFORT returns an empty GeoDataFrame when all tasks fail."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    mock_driver.extract.side_effect = RuntimeError("extract failed")
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)
    profile = AereoProfile(
        name="test", resolution=100.0, collections={"MODIS": ["var1"]}
    )
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
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    def _extract(task):
        if task.profile.name == "fail":
            raise RuntimeError("intentional failure")
        return gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])

    mock_driver.extract.side_effect = _extract
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)

    task_ok = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="ok", resolution=100.0, collections={"MODIS": ["var1"]}
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    task_fail = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="fail", resolution=100.0, collections={"MODIS": ["var1"]}
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    result = client.execute_tasks(
        [task_ok, task_fail],
        failure_mode=FailureMode.BEST_EFFORT,
    )
    assert len(result) == 1
    assert result.iloc[0]["id"] == 1


def test_execute_tasks_strict_mode_raises_on_first_failure(monkeypatch):
    """STRICT mode raises immediately on the first failing task."""
    client = AereoClient()
    mock_driver = MagicMock()
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    def _extract(task):
        if task.profile.name == "fail":
            raise RuntimeError("intentional failure")
        return gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)])

    mock_driver.extract.side_effect = _extract
    monkeypatch.setattr(client, "_driver", mock_driver)

    valid_df = _make_mock_gdf()
    grid_config = GridConfig(target_grid_dist=50_000)

    task_ok = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="ok", resolution=100.0, collections={"MODIS": ["var1"]}
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )
    task_fail = ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        profile=AereoProfile(
            name="fail", resolution=100.0, collections={"MODIS": ["var1"]}
        ),
        uri="test",
        grid_cells=[],
        grid_config=grid_config,
    )

    with pytest.raises(RuntimeError, match="intentional failure"):
        client.execute_tasks([task_ok, task_fail], failure_mode=FailureMode.STRICT)
