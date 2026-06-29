import inspect
from typing import Any, Sequence, cast
from unittest.mock import MagicMock

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
    AereoPlugin,
    ExtractionTask,
    GridConfig,
    PatchConfig,
    Processor,
    Reprojector,
)
from aereo.pipeline import ExtractionJob
from aereo.schemas.core import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame


def _call_params(plugin: Any) -> set[str]:
    """Return the parameter names of a callable's __call__ method."""
    try:
        sig = inspect.signature(plugin.__call__)
    except (ValueError, TypeError):
        return set()
    return set(sig.parameters.keys())


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
    from aereo.builtins.read import read_odc_stac
    from aereo.builtins.reproject import reproject_odc
    from aereo.builtins.write import write_geotiff

    extract = ExtractConfig(
        read=read_odc_stac,
        reproject=reproject_odc,
        write=write_geotiff,
    )
    if pipeline:
        read_plugin = pipeline[0]
        reproject_plugin = None
        write_plugin = None
        pre_processors: Sequence[Processor] = []
        post_processors: Sequence[Processor] = []

        reproject_idx = -1
        writer_idx = -1
        for idx, plugin in enumerate(pipeline):
            if idx == 0:
                continue
            params = _call_params(plugin)
            is_magic = isinstance(plugin, MagicMock)
            is_reprojector = (
                "ds" in params and "task" in params and "patch" not in params
            )
            is_writer = "patch" in params

            if is_reprojector or (is_magic and writer_idx == -1):
                reproject_plugin = plugin
                reproject_idx = idx
            elif is_writer:
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
        extract=extract,
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame, valid_df),
        job=job,
        patches=patches or [],
        task_context=task_context or {},
    )


class _DummyReader:
    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        return xr.Dataset(
            {"B04": (["y", "x"], np.ones((4, 4)))},
            coords={"y": range(4), "x": range(4)},
        )


class _DummyReprojector:
    def __call__(self, ds: xr.Dataset, task: ExtractionTask) -> dict[str, xr.Dataset]:
        return {patch.id: ds for patch in task.patches}


class _DummyWriter:
    def __call__(
        self, ds: xr.Dataset, task: ExtractionTask, patch: Any
    ) -> GeoDataFrame[ArtifactSchema]:
        return cast(
            GeoDataFrame[ArtifactSchema],
            gpd.GeoDataFrame(
                {"id": ["a1"]}, geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])]
            ),
        )


class _DummyProcessor:
    value: int = 2

    def __init__(self, value: int = 2) -> None:
        self.value = value

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        ds = ds.copy()
        ds["B04"] = ds["B04"] * self.value
        return ds


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


# ---------------------------------------------------------------------------
# run_task
# ---------------------------------------------------------------------------


def test_run_task_executes_pipeline():
    """Verify that run_task runs the pipeline successfully."""
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
    result = run_task(task)

    assert isinstance(result, gpd.GeoDataFrame)
    assert not result.empty


def test_run_task_calls_reprojector_once_per_task():
    """Reprojector is called once per task, not once per patch."""
    mock_reprojector = MagicMock(spec=Reprojector)
    mock_reprojector.return_value = {"cell-1": xr.Dataset()}

    pipeline = [
        _DummyReader(),
        mock_reprojector,
        _DummyWriter(),
    ]

    task = _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")])
    run_task(task)

    mock_reprojector.assert_called_once()


def test_run_task_raises_when_reprojector_misses_patch():
    """ValueError is raised when the reprojector omits a patch id."""

    class _SparseReprojector:
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
    with pytest.raises(ValueError, match="did not return a dataset for every patch"):
        run_task(task)


def test_run_task_raises_when_reader_is_missing():
    """ValueError is raised when the extract config has no reader."""
    task = _make_task()
    job = task.job.model_copy(
        update={"extract": task.extract.model_copy(update={"read": None})}
    )
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
    pipeline = [_DummyReader(), _DummyReprojector(), _DummyWriter()]
    tasks = [
        _make_task(pipeline=pipeline, patches=[_mock_patch("cell-1")]),
        _make_task(pipeline=pipeline, patches=[_mock_patch("cell-2")]),
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
        pipeline=[_FailingReader(), _DummyReprojector(), _DummyWriter()],
        patches=[_mock_patch("a")],
    )
    ok_pipeline = [_DummyReader(), _DummyReprojector(), _DummyWriter()]
    ok_task = _make_task(pipeline=ok_pipeline, patches=[_mock_patch("b")])

    executor = LocalExecutor(failure_mode="best_effort")
    artifacts = executor([failing_task, ok_task])

    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) == 1


def test_local_executor_strict_propagates_failure(monkeypatch):
    monkeypatch.setattr("aereo.schemas.core.ArtifactSchema.validate", lambda x: x)

    failing_task = _make_task(
        pipeline=[_FailingReader(), _DummyReprojector(), _DummyWriter()],
        patches=[_mock_patch("a")],
    )

    executor = LocalExecutor(failure_mode="strict")
    with pytest.raises(RuntimeError, match="read failed"):
        executor([failing_task])


def test_local_executor_sequential_when_workers_none():
    executor = LocalExecutor(workers=None)
    pipeline = [_DummyReader(), _DummyReprojector(), _DummyWriter()]
    tasks = [
        _make_task(pipeline=pipeline, patches=[_mock_patch("a")]),
        _make_task(pipeline=pipeline, patches=[_mock_patch("b")]),
    ]
    artifacts = executor(tasks)
    assert len(artifacts) == 2


def test_local_executor_thread_pool():
    executor = LocalExecutor(workers=2, use_threads=True)
    pipeline = [_DummyReader(), _DummyReprojector(), _DummyWriter()]
    tasks = [
        _make_task(pipeline=pipeline, patches=[_mock_patch("a")]),
        _make_task(pipeline=pipeline, patches=[_mock_patch("b")]),
    ]
    artifacts = executor(tasks)
    assert len(artifacts) == 2
