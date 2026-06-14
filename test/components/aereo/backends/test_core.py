from typing import Any, Sequence, cast
from unittest.mock import MagicMock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from pydantic import PrivateAttr
from shapely.geometry import Polygon

from aereo.backends import (
    LocalProcessBackend,
    TaskRunner,
    ThreadBackend,
)
from aereo.interfaces.core import (
    AereoPlugin,
    BatchWriter,
    ExtractionTask,
    GridConfig,
    PatchConfig,
    Processor,
    Reader,
    Reprojector,
    Writer,
)
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    pipeline: list[AereoPlugin] | None = None,
    task_context: dict[str, Any] | None = None,
    patches: list[Any] | None = None,
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    valid_df["collection"] = "C1"

    grid_config = GridConfig(target_grid_dist=50_000)
    from aereo.interfaces.core import ExtractConfig
    from aereo.builtins.read import ReadODCSTAC
    from aereo.builtins.reproject import ReprojectODC
    from aereo.builtins.write import WriteGeoTIFF

    extract = ExtractConfig(
        read=ReadODCSTAC(),
        reproject=ReprojectODC(),
        write=WriteGeoTIFF(),
    )
    # If pipeline args are provided, try to mock them into the extract config
    # In practice for test_core.py, the pipeline arg might just be a list of dummy plugins
    if pipeline:
        read_plugin = None
        reproject_plugin = None
        write_plugin = None
        pre_processors: Sequence[Processor] = []
        post_processors: Sequence[Processor] = []

        reproject_idx = -1
        writer_idx = -1
        for idx, plugin in enumerate(pipeline):
            if isinstance(plugin, Reader):
                read_plugin = plugin
            elif isinstance(plugin, Reprojector):
                reproject_plugin = plugin
                reproject_idx = idx
            elif isinstance(plugin, (Writer, BatchWriter)):
                write_plugin = plugin
                writer_idx = idx

        if reproject_idx != -1:
            pre_processors = cast(Sequence[Processor], pipeline[1:reproject_idx])
            if writer_idx != -1:
                post_processors = cast(
                    Sequence[Processor], pipeline[reproject_idx + 1 : writer_idx]
                )
            else:
                post_processors = cast(
                    Sequence[Processor], pipeline[reproject_idx + 1 :]
                )

        if read_plugin:
            extract = ExtractConfig(
                read=read_plugin,
                preprocess=pre_processors,
                reproject=reproject_plugin,
                postprocess=post_processors,
                write=write_plugin,
            )

    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=PatchConfig(resolution=10.0),
        output_uri="test-uri",
        search=None,
        extract=extract,
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        job=job,
        patches=patches or [],
        task_context=task_context or {},
    )


class _DummyReader(Reader):
    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyReprojector(Reprojector):
    def __call__(self, ds: xr.Dataset, task: ExtractionTask) -> dict[str, xr.Dataset]:
        return {patch.id: ds for patch in task.patches}


