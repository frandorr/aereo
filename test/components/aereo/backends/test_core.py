import attrs
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import Polygon

from aereo.execution import run_task
from aereo.executors import LocalExecutor
from aereo.interfaces.core import (
    ExtractionTask,
)
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from typing import Any, cast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyReader:
    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyWriter:
    def __call__(
        self, ds: xr.Dataset, task: ExtractionTask, patch: Any
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(
            GeoDataFrame[ArtifactSchema],
            gpd.GeoDataFrame(
                {"id": [patch.id]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
            ),
        )


class _FailingReader:
    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        raise RuntimeError("read failed")


class _MockPatch:
    """Picklable stand-in for an ExtractionPatch."""

    def __init__(self, patch_id: str) -> None:
        self.id = patch_id
        self.geobox = None


def _mock_patch(patch_id: str) -> _MockPatch:
    """Return a minimal mock patch with the given id."""
    return _MockPatch(patch_id)


def _make_task(
    reader: Any = _DummyReader(),
    writer: Any | None = None,
    task_context: dict[str, Any] | None = None,
    patches: list[Any] | None = None,
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    valid_df["collection"] = "C1"

    job = ExtractionJob(
        grid_dist=50_000,
        output_uri="test-uri",
        read=reader,
        write=writer,
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        job=job,
        patches=patches or [],
        task_context=task_context or {},
    )


# ---------------------------------------------------------------------------
# run_task
# ---------------------------------------------------------------------------


def test_run_task_executes_read_write():
    """Verify that run_task runs read -> write successfully."""
    task = _make_task(
        writer=_DummyWriter(),
        patches=[_mock_patch("cell-1")],
    )
    result = run_task(task)

    assert isinstance(result, gpd.GeoDataFrame)
    assert not result.empty


def test_run_task_calls_writer_once_per_patch():
    """Writer is called once per patch."""
    import unittest.mock

    writer = unittest.mock.Mock(
        side_effect=_DummyWriter(),
        spec=_DummyWriter(),
    )
    task = _make_task(
        writer=writer,
        patches=[_mock_patch("cell-1"), _mock_patch("cell-2")],
    )
    run_task(task)

    assert writer.call_count == 2


def test_run_task_raises_when_reader_is_missing():
    """ValueError is raised when the job has no reader."""
    task = _make_task()
    job = task.job.model_copy(update={"read": None})
    task = attrs.evolve(task, job=job)
    with pytest.raises(ValueError, match="Pipeline must contain a Reader stage"):
        run_task(task)


# ---------------------------------------------------------------------------
# LocalExecutor
# ---------------------------------------------------------------------------


def test_local_executor_is_callable():
    assert callable(LocalExecutor())


def test_local_executor_runs_tasks():
    executor = LocalExecutor(workers=2)
    tasks = [
        _make_task(
            writer=_DummyWriter(),
            patches=[_mock_patch("cell-1")],
        ),
        _make_task(
            writer=_DummyWriter(),
            patches=[_mock_patch("cell-2")],
        ),
    ]
    artifacts = executor(tasks)
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) == 2


def test_local_executor_empty_tasks():
    executor = LocalExecutor()
    result = executor([])
    assert isinstance(result, gpd.GeoDataFrame)
    assert result.empty


def test_local_executor_best_effort_skips_failed_tasks(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    failing_task = _make_task(
        reader=_FailingReader(),
        writer=_DummyWriter(),
        patches=[_mock_patch("a")],
    )
    ok_task = _make_task(
        writer=_DummyWriter(),
        patches=[_mock_patch("b")],
    )

    executor = LocalExecutor(failure_mode="best_effort")
    artifacts = executor([failing_task, ok_task])

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) == 1


def test_local_executor_strict_propagates_failure(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    failing_task = _make_task(
        reader=_FailingReader(),
        writer=_DummyWriter(),
        patches=[_mock_patch("a")],
    )

    executor = LocalExecutor(failure_mode="strict")
    with pytest.raises(RuntimeError, match="read failed"):
        executor([failing_task])


def test_local_executor_sequential_when_workers_none():
    executor = LocalExecutor(workers=None)
    tasks = [
        _make_task(
            writer=_DummyWriter(),
            patches=[_mock_patch("a")],
        ),
        _make_task(
            writer=_DummyWriter(),
            patches=[_mock_patch("b")],
        ),
    ]
    artifacts = executor(tasks)
    assert len(artifacts) == 2


def test_local_executor_thread_pool():
    executor = LocalExecutor(workers=2, use_threads=True)
    tasks = [
        _make_task(
            writer=_DummyWriter(),
            patches=[_mock_patch("a")],
        ),
        _make_task(
            writer=_DummyWriter(),
            patches=[_mock_patch("b")],
        ),
    ]
    artifacts = executor(tasks)
    assert len(artifacts) == 2
