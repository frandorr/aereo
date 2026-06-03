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
    AereoProfile,
    ExtractionTask,
    GridConfig,
    Reader,
    Writer,
)
from aereo.registry.core import AereoRegistry
from aereo.schemas.core import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    profile: AereoProfile | None = None,
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
        profile=profile or AereoProfile(name="test", resolution=100.0),
        uri="test-uri",
        grid_cells=grid_cells or [],
        grid_config=grid_config,
        task_context=task_context or {},
    )


def _make_mock_registry() -> MagicMock:
    """Return a MagicMock configured like an AereoRegistry."""
    mock = MagicMock(spec=AereoRegistry)
    mock.has.return_value = True
    mock.find_for.return_value = []
    return mock


class _DummyReader(Reader):
    """A dummy reader that returns a simple xarray Dataset."""

    supported_collections = ("*",)

    def read(self, task, params):
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyWriter(Writer):
    """A dummy writer that returns an empty GeoDataFrame."""

    supported_collections = ("*",)

    def write(self, ds, task, cell, params):
        return gpd.GeoDataFrame()


# ---------------------------------------------------------------------------
# TaskRunner (Phase 1 pipeline)
# ---------------------------------------------------------------------------


def test_task_runner_resolves_stage_from_profile():
    """Verify that TaskRunner resolves plugins defined in the profile."""
    mock_registry = _make_mock_registry()
    mock_reader = MagicMock(spec=_DummyReader)
    mock_reader.read.return_value = xr.Dataset()

    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()

    mock_writer = MagicMock(spec=_DummyWriter)
    mock_writer.write.return_value = gpd.GeoDataFrame(
        {"id": ["a1"]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )

    allowed = {"my_reader", "my_reprojector", "my_writer"}

    def _mock_has(type_label, name):
        return name in allowed

    def _mock_get(type_label, name, **kwargs):
        if type_label == "reader" and name == "my_reader":
            return mock_reader
        if type_label == "reprojector" and name == "my_reprojector":
            return mock_reprojector
        if type_label == "writer" and name == "my_writer":
            return mock_writer
        raise ValueError(f"Unexpected get: {type_label}, {name}")

    mock_registry.has.side_effect = _mock_has
    mock_registry.get.side_effect = _mock_get

    profile = AereoProfile(
        name="test",
        resolution=100.0,
        read={"my_reader": {}},
        reproject={"my_reprojector": {}},
        write={"my_writer": {}},
    )
    runner = TaskRunner(registry=mock_registry)
    task = _make_task(profile=profile)

    runner.run(task)

    mock_registry.has.assert_any_call("reader", "my_reader")
    mock_registry.has.assert_any_call("reprojector", "my_reprojector")
    mock_registry.has.assert_any_call("writer", "my_writer")


def test_task_runner_falls_back_to_auto_discovery():
    """Verify that TaskRunner falls back to auto-discovery when no profile configuration is set."""
    mock_registry = _make_mock_registry()
    mock_reader = MagicMock(spec=_DummyReader)
    mock_reader.read.return_value = xr.Dataset()

    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()

    mock_writer = MagicMock(spec=_DummyWriter)
    mock_writer.write.return_value = gpd.GeoDataFrame()

    mock_registry.has.return_value = False

    def _mock_find_for(type_label, collection):
        if type_label == "reader":
            return ["auto_reader"]
        if type_label == "reprojector":
            return ["auto_reprojector"]
        if type_label == "writer":
            return ["auto_writer"]
        return []

    def _mock_get(type_label, name, **kwargs):
        if type_label == "reader" and name == "auto_reader":
            return mock_reader
        if type_label == "reprojector" and name == "auto_reprojector":
            return mock_reprojector
        if type_label == "writer" and name == "auto_writer":
            return mock_writer
        raise ValueError(f"Unexpected get: {type_label}, {name}")

    mock_registry.find_for.side_effect = _mock_find_for
    mock_registry.get.side_effect = _mock_get

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        collections={"C1": ["var1"]},
    )
    task = _make_task(profile=profile)

    runner.run(task)

    mock_registry.find_for.assert_any_call("reader", "C1")


def test_task_runner_raises_when_no_reader_found():
    """ValueError when no reader plugin can be resolved."""
    mock_registry = _make_mock_registry()
    mock_registry.has.return_value = False
    mock_registry.find_for.return_value = []

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="orphan",
        resolution=100.0,
        collections={"C1": ["var1"]},
    )
    task = _make_task(profile=profile)

    with pytest.raises(ValueError, match="No reader plugin found"):
        runner.run(task)


