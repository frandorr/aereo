from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from aereo.execution.core import (
    LocalProcessBackend,
    TaskRunner,
    ThreadBackend,
)
from aereo.interfaces.core import AereoProfile, ExtractionTask, GridConfig
from aereo.registry.core import AereoRegistry
from aereo.schemas.core import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    profile: AereoProfile | None = None,
    task_context: dict[str, Any] | None = None,
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
        grid_cells=[],
        grid_config=grid_config,
        task_context=task_context or {},
    )


def _make_mock_registry() -> MagicMock:
    """Return a MagicMock configured like an AereoRegistry."""
    mock = MagicMock(spec=AereoRegistry)
    mock.has_extractor.return_value = True
    mock.find_extractors_for.return_value = []
    return mock


# ---------------------------------------------------------------------------
# TaskRunner
# ---------------------------------------------------------------------------


def test_task_runner_uses_extractor_hint_from_task_context():
    """Resolution priority 1: task_context['extractor_hint']."""
    mock_registry = _make_mock_registry()
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = gpd.GeoDataFrame()
    mock_registry.get_extractor.return_value = mock_extractor

    runner = TaskRunner(registry=mock_registry)
    task = _make_task(task_context={"extractor_hint": "my_extractor"})

    runner.run(task)

    mock_registry.get_extractor.assert_called_once_with("my_extractor")


def test_task_runner_falls_back_to_profile_hint():
    """Resolution priority 2: profile.plugin_hints['extract']."""
    mock_registry = _make_mock_registry()
    mock_registry.has_extractor.side_effect = lambda name: name == "profile_hinted"
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = gpd.GeoDataFrame()
    mock_registry.get_extractor.return_value = mock_extractor

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        plugin_hints={"extract": "profile_hinted"},
    )
    task = _make_task(profile=profile)

    runner.run(task)

    mock_registry.get_extractor.assert_called_once_with("profile_hinted")


def test_task_runner_auto_discovers_from_collections():
    """Resolution priority 3: auto-discover from profile.collections."""
    mock_registry = _make_mock_registry()
    mock_registry.has_extractor.return_value = False
    mock_registry.find_extractors_for.return_value = ["auto_extractor"]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = gpd.GeoDataFrame()
    mock_registry.get_extractor.return_value = mock_extractor

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        collections={"C1": ["var1"]},
    )
    task = _make_task(profile=profile)

    runner.run(task)

    mock_registry.find_extractors_for.assert_called_once_with("C1")
    mock_registry.get_extractor.assert_called_once_with("auto_extractor")


def test_task_runner_raises_when_no_extractor_found():
    """ValueError when no extractor can be resolved."""
    mock_registry = _make_mock_registry()
    mock_registry.has_extractor.return_value = False
    mock_registry.find_extractors_for.return_value = []

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="orphan",
        resolution=100.0,
        collections={"C1": ["var1"]},
    )
    task = _make_task(profile=profile)

    with pytest.raises(ValueError, match="No extractor plugin found"):
        runner.run(task)


def test_task_runner_merges_profile_extract_params():
    """Profile extract_params are passed to extractor.extract()."""
    mock_registry = _make_mock_registry()
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = gpd.GeoDataFrame()
    mock_registry.get_extractor.return_value = mock_extractor

    runner = TaskRunner(registry=mock_registry)
    profile = AereoProfile(
        name="test",
        resolution=100.0,
        plugin_hints={"extract": "dummy"},
        extract_params={"calibration": "reflectance", "padding": 2},
    )
    task = _make_task(profile=profile, task_context={"extractor_hint": "dummy"})

    runner.run(task)

    call_args = mock_extractor.extract.call_args
    passed_params = (
        call_args.args[1]
        if len(call_args.args) > 1
        else call_args.kwargs.get("extract_params")
    )
    assert passed_params == {"calibration": "reflectance", "padding": 2}


def test_task_runner_returns_extractor_result():
    """The GeoDataFrame returned by extract() is passed through unchanged."""
    mock_registry = _make_mock_registry()
    expected = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
    )
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = expected
    mock_registry.get_extractor.return_value = mock_extractor

    runner = TaskRunner(registry=mock_registry)
    task = _make_task(task_context={"extractor_hint": "dummy"})

    result = runner.run(task)

    assert result is expected


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


def test_local_backend_parallel_with_callable_downloader():
    """ProcessPoolExecutor works when tasks contain live callable downloaders."""
    from aereo.interfaces.core import AereoProfile

    def my_dl(url: str, path: Path) -> None:
        pass

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
                downloader=my_dl,  # pyright: ignore[reportArgumentType]
            ),
            task_context={"test_idx": 0},
        ),
        _make_task(
            profile=AereoProfile(
                name="p2",
                resolution=100.0,
                downloader=lambda url, path: None,  # pyright: ignore[reportArgumentType]
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
