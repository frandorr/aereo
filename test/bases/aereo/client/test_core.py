from typing import cast
from unittest.mock import MagicMock

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from aereo.client.core import AereoClient, FailureMode, normalize_geometry
from aereo.interfaces.core import (
    ExtractionTask,
    GridConfig,
    PatchConfig,
    SearchProvider,
    ExecutionBackend,
)
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


def test_client_search_success():
    mock_searcher = MagicMock(spec=SearchProvider)
    valid_df = gpd.GeoDataFrame(
        {"id": ["asset_1"], "collection": ["MODIS"]},
        geometry=[Point(0, 0)],
    )
    mock_searcher.return_value = valid_df

    client = AereoClient()
    search_results = client.search(mock_searcher)

    assert len(search_results) == 1
    mock_searcher.assert_called_once()
    assert isinstance(search_results, pd.DataFrame)


# ---------------------------------------------------------------------------
# prepare_tasks
# ---------------------------------------------------------------------------


def _make_valid_search_df():
    valid_df = gpd.GeoDataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    valid_df["collection"] = "MODIS"
    valid_df["start_time"] = pd.Timestamp("2023-01-01")
    return valid_df


def test_prepare_tasks_requires_grid_config():
    valid_search_df = _make_valid_search_df()
    client = AereoClient()

    with pytest.raises(ValueError, match="grid_config must be provided"):
        client.prepare_tasks(
            search_results=cast(GeoDataFrame, valid_search_df),
            pipeline=[],
            uri="s3://bucket/out/",
        )


def test_prepare_tasks_returns_tasks(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = _make_valid_search_df()

    client = AereoClient()
    grid_config = GridConfig(target_grid_dist=50_000)
    patch_config = PatchConfig(resolution=10.0)
    tasks = client.prepare_tasks(
        search_results=cast(GeoDataFrame, valid_df),
        pipeline=[],
        grid_config=grid_config,
        patch_config=patch_config,
        uri="s3://out",
        cells_per_task=1,
    )
    assert isinstance(tasks, list)
    assert len(tasks) > 0
    assert tasks[0].uri == "s3://out"


# ---------------------------------------------------------------------------
# execute_tasks
# ---------------------------------------------------------------------------


def test_execute_tasks_empty():
    client = AereoClient()
    result = client.execute_tasks([])
    assert len(result) == 0


def test_execute_tasks_failure_mode_strict(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    mock_backend = MagicMock(spec=ExecutionBackend)
    mock_backend.run_tasks.side_effect = RuntimeError("run failed")

    client = AereoClient()
    task = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        pipeline=[],
        uri="test",
        patches=[],
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
    )

    with pytest.raises(RuntimeError, match="run failed"):
        client.execute_tasks(
            [task], backend=mock_backend, failure_mode=FailureMode.STRICT
        )


def test_execute_tasks_failure_mode_best_effort(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    mock_backend = MagicMock(spec=ExecutionBackend)
    mock_backend.run_tasks.side_effect = RuntimeError("run failed")

    client = AereoClient()
    task = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        pipeline=[],
        uri="test",
        patches=[],
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
    )

    result = client.execute_tasks(
        [task], backend=mock_backend, failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(result) == 0


def test_execute_tasks_best_effort_partial_results(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    mock_backend = MagicMock(spec=ExecutionBackend)

    df_ok = gpd.GeoDataFrame(
        {"path": ["/path/to/img.tif"], "variable": ["B04"], "cell_id": ["cell_1"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )

    def _run_tasks(tasks, runner=None):
        if tasks[0].uri == "fail":
            raise RuntimeError("intentional failure")
        return [df_ok]

    mock_backend.run_tasks.side_effect = _run_tasks

    client = AereoClient()
    task_ok = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        pipeline=[],
        uri="ok",
        patches=[],
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
    )
    task_fail = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        pipeline=[],
        uri="fail",
        patches=[],
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
    )

    result = client.execute_tasks(
        [task_ok, task_fail],
        backend=mock_backend,
        failure_mode=FailureMode.BEST_EFFORT,
    )
    assert len(result) == 1
    assert result.iloc[0]["cell_id"] == "cell_1"
