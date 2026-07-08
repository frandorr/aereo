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
from pandera.typing.geopandas import GeoDataFrame
from typing import Any, cast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyReader:
    def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _CapturingReader:
    """Reader that records the kwargs it receives."""

    captured: dict[str, Any]

    def __init__(self) -> None:
        self.captured = {}

    def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
        self.captured = {"task": task, **kwargs}
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyWriter:
    def __call__(self, ds: xr.Dataset, path: str, **kwargs) -> str:
        import rioxarray  # noqa: F401

        da = xr.DataArray(
            np.ones((4, 4), dtype=np.float32),
            dims=["y", "x"],
            coords={"y": range(4), "x": range(4)},
        )
        da.rio.write_crs("EPSG:4326", inplace=True)
        da.rio.to_raster(path)
        return path


class _FailingReader:
    def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
        raise RuntimeError("read failed")


def _make_task(
    reader: Any = _DummyReader(),
    writer: Any = _DummyWriter(),
    task_id: str = "task-0",
    job_name: str = "test-job",
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing."""
    valid_df = gpd.GeoDataFrame(
        {
            "id": ["asset-1"],
            "collection": ["C1"],
            "start_time": [pd.Timestamp("2023-01-01")],
            "end_time": [pd.Timestamp("2023-01-02")],
            "href": ["s3://bucket/file.tif"],
            "geometry": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
        },
        crs="EPSG:4326",
    )

    job = ExtractionJob(
        name=job_name,
        grid_dist=50_000,
        resolution=10.0,
        output_uri="test-uri",
        read=reader,
        write=writer,
    )
    return ExtractionTask(
        id=task_id,
        assets=cast(GeoDataFrame, valid_df),
        job=job,
    )


# ---------------------------------------------------------------------------
# run_task
# ---------------------------------------------------------------------------


def test_run_task_executes_read_write(tmp_path):
    """Verify that run_task runs read -> write successfully."""
    task = _make_task(
        writer=_DummyWriter(),
        job_name="read-write",
    )
    task = attrs.evolve(
        task, job=task.job.model_copy(update={"output_uri": str(tmp_path / "out")})
    )
    result = run_task(task)

    assert isinstance(result, gpd.GeoDataFrame)
    assert not result.empty


def test_run_task_raises_when_reader_is_missing():
    """ValueError is raised when the job has no reader."""
    task = _make_task(writer=_DummyWriter())
    job = task.job.model_copy(update={"read": None})
    task = attrs.evolve(task, job=job)
    with pytest.raises(ValueError, match="Pipeline must contain a Reader stage"):
        run_task(task)


def test_run_task_passes_aoi_to_reader():
    """run_task forwards task.aoi.bounds to the reader when an AOI is set."""
    reader = _CapturingReader()
    task = _make_task(reader=reader, writer=_DummyWriter())
    task = attrs.evolve(
        task,
        aoi=Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]),
    )

    run_task(task)

    assert "task" in reader.captured
    assert reader.captured["task"] is task
    assert task.bbox == (0.0, 0.0, 1.0, 1.0)


def test_run_task_passes_partial_kwargs_to_reader():
    """Reader kwargs bound via functools.partial are forwarded as keyword args."""
    from functools import partial

    reader = _CapturingReader()
    custom_aoi = (-1.0, -1.0, 2.0, 2.0)
    base_task = _make_task(
        reader=partial(reader, aoi=custom_aoi), writer=_DummyWriter()
    )
    task = attrs.evolve(
        base_task,
        aoi=Polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]),
    )

    run_task(task)

    assert reader.captured["task"] is task
    assert reader.captured["aoi"] == custom_aoi


# ---------------------------------------------------------------------------
# LocalExecutor
# ---------------------------------------------------------------------------


def test_local_executor_is_callable():
    assert callable(LocalExecutor())


def test_local_executor_runs_tasks(tmp_path):
    executor = LocalExecutor(workers=2)
    tasks = [
        _make_task(
            writer=_DummyWriter(),
            task_id="task-0",
            job_name="local",
        ),
        _make_task(
            writer=_DummyWriter(),
            task_id="task-1",
            job_name="local",
        ),
    ]
    for i, task in enumerate(tasks):
        tasks[i] = attrs.evolve(
            task,
            job=task.job.model_copy(update={"output_uri": str(tmp_path / f"out{i}")}),
        )
    artifacts = executor(tasks)
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) >= 2


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
        task_id="fail",
    )
    ok_task = _make_task(
        writer=_DummyWriter(),
        task_id="ok",
    )

    executor = LocalExecutor(failure_mode="best_effort")
    artifacts = executor([failing_task, ok_task])

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) >= 1


def test_local_executor_strict_propagates_failure(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    failing_task = _make_task(
        reader=_FailingReader(),
        writer=_DummyWriter(),
        task_id="fail",
    )

    executor = LocalExecutor(failure_mode="strict")
    with pytest.raises(RuntimeError, match="read failed"):
        executor([failing_task])


def test_local_executor_sequential_when_workers_none(tmp_path):
    executor = LocalExecutor(workers=None)
    tasks = [
        _make_task(
            writer=_DummyWriter(),
            task_id="task-0",
            job_name="seq",
        ),
        _make_task(
            writer=_DummyWriter(),
            task_id="task-1",
            job_name="seq",
        ),
    ]
    for i, task in enumerate(tasks):
        tasks[i] = attrs.evolve(
            task,
            job=task.job.model_copy(update={"output_uri": str(tmp_path / f"out{i}")}),
        )
    artifacts = executor(tasks)
    assert len(artifacts) >= 2


def test_local_executor_thread_pool(tmp_path):
    executor = LocalExecutor(workers=2, use_threads=True)
    tasks = [
        _make_task(
            writer=_DummyWriter(),
            task_id="task-0",
            job_name="thread",
        ),
        _make_task(
            writer=_DummyWriter(),
            task_id="task-1",
            job_name="thread",
        ),
    ]
    for i, task in enumerate(tasks):
        tasks[i] = attrs.evolve(
            task,
            job=task.job.model_copy(update={"output_uri": str(tmp_path / f"out{i}")}),
        )
    artifacts = executor(tasks)
    assert len(artifacts) >= 2
