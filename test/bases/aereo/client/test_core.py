from typing import cast
from unittest.mock import MagicMock

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.builtins.read import ReadODCSTAC
from aereo.builtins.task_builder import GroupedTaskBuilder
from aereo.client.core import AereoClient, FailureMode
from aereo.interfaces.core import (
    ExecutionBackend,
    ExtractionTask,
    ExtractConfig,
    GridConfig,
    PatchConfig,
    SearchProvider,
)
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


def _make_valid_search_df():
    valid_df = gpd.GeoDataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    valid_df["collection"] = "MODIS"
    valid_df["start_time"] = pd.Timestamp("2023-01-01")
    return valid_df


def test_client_search_success():
    mock_searcher = MagicMock(spec=SearchProvider)
    valid_df = gpd.GeoDataFrame(
        {"id": ["asset_1"], "collection": ["MODIS"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 0]])],
    )
    mock_searcher.return_value = valid_df

    client = AereoClient()
    search_results = client.search(mock_searcher)

    assert len(search_results) == 1
    mock_searcher.assert_called_once()
    assert isinstance(search_results, pd.DataFrame)


# ---------------------------------------------------------------------------
# build_tasks
# ---------------------------------------------------------------------------


def test_build_tasks_returns_tasks(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = _make_valid_search_df()

    job = ExtractionJob(
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="s3://out",
        search=None,
        task_builder=GroupedTaskBuilder(cells_per_task=1),
        extract=ExtractConfig(read=ReadODCSTAC()),
    )

    client = AereoClient()
    tasks = client.build_tasks(
        search_results=cast(GeoDataFrame, valid_df),
        job=job,
    )
    assert isinstance(tasks, list)
    assert len(tasks) > 0
    assert tasks[0].output_uri == "s3://out"


def test_build_tasks_uses_job_target_aoi(monkeypatch, tmp_path):
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = _make_valid_search_df()

    aoi_path = tmp_path / "aoi.geojson"
    aoi_path.write_text(
        '{"type": "Polygon", "coordinates": [[[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5], [0, 0]]]}'
    )

    job = ExtractionJob(
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="s3://out",
        search=None,
        task_builder=GroupedTaskBuilder(cells_per_task=1),
        extract=ExtractConfig(read=ReadODCSTAC()),
        target_aoi=str(aoi_path),
    )

    client = AereoClient()
    tasks = client.build_tasks(
        search_results=cast(GeoDataFrame, valid_df),
        job=job,
    )
    assert isinstance(tasks, list)
    assert len(tasks) > 0
    assert tasks[0].aoi is not None


def test_build_tasks_preserves_job_derivative(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = _make_valid_search_df()

    job = ExtractionJob(
        name="s2_ndvi",
        derivative="ndvi",
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="s3://out",
        search=None,
        task_builder=GroupedTaskBuilder(cells_per_task=1),
        extract=ExtractConfig(read=ReadODCSTAC()),
    )

    client = AereoClient()
    tasks = client.build_tasks(
        search_results=cast(GeoDataFrame, valid_df),
        job=job,
    )
    assert isinstance(tasks, list)
    assert len(tasks) > 0
    assert tasks[0].job.derivative == "ndvi"
    assert tasks[0].job.name == "s2_ndvi"


def test_build_tasks_falls_back_to_search_intersects(monkeypatch):
    """When no target_aoi is set, job.search.intersects is used via effective_target_aoi."""
    monkeypatch.setattr("aereo.schemas.core.AssetSchema.validate", lambda x: x)
    valid_df = _make_valid_search_df()

    from aereo.interfaces.core import SearchProvider

    search_aoi = Polygon([[0, 0], [0.3, 0], [0.3, 0.3], [0, 0.3], [0, 0]])
    mock_searcher = MagicMock(spec=SearchProvider)
    mock_searcher.intersects = search_aoi

    job = ExtractionJob(
        name="s2_ndvi",
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="s3://out",
        search=mock_searcher,
        task_builder=GroupedTaskBuilder(cells_per_task=1),
        extract=ExtractConfig(read=ReadODCSTAC()),
    )

    client = AereoClient()
    tasks = client.build_tasks(
        search_results=cast(GeoDataFrame, valid_df),
        job=job,
    )
    assert isinstance(tasks, list)
    assert len(tasks) > 0
    assert tasks[0].job.effective_target_aoi is search_aoi


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
    job = ExtractionJob(
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="test",
        search=None,
        extract=ExtractConfig(read=ReadODCSTAC()),
    )
    task = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        job=job,
        patches=[],
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
    job = ExtractionJob(
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="test",
        search=None,
        extract=ExtractConfig(read=ReadODCSTAC()),
    )
    task = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        job=job,
        patches=[],
    )

    result = client.execute_tasks(
        [task], backend=mock_backend, failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(result) == 0


def test_execute_tasks_best_effort_partial_results(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)
    mock_backend = MagicMock(spec=ExecutionBackend)

    df_ok = gpd.GeoDataFrame(
        {"id": ["a"]},
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
    )
    mock_backend.run_tasks.return_value = iter([df_ok])

    client = AereoClient()
    job = ExtractionJob(
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="test",
        search=None,
        extract=ExtractConfig(read=ReadODCSTAC()),
    )
    task = ExtractionTask(
        assets=cast(GeoDataFrame, _make_valid_search_df()),
        job=job,
        patches=[],
    )

    result = client.execute_tasks(
        [task], backend=mock_backend, failure_mode=FailureMode.BEST_EFFORT
    )
    assert len(result) == 1
