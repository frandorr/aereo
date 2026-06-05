from typing import Any, cast
from unittest.mock import MagicMock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import Polygon

from aereo.backends import (
    LocalProcessBackend,
    TaskRunner,
    ThreadBackend,
)
from aereo.interfaces.core import (
    AereoDataset,
    AereoPlugin,
    ExtractionTask,
    GridConfig,
    Reader,
    Reprojector,
    Writer,
    Processor,
)
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    pipeline: list[AereoPlugin] | None = None,
    task_context: dict[str, Any] | None = None,
    grid_cells: list[Any] | None = None,
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    valid_df["collection"] = "C1"

    grid_config = GridConfig(target_grid_dist=50_000)
    return ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        pipeline=pipeline or [],
        uri="test-uri",
        grid_cells=grid_cells or [],
        grid_config=grid_config,
        task_context=task_context or {},
    )


class _DummyReader(Reader):
    def __call__(self, task: ExtractionTask) -> AereoDataset:
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyReprojector(Reprojector):
    resolution: float = 100.0

    def __call__(self, ds: AereoDataset, geobox: Any) -> AereoDataset:
        return ds


class _DummyWriter(Writer):
    def __call__(
        self, ds: AereoDataset, task: ExtractionTask, cell: Any
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(
            GeoDataFrame[ArtifactSchema],
            gpd.GeoDataFrame(
                {"id": ["a1"]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
            ),
        )


class _DummyProcessor(Processor):
    value: int = 2

    def __call__(self, ds: AereoDataset) -> AereoDataset:
        ds = ds.copy()
        ds["B04"] = ds["B04"] * self.value
        return ds


# ---------------------------------------------------------------------------
# TaskRunner
# ---------------------------------------------------------------------------


def test_task_runner_executes_pipeline():
    """Verify that TaskRunner runs the pipeline successfully."""
    # Create mock grid cell
    mock_cell = MagicMock()
    mock_cell.id.return_value = "cell-1"
    mock_cell.geom = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    mock_cell.utm_crs = "EPSG:4326"
    mock_cell.utm_footprint = mock_cell.geom
    mock_cell.area_def.return_value = MagicMock()

    pipeline = [
        _DummyReader(),
        _DummyProcessor(value=3),
        _DummyReprojector(resolution=50.0),
        _DummyProcessor(value=2),
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, grid_cells=[mock_cell])
    runner = TaskRunner()
    result = runner.run(task)

    assert isinstance(result, gpd.GeoDataFrame)
    assert not result.empty


def test_task_runner_raises_on_missing_stages():
    """ValueError when any required stage is missing."""
    runner = TaskRunner()

    # Missing Reader
    task = _make_task(pipeline=[_DummyReprojector(), _DummyWriter()])
    with pytest.raises(ValueError, match="must contain a Reader stage"):
        runner.run(task)

    # Missing Reprojector
    task = _make_task(pipeline=[_DummyReader(), _DummyWriter()])
    with pytest.raises(ValueError, match="must contain a Reprojector stage"):
        runner.run(task)

    # Missing Writer
    task = _make_task(pipeline=[_DummyReader(), _DummyReprojector()])
    with pytest.raises(ValueError, match="must contain a Writer stage"):
        runner.run(task)


def test_task_runner_callbacks():
    """Verify that TaskRunner invokes callbacks."""
    mock_cell = MagicMock()
    mock_cell.id.return_value = "cell-1"
    mock_cell.geom = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    mock_cell.utm_crs = "EPSG:4326"
    mock_cell.utm_footprint = mock_cell.geom
    mock_cell.area_def.return_value = MagicMock()

    pipeline = [
        _DummyReader(),
        _DummyReprojector(resolution=50.0),
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, grid_cells=[mock_cell])
    mock_callback = MagicMock()
    runner = TaskRunner(callbacks=[mock_callback])
    runner.run(task)

    mock_callback.on_task_start.assert_called_once_with(task)
    mock_callback.on_download_complete.assert_called_once_with(task)
    mock_callback.on_read_complete.assert_called_once()
    mock_callback.on_reproject_complete.assert_called_once()
    mock_callback.on_cell_complete.assert_called_once()
    mock_callback.on_task_complete.assert_called_once()


# ---------------------------------------------------------------------------
# Picklable test helpers for process-based tests
# ---------------------------------------------------------------------------


class _PicklableRunner:
    """A minimal picklable runner for testing ProcessPoolExecutor paths."""

    def __init__(self, results: list[gpd.GeoDataFrame]) -> None:
        self.results = results

    def run(self, task: ExtractionTask) -> gpd.GeoDataFrame:
        idx = task.task_context.get("test_idx", 0)
        return self.results[idx]


# ---------------------------------------------------------------------------
# LocalProcessBackend
# ---------------------------------------------------------------------------


def test_local_backend_sequential_when_max_workers_none():
    """When max_workers is None, tasks run sequentially."""
    backend = LocalProcessBackend(max_workers=None)
    mock_runner = MagicMock(spec=TaskRunner)
    expected = [gpd.GeoDataFrame({"i": [i]}) for i in range(3)]
    mock_runner.run.side_effect = expected

    tasks = [_make_task() for _ in range(3)]
    results = list(backend.run_tasks(tasks, mock_runner))

    assert len(results) == 3
    assert mock_runner.run.call_count == 3
    for i, result in enumerate(results):
        assert result["i"].iloc[0] == i


def test_local_backend_sequential_when_single_task():
    """Even with max_workers > 1, a single task runs sequentially."""
    backend = LocalProcessBackend(max_workers=4)
    mock_runner = MagicMock(spec=TaskRunner)
    expected = gpd.GeoDataFrame({"id": [42]})
    mock_runner.run.return_value = expected

    tasks = [_make_task()]
    results = list(backend.run_tasks(tasks, mock_runner))

    assert len(results) == 1
    mock_runner.run.assert_called_once()


def test_local_backend_parallel_with_multiple_tasks():
    """ProcessPoolExecutor path runs tasks in parallel and preserves order."""
    backend = LocalProcessBackend(max_workers=2)
    runner = _PicklableRunner(
        [
            gpd.GeoDataFrame({"i": [0]}),
            gpd.GeoDataFrame({"i": [1]}),
            gpd.GeoDataFrame({"i": [2]}),
        ]
    )

    tasks = [
        _make_task(task_context={"test_idx": 0}),
        _make_task(task_context={"test_idx": 1}),
        _make_task(task_context={"test_idx": 2}),
    ]
    results = list(backend.run_tasks(tasks, cast(TaskRunner, runner)))

    assert len(results) == 3
    # Results must be in task order, not completion order
    for i, result in enumerate(results):
        assert result["i"].iloc[0] == i


def test_local_backend_empty_tasks():
    """Empty task list returns empty iterable."""
    backend = LocalProcessBackend()
    mock_runner = MagicMock(spec=TaskRunner)

    results = list(backend.run_tasks([], mock_runner))

    assert results == []
    mock_runner.run.assert_not_called()


def test_local_backend_requires_runner():
    """LocalProcessBackend raises ValueError when runner is None."""
    backend = LocalProcessBackend()
    with pytest.raises(ValueError, match="requires a runner"):
        list(backend.run_tasks([_make_task()], runner=None))


def test_local_backend_exception_propagates():
    """Exceptions from runner.run() propagate in strict mode."""
    backend = LocalProcessBackend(max_workers=None)
    mock_runner = MagicMock(spec=TaskRunner)
    mock_runner.run.side_effect = RuntimeError("task failed")

    tasks = [_make_task()]
    with pytest.raises(RuntimeError, match="task failed"):
        list(backend.run_tasks(tasks, mock_runner))


# ---------------------------------------------------------------------------
# ThreadBackend
# ---------------------------------------------------------------------------


def test_thread_backend_sequential_when_max_workers_none():
    """When max_workers is None, tasks run sequentially."""
    backend = ThreadBackend(max_workers=None)
    mock_runner = MagicMock(spec=TaskRunner)
    expected = [gpd.GeoDataFrame({"i": [i]}) for i in range(3)]
    mock_runner.run.side_effect = expected

    tasks = [_make_task() for _ in range(3)]
    results = list(backend.run_tasks(tasks, mock_runner))

    assert len(results) == 3
    assert mock_runner.run.call_count == 3
    for i, result in enumerate(results):
        assert result["i"].iloc[0] == i


def test_thread_backend_sequential_when_single_task():
    """Even with max_workers > 1, a single task runs sequentially."""
    backend = ThreadBackend(max_workers=4)
    mock_runner = MagicMock(spec=TaskRunner)
    expected = gpd.GeoDataFrame({"id": [42]})
    mock_runner.run.return_value = expected

    tasks = [_make_task()]
    results = list(backend.run_tasks(tasks, mock_runner))

    assert len(results) == 1
    mock_runner.run.assert_called_once()


def test_thread_backend_parallel_with_multiple_tasks():
    """ThreadPoolExecutor path runs tasks in parallel and preserves order."""
    backend = ThreadBackend(max_workers=2)
    runner = _PicklableRunner(
        [
            gpd.GeoDataFrame({"i": [0]}),
            gpd.GeoDataFrame({"i": [1]}),
            gpd.GeoDataFrame({"i": [2]}),
        ]
    )

    tasks = [
        _make_task(task_context={"test_idx": 0}),
        _make_task(task_context={"test_idx": 1}),
        _make_task(task_context={"test_idx": 2}),
    ]
    results = list(backend.run_tasks(tasks, cast(TaskRunner, runner)))

    assert len(results) == 3
    # Results must be in task order, not completion order
    for i, result in enumerate(results):
        assert result["i"].iloc[0] == i


def test_thread_backend_empty_tasks():
    """Empty task list returns empty iterable."""
    backend = ThreadBackend()
    mock_runner = MagicMock(spec=TaskRunner)

    results = list(backend.run_tasks([], mock_runner))

    assert results == []
    mock_runner.run.assert_not_called()


def test_thread_backend_requires_runner():
    """ThreadBackend raises ValueError when runner is None."""
    backend = ThreadBackend()
    with pytest.raises(ValueError, match="requires a runner"):
        list(backend.run_tasks([_make_task()], runner=None))


def test_thread_backend_exception_propagates():
    """Exceptions from runner.run() propagate."""
    backend = ThreadBackend(max_workers=None)
    mock_runner = MagicMock(spec=TaskRunner)
    mock_runner.run.side_effect = RuntimeError("task failed")

    tasks = [_make_task()]
    with pytest.raises(RuntimeError, match="task failed"):
        list(backend.run_tasks(tasks, mock_runner))