class _DummyWriter(Writer):
    def __call__(
        self, ds: xr.Dataset, task: ExtractionTask, cell: Any
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(
            GeoDataFrame[ArtifactSchema],
            gpd.GeoDataFrame(
                {"id": ["a1"]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
            ),
        )


class _DummyProcessor(Processor):
    value: int = 2

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        ds = ds.copy()
        ds["B04"] = ds["B04"] * self.value
        return ds


def _mock_patch(patch_id: str) -> MagicMock:
    """Return a minimal mock patch with the given id."""
    mock = MagicMock()
    mock.id = patch_id
    mock.geobox = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# TaskRunner
# ---------------------------------------------------------------------------


def test_task_runner_executes_pipeline():
    """Verify that TaskRunner runs the pipeline successfully."""
    # Create mock grid cell
    mock_cell = MagicMock()
    mock_cell.id = "cell-1"
    mock_cell.cell_geometry = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    mock_cell.utm_crs = "EPSG:4326"
    mock_cell.utm_footprint = mock_cell.cell_geometry
    mock_cell.area_def.return_value = MagicMock()

    pipeline = [
        _DummyReader(),
        _DummyProcessor(value=3),
        _DummyReprojector(),
        _DummyProcessor(value=2),
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, patches=[mock_cell])
    runner = TaskRunner()
    result = runner.run(task)

    assert isinstance(result, gpd.GeoDataFrame)
    assert not result.empty


def test_task_runner_callbacks():
    """Verify that TaskRunner invokes callbacks."""
    mock_cell = MagicMock()
    mock_cell.id = "cell-1"
    mock_cell.cell_geometry = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    mock_cell.utm_crs = "EPSG:4326"
    mock_cell.utm_footprint = mock_cell.cell_geometry
    mock_cell.area_def.return_value = MagicMock()

    pipeline = [
        _DummyReader(),
        _DummyReprojector(),
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, patches=[mock_cell])
    mock_callback = MagicMock()
    runner = TaskRunner(callbacks=[mock_callback])
    runner.run(task)

    mock_callback.on_task_start.assert_called_once_with(task)
    mock_callback.on_download_complete.assert_called_once_with(task)
    mock_callback.on_read_complete.assert_called_once()
    mock_callback.on_reproject_complete.assert_called_once()
    mock_callback.on_patch_write_complete.assert_called_once()
    mock_callback.on_task_complete.assert_called_once()


def test_task_runner_calls_reprojector_once_per_task():
    """Reprojector is called once per task, not once per patch."""
    mock_reprojector = MagicMock(spec=Reprojector)
    mock_reprojector.return_value = {"cell-1": xr.Dataset()}

    pipeline = [
        _DummyReader(),
        mock_reprojector,
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")])
    runner = TaskRunner()
    runner.run(task)

    mock_reprojector.assert_called_once()


def test_task_runner_raises_when_reprojector_misses_patch():
    """ValueError is raised when the reprojector omits a patch id."""

    class _SparseReprojector(Reprojector):
        def __call__(
            self, ds: xr.Dataset, task: ExtractionTask
        ) -> dict[str, xr.Dataset]:
            # Only return the first patch, omitting the second.
            return {task.patches[0].id: ds}

    pipeline = [
        _DummyReader(),
        _SparseReprojector(),
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, patches=[_mock_patch("a"), _mock_patch("b")])
    runner = TaskRunner()
    with pytest.raises(ValueError, match="did not return a dataset for every patch"):
        runner.run(task)


def test_task_runner_callbacks_fire_per_patch():
    """on_reproject_complete fires once for every patch."""
    mock_reprojector = MagicMock(spec=Reprojector)
    mock_reprojector.return_value = {"a": xr.Dataset(), "b": xr.Dataset()}

    pipeline = [
        _DummyReader(),
        mock_reprojector,
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, patches=[_mock_patch("a"), _mock_patch("b")])
    callback = MagicMock()
    runner = TaskRunner(callbacks=[callback])
    runner.run(task)

    assert callback.on_reproject_complete.call_count == 2


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


def test_task_runner_dispatches_to_batch_writer():
    """TaskRunner dispatches to BatchWriter when configured."""
    from aereo.interfaces.core import BatchWriter

    class _DummyBatchWriter(BatchWriter):
        def __call__(self, patches, task):
            assert "cell-1" in patches
            return gpd.GeoDataFrame(
                {"id": ["a1"]},
                geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
            )

    pipeline = [_DummyReader(), _DummyReprojector(), _DummyBatchWriter()]
    task = _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")])
    runner = TaskRunner()
    result = runner.run(task)
    assert isinstance(result, gpd.GeoDataFrame)


def test_task_runner_rejects_batch_writer_without_reprojector():
    """ValueError is raised when BatchWriter is used without a Reprojector."""
    from aereo.interfaces.core import BatchWriter

    class _DummyBatchWriter(BatchWriter):
        def __call__(self, patches, task):
            return gpd.GeoDataFrame()

    pipeline = [_DummyReader(), _DummyBatchWriter()]
    task = _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")])
    runner = TaskRunner()
    with pytest.raises(ValueError, match="BatchWriter requires a Reprojector"):
        runner.run(task)


# ---------------------------------------------------------------------------
# TaskResultCache integration
# ---------------------------------------------------------------------------


class _CountingReader(Reader):
    """Reader that counts how many times it is invoked."""

    _call_count: int = PrivateAttr(default=0)

    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        self._call_count += 1
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )

    @property
    def call_count(self) -> int:
        return self._call_count


class _FailingReader(Reader):
    """Reader that always raises."""

    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        raise RuntimeError("download failed")


def _task_with_output_uri(task: ExtractionTask, output_uri: str) -> ExtractionTask:
    """Return a copy of *task* with its job output_uri updated."""
    return cast(
        ExtractionTask,
        task.__class__(
            assets=task.assets,
            job=task.job.model_copy(update={"output_uri": output_uri}),
            patches=task.patches,
            task_context=task.task_context,
        ),
    )


def test_task_runner_cache_miss_executes_and_writes_cache(tmp_path):
    """When no cache exists, the pipeline runs and writes a cache file."""
    from aereo.cache import TaskResultCache

    pipeline = [_DummyReader(), _DummyReprojector(), _DummyWriter()]
    task = _task_with_output_uri(
        _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")]),
        str(tmp_path),
    )

    cache = TaskResultCache()
    runner = TaskRunner(cache=cache)
    result = runner.run(task)

    assert isinstance(result, gpd.GeoDataFrame)
    assert cache.path(task).exists()


def test_task_runner_cache_hit_skips_execution(tmp_path):
    """When a cache exists, the pipeline is skipped and cached artifacts are returned."""
    from aereo.cache import TaskResultCache

    reader = _CountingReader()
    task = _task_with_output_uri(
        _make_task(
            pipeline=[reader, _DummyReprojector(), _DummyWriter()],
            patches=[_mock_patch("cell-1")],
        ),
        str(tmp_path),
    )

    cache = TaskResultCache()
    runner = TaskRunner(cache=cache)
    first_result = runner.run(task)
    assert reader.call_count == 1

    second_result = runner.run(task)
    assert reader.call_count == 1
    assert len(second_result) == len(first_result)


def test_task_runner_overwrite_bypasses_cache(tmp_path):
    """When overwrite is True, the cache is ignored and the pipeline re-runs."""
    from aereo.cache import TaskResultCache

    reader = _CountingReader()
    task = _task_with_output_uri(
        _make_task(
            pipeline=[reader, _DummyReprojector(), _DummyWriter()],
            patches=[_mock_patch("cell-1")],
        ),
        str(tmp_path),
    )

    cache = TaskResultCache()
    runner = TaskRunner(cache=cache)
    runner.run(task)
    assert reader.call_count == 1

    overwrite_task = cast(
        ExtractionTask,
        task.__class__(
            assets=task.assets,
            job=task.job.model_copy(update={"overwrite": True}),
            patches=task.patches,
            task_context=task.task_context,
        ),
    )
    runner.run(overwrite_task)
    assert reader.call_count == 2


def test_task_runner_failure_does_not_write_cache(tmp_path):
    """Failed tasks must not leave a cache entry behind."""
    from aereo.cache import TaskResultCache

    task = _task_with_output_uri(
        _make_task(
            pipeline=[_FailingReader()],
            patches=[_mock_patch("cell-1")],
        ),
        str(tmp_path),
    )

    cache = TaskResultCache()
    runner = TaskRunner(cache=cache)
    with pytest.raises(RuntimeError, match="download failed"):
        runner.run(task)

    assert not cache.path(task).exists()


def test_task_runner_cache_callbacks_fire(tmp_path):
    """Cache hit/miss callbacks are invoked correctly."""
    from aereo.cache import TaskResultCache

    pipeline = [_DummyReader(), _DummyReprojector(), _DummyWriter()]
    task = _task_with_output_uri(
        _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")]),
        str(tmp_path),
    )

    cache = TaskResultCache()
    callback = MagicMock()
    runner = TaskRunner(cache=cache, callbacks=[callback])
    runner.run(task)

    callback.on_task_cache_miss.assert_called_once_with(task)
    callback.on_task_cache_hit.assert_not_called()

    # Second run hits cache.
    callback.reset_mock()
    runner.run(task)
    callback.on_task_cache_hit.assert_called_once_with(task)
    callback.on_task_cache_miss.assert_not_called()