def test_task_runner_passes_stage_params_to_method_calls():
    """Profile stage parameters are passed to plugin method calls, not __init__."""
    mock_registry = _make_mock_registry()
    mock_reader = MagicMock(spec=_DummyReader)
    mock_reader.read.return_value = xr.Dataset()

    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()

    mock_writer = MagicMock(spec=_DummyWriter)
    mock_writer.write.return_value = gpd.GeoDataFrame(
        {"id": ["a1"]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )

    allowed = {"dummy"}

    def _mock_has(type_label, name):
        return name in allowed

    def _mock_get(type_label, name, **kwargs):
        if type_label == "reader" and name == "dummy":
            return mock_reader
        if type_label == "reprojector" and name == "dummy":
            return mock_reprojector
        if type_label == "writer" and name == "dummy":
            return mock_writer
        raise ValueError(f"Unexpected get: {type_label}, {name}")

    mock_registry.has.side_effect = _mock_has
    mock_registry.get.side_effect = _mock_get

    # Create a mock grid cell so the per-cell loop executes
    mock_cell = MagicMock()
    mock_cell.id.return_value = "cell-1"
    mock_cell.geom = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    mock_cell.utm_crs = "EPSG:4326"
    mock_cell.utm_footprint = mock_cell.geom
    mock_cell.area_def.return_value = MagicMock()

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        read={"dummy": {"odc_params": {"chunks": {"x": 2048}}}},
        reproject={"dummy": {"reproject_params": {"resampling": "bilinear"}}},
        write={"dummy": {"rio_params": {"compress": "deflate"}}},
    )
    task = _make_task(profile=profile, grid_cells=[mock_cell])

    runner.run(task)

    # Stage params go to method calls, NOT __init__ (registry.get)
    mock_registry.get.assert_any_call("reader", "dummy")
    mock_registry.get.assert_any_call("reprojector", "dummy")
    mock_registry.get.assert_any_call("writer", "dummy")

    mock_reader.read.assert_called_once()
    assert mock_reader.read.call_args[0][1] == {"odc_params": {"chunks": {"x": 2048}}}

    mock_reprojector.reproject.assert_called_once()
    assert mock_reprojector.reproject.call_args[0][2] == {
        "reproject_params": {"resampling": "bilinear"}
    }

    mock_writer.write.assert_called_once()
    assert mock_writer.write.call_args[0][3] == {"rio_params": {"compress": "deflate"}}


def test_task_runner_returns_writer_result():
    """The GeoDataFrame returned by writer.write() is accumulated."""
    mock_registry = _make_mock_registry()
    mock_reader = MagicMock(spec=_DummyReader)
    mock_reader.read.return_value = xr.Dataset()

    mock_reprojector = MagicMock()
    mock_reprojector.reproject.return_value = xr.Dataset()

    expected = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )
    mock_writer = MagicMock(spec=_DummyWriter)
    mock_writer.write.return_value = expected

    allowed = {"dummy"}

    def _mock_has(type_label, name):
        return name in allowed

    def _mock_get(type_label, name, **kwargs):
        if type_label == "reader" and name == "dummy":
            return mock_reader
        if type_label == "reprojector" and name == "dummy":
            return mock_reprojector
        if type_label == "writer" and name == "dummy":
            return mock_writer
        raise ValueError(f"Unexpected get: {type_label}, {name}")

    mock_registry.has.side_effect = _mock_has
    mock_registry.get.side_effect = _mock_get

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        read={"dummy": {}},
        reproject={"dummy": {}},
        write={"dummy": {}},
    )
    task = _make_task(profile=profile)

    result = runner.run(task)

    # Result should be a GeoDataFrame
    assert isinstance(result, gpd.GeoDataFrame)


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


def test_local_backend_parallel_with_multiple_profiles():
    """ProcessPoolExecutor works with different profile names."""
    from aereo.interfaces.core import AereoProfile

    backend = LocalProcessBackend(max_workers=2)
    runner = _PicklableRunner(
        [
            gpd.GeoDataFrame({"i": [0]}),
            gpd.GeoDataFrame({"i": [1]}),
        ]
    )

    tasks = [
        _make_task(
            profile=AereoProfile(
                name="p1",
                resolution=100.0,
            ),
            task_context={"test_idx": 0},
        ),
        _make_task(
            profile=AereoProfile(
                name="p2",
                resolution=100.0,
            ),
            task_context={"test_idx": 1},
        ),
    ]
    results = list(backend.run_tasks(tasks, cast(TaskRunner, runner)))

    assert len(results) == 2
    assert results[0]["i"].iloc[0] == 0
    assert results[1]["i"].iloc[0] == 1


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
