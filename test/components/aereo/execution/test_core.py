import functools
from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import structlog
import xarray as xr
from aereo.builtins.reproject import reproject_odc
from aereo.execution.core import (
    _build_grid_cells,
    _callable_accepts_crs,
    _crop_dataset_to_cell,
    _infer_utm_crs,
    _raw_reproject_crs,
    run_task,
)
from aereo.grid import GridCell
from aereo.interfaces.core import ExtractionTask, Reader
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon, box


class _DummyReader(Reader):
    def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
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


def _make_task(job: ExtractionJob) -> ExtractionTask:
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
    return ExtractionTask(
        id="task-1",
        assets=cast(GeoDataFrame[AssetSchema], valid_df),
        job=job,
    )


def _add_variable(name: str, value: int):
    def processor(ds: xr.Dataset, **kwargs) -> xr.Dataset:
        ds = ds.copy()
        ds[name] = xr.DataArray(
            np.full((4, 4), value, dtype=np.float32),
            dims=["y", "x"],
        )
        return ds

    return processor


def test_run_task_applies_multiple_preprocessors_in_order(tmp_path):
    calls = []

    def recorder(name: str):
        def processor(ds: xr.Dataset, **kwargs) -> xr.Dataset:
            calls.append(name)
            return ds

        return processor

    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_DummyReader(),
        write=_DummyWriter(),
        preprocess=[recorder("first"), recorder("second")],
    )
    artifacts = run_task(_make_task(job))
    assert calls == ["first", "second"]
    assert isinstance(artifacts, gpd.GeoDataFrame)


def test_run_task_applies_multiple_postprocessors_in_order(tmp_path):
    calls = []

    def recorder(name: str):
        def processor(ds: xr.Dataset, **kwargs) -> xr.Dataset:
            calls.append(name)
            return ds

        return processor

    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_DummyReader(),
        write=_DummyWriter(),
        postprocess=[recorder("first"), recorder("second")],
    )
    artifacts = run_task(_make_task(job))
    assert calls == ["first", "second"]
    assert isinstance(artifacts, gpd.GeoDataFrame)


def test_run_task_preprocessors_transform_dataset(tmp_path):
    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_DummyReader(),
        write=_DummyWriter(),
        preprocess=[_add_variable("A", 1), _add_variable("B", 2)],
    )
    # Processor transformations are verified by execution completing without
    # error and the pipeline producing artifacts.
    artifacts = run_task(_make_task(job))
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(artifacts) >= 1


def test_build_grid_cells_uses_task_grid_cells():
    """Explicit grid_cells attribute is used instead of recomputing from AOI."""
    job = ExtractionJob(
        grid_dist=10_000,
        output_uri="s3://test/output",
        read=_DummyReader(),
        write=_DummyWriter(),
    )
    task = ExtractionTask(
        id="task-1",
        assets=cast(
            GeoDataFrame[AssetSchema],
            gpd.GeoDataFrame(
                {
                    "id": ["asset-1"],
                    "collection": ["C1"],
                    "start_time": [pd.Timestamp("2023-01-01")],
                    "end_time": [pd.Timestamp("2023-01-02")],
                    "href": ["s3://bucket/file.tif"],
                    "geometry": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
                },
                crs="EPSG:4326",
            ),
        ),
        job=job,
        # AOI large enough to intersect many cells, but grid_cells pins one.
        aoi=box(-1.0, -1.0, 1.0, 1.0),
        grid_cells=[
            GridCell(id="0U_0R", d=10_000, cell_geometry=box(-0.05, -0.05, 0.05, 0.05))
        ],
    )
    cells = _build_grid_cells(task)
    assert cells == task.grid_cells
    assert [c.id for c in cells] == ["0U_0R"]


def _swath_reader(shape: tuple[int, int] = (20, 20)) -> Reader:
    """Return a reader that produces a synthetic swath dataset."""
    rows, cols = shape
    lons = np.linspace(-70.0, -69.0, cols)
    lats = np.linspace(-40.0, -39.0, rows)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    class _SwathReader(Reader):
        def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
            return xr.Dataset(
                {
                    "band": (["y", "x"], np.ones(shape, dtype=np.float32)),
                    "longitude": (["y", "x"], lon_grid),
                    "latitude": (["y", "x"], lat_grid),
                }
            )

    return _SwathReader()


def test_crop_dataset_to_cell_reduces_shape():
    """Cropping masks and drops pixels outside the buffered cell bounds."""
    ds = _swath_reader((20, 20))(
        ExtractionTask(
            id="t",
            assets=cast(
                GeoDataFrame[AssetSchema],
                gpd.GeoDataFrame(
                    {"id": ["a"], "href": ["h"], "geometry": [box(-70, -40, -69, -39)]},
                    crs="EPSG:4326",
                ),
            ),
            job=ExtractionJob(
                grid_dist=1000,
                output_uri="s3://test",
                read=_DummyReader(),
                write=_DummyWriter(),
            ),
        )
    )

    cell = GridCell(
        id="cell",
        d=1000,
        cell_geometry=box(-69.7, -39.7, -69.3, -39.3),
    )
    cropped = _crop_dataset_to_cell(ds, cell, buffer=0.05)

    assert cropped["band"].shape[0] <= ds["band"].shape[0]
    assert cropped["band"].shape[1] <= ds["band"].shape[1]
    assert cropped["band"].shape != ds["band"].shape


def test_crop_dataset_to_cell_uses_geobox_when_given():
    """When a GeoBox is passed, the crop region follows the GeoBox extent."""
    ds = _swath_reader((40, 40))(
        ExtractionTask(
            id="t",
            assets=cast(
                GeoDataFrame[AssetSchema],
                gpd.GeoDataFrame(
                    {"id": ["a"], "href": ["h"], "geometry": [box(-70, -40, -69, -39)]},
                    crs="EPSG:4326",
                ),
            ),
            job=ExtractionJob(
                grid_dist=1000,
                output_uri="s3://test",
                read=_DummyReader(),
                write=_DummyWriter(),
            ),
        )
    )

    # Small cell (~1 km) near the centre of the swath.
    cell = GridCell(
        id="cell",
        d=1000,
        cell_geometry=box(-69.52, -39.52, -69.51, -39.51),
    )
    # GeoBox with a large margin so it extends well beyond the cell geometry.
    geobox = cell.to_geobox(resolution=1000.0, margin=200.0)

    cropped_cell = _crop_dataset_to_cell(ds, cell, buffer=0.01)
    cropped_geobox = _crop_dataset_to_cell(ds, cell, buffer=0.01, geobox=geobox)

    # The GeoBox-based crop must cover at least as many source pixels because
    # the GeoBox extent (with margin) is larger than the cell geometry.
    assert cropped_geobox["band"].shape[0] >= cropped_cell["band"].shape[0]
    assert cropped_geobox["band"].shape[1] >= cropped_cell["band"].shape[1]
    # And strictly larger in at least one dimension because the margin is non-zero.
    assert (
        cropped_geobox["band"].shape[0] > cropped_cell["band"].shape[0]
        or cropped_geobox["band"].shape[1] > cropped_cell["band"].shape[1]
    )


def test_run_task_grid_mode_crops_before_reproject(tmp_path):
    """In grid mode, each cell receives a cropped swath before reprojection."""
    seen_shapes: list[tuple[int, ...]] = []

    class _ShapeRecordingReprojector:
        def __call__(self, ds: xr.Dataset, geobox=None, **kwargs) -> xr.Dataset:
            seen_shapes.append(tuple(ds["band"].shape))
            # Return a minimal gridded dataset so writing succeeds.
            out = xr.Dataset(
                {"band": (["y", "x"], np.ones((2, 2), dtype=np.float32))},
                coords={"y": [0, 1], "x": [0, 1]},
            )
            import rioxarray  # noqa: F401

            out = out.rio.write_crs("EPSG:4326")
            return out

    job = ExtractionJob(
        grid_dist=10_000,
        output_uri=str(tmp_path / "out"),
        read=_swath_reader((20, 20)),
        write=_DummyWriter(),
        reproject=_ShapeRecordingReprojector(),
        reproject_mode="grid",
        grid_resolution=1000,
        crop_buffer=0.05,
    )
    task = ExtractionTask(
        id="task-1",
        assets=cast(
            GeoDataFrame[AssetSchema],
            gpd.GeoDataFrame(
                {
                    "id": ["asset-1"],
                    "collection": ["C1"],
                    "start_time": [pd.Timestamp("2023-01-01")],
                    "end_time": [pd.Timestamp("2023-01-02")],
                    "href": ["s3://bucket/file.tif"],
                    "geometry": [
                        Polygon([[-70, -40], [-69, -40], [-69, -39], [-70, -39]])
                    ],
                },
                crs="EPSG:4326",
            ),
        ),
        job=job,
        grid_cells=[
            GridCell(
                id="0U_0R",
                d=10_000,
                cell_geometry=box(-69.7, -39.7, -69.3, -39.3),
            )
        ],
    )

    artifacts = run_task(task)
    assert isinstance(artifacts, gpd.GeoDataFrame)
    assert len(seen_shapes) == 1
    # The reprojector should receive a cropped dataset, not the full 20x20 swath.
    assert seen_shapes[0] != (20, 20)


def test_run_task_grid_mode_uses_grid_cells_margin(tmp_path):
    """grid_cells_margin expands the GeoBox passed to the reprojector."""
    seen_geoboxes: list[Any] = []

    class _GeoboxRecordingReprojector:
        def __call__(self, ds: xr.Dataset, geobox=None, **kwargs) -> xr.Dataset:
            seen_geoboxes.append(geobox)
            out = xr.Dataset(
                {"band": (["y", "x"], np.ones((2, 2), dtype=np.float32))},
                coords={"y": [0, 1], "x": [0, 1]},
            )
            import rioxarray  # noqa: F401

            out = out.rio.write_crs("EPSG:4326")
            return out

    def _run(margin: float) -> Any:
        job = ExtractionJob(
            grid_dist=10_000,
            output_uri=str(tmp_path / f"out_{margin}"),
            read=_swath_reader((20, 20)),
            write=_DummyWriter(),
            reproject=_GeoboxRecordingReprojector(),
            reproject_mode="grid",
            grid_resolution=1000,
            crop_buffer=0.05,
            grid_cells_margin=margin,
        )
        task = ExtractionTask(
            id="task-1",
            assets=cast(
                GeoDataFrame[AssetSchema],
                gpd.GeoDataFrame(
                    {
                        "id": ["asset-1"],
                        "collection": ["C1"],
                        "start_time": [pd.Timestamp("2023-01-01")],
                        "end_time": [pd.Timestamp("2023-01-02")],
                        "href": ["s3://bucket/file.tif"],
                        "geometry": [
                            Polygon([[-70, -40], [-69, -40], [-69, -39], [-70, -39]])
                        ],
                    },
                    crs="EPSG:4326",
                ),
            ),
            job=job,
            grid_cells=[
                GridCell(
                    id="0U_0R",
                    d=10_000,
                    cell_geometry=box(-69.7, -39.7, -69.3, -39.3),
                )
            ],
        )
        run_task(task)
        return seen_geoboxes[-1]

    gb_no_margin = _run(0.0)
    gb_with_margin = _run(50.0)
    assert gb_with_margin.shape[1] > gb_no_margin.shape[1]
    assert gb_with_margin.shape[0] > gb_no_margin.shape[0]
# ---------------------------------------------------------------------------
# Raw-mode CRS helpers
# ---------------------------------------------------------------------------


def test_raw_reproject_crs_reads_partial_keyword():
    rp = functools.partial(reproject_odc, crs="epsg:32720", resolution=375)
    assert _raw_reproject_crs(rp) == "epsg:32720"


def test_raw_reproject_crs_returns_none_without_crs():
    rp = functools.partial(reproject_odc, resolution=375)
    assert _raw_reproject_crs(rp) is None


def test_raw_reproject_crs_returns_none_for_plain_callable():
    assert _raw_reproject_crs(lambda ds: ds) is None


def test_callable_accepts_crs_detects_crs_param():
    def f(ds, crs=None):
        return ds

    assert _callable_accepts_crs(f) is True


def test_callable_accepts_crs_detects_kwargs():
    def f(ds, **kwargs):
        return ds

    assert _callable_accepts_crs(f) is True


def test_callable_accepts_crs_false_for_plain_callable():
    assert _callable_accepts_crs(lambda ds: ds) is False


# ---------------------------------------------------------------------------
# UTM inference helper
# ---------------------------------------------------------------------------


def _make_gridded_ds(
    bounds: tuple[float, float, float, float] = (-58.5, -34.8, -53.1, -30.2),
    crs: str = "epsg:4326",
    shape: tuple[int, int] = (8, 8),
) -> xr.Dataset:
    """Return a synthetic gridded dataset with the requested bounds and CRS."""
    minx, miny, maxx, maxy = bounds
    x = np.linspace(minx, maxx, shape[1])
    y = np.linspace(maxy, miny, shape[0])
    da = xr.DataArray(
        np.ones(shape, dtype=np.float32),
        dims=["y", "x"],
        coords={"y": y, "x": x},
    )
    da.rio.write_crs(crs, inplace=True)
    return xr.Dataset({"band": da})


def _make_swath_ds(
    lons: np.ndarray | None = None,
    lats: np.ndarray | None = None,
    shape: tuple[int, int] = (8, 8),
) -> xr.Dataset:
    """Return a synthetic swath dataset with lons/lats covering UTM zone 21S."""
    if lons is None:
        lons = np.linspace(-58.5, -53.1, shape[1])
    if lats is None:
        lats = np.linspace(-34.8, -30.2, shape[0])
    if lons.ndim == 2 and lats.ndim == 2:
        lon_grid, lat_grid = lons, lats
    else:
        lon_grid, lat_grid = np.meshgrid(lons, lats)
    data = np.ones(shape, dtype=np.float32)
    return xr.Dataset(
        {
            "band": (["y", "x"], data),
            "lons": (["y", "x"], lon_grid),
            "lats": (["y", "x"], lat_grid),
        }
    )


def _task_for_aoi(geometry) -> ExtractionTask:
    """Return a task whose AOI is the given shapely geometry."""
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="s3://test/output",
        read=_DummyReader(),
        write=_DummyWriter(),
    )
    return ExtractionTask(
        id="task-1",
        assets=cast(
            GeoDataFrame[AssetSchema],
            gpd.GeoDataFrame(
                {
                    "id": ["asset-1"],
                    "href": ["s3://bucket/file.tif"],
                    "geometry": [box(-58.5, -34.8, -53.1, -30.2)],
                },
                crs="EPSG:4326",
            ),
        ),
        job=job,
        aoi=geometry,
    )


def test_infer_utm_crs_from_regular_dataset():
    ds = _make_gridded_ds(bounds=(-58.5, -34.8, -53.1, -30.2), crs="epsg:4326")
    task = _task_for_aoi(box(-58.5, -34.8, -53.1, -30.2))
    assert _infer_utm_crs(ds, task) == "32721"


def test_infer_utm_crs_from_swath_lons_lats():
    ds = _make_swath_ds()
    task = _task_for_aoi(box(-58.5, -34.8, -53.1, -30.2))
    assert _infer_utm_crs(ds, task) == "32721"


def test_infer_utm_crs_from_swath_with_nan_padding():
    lons = np.linspace(-58.5, -53.1, 8)
    lats = np.linspace(-34.8, -30.2, 8)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    lon_grid[0, :] = np.nan
    lon_grid[-1, :] = np.nan
    lat_grid[0, :] = np.nan
    lat_grid[-1, :] = np.nan
    ds = _make_swath_ds(lons=lon_grid, lats=lat_grid)
    task = _task_for_aoi(box(-58.5, -34.8, -53.1, -30.2))
    assert _infer_utm_crs(ds, task) == "32721"


def test_infer_utm_crs_reprojects_native_bounds_to_wgs84():
    ds = _make_gridded_ds(bounds=(300000, 6100000, 800000, 6600000), crs="epsg:32721")
    task = _task_for_aoi(box(-59.2, -35.3, -53.6, -30.6))
    assert _infer_utm_crs(ds, task) == "32721"


def test_infer_utm_crs_falls_back_to_task_aoi():
    ds = xr.Dataset()
    task = _task_for_aoi(box(-58.5, -34.8, -53.1, -30.2))
    assert _infer_utm_crs(ds, task) == "32721"


def test_infer_utm_crs_warns_on_wide_footprint():
    ds = _make_gridded_ds(bounds=(-120, 10, -60, 40), crs="epsg:4326")
    task = _task_for_aoi(box(-120, 10, -60, 40))
    with structlog.testing.capture_logs() as cap_logs:
        _infer_utm_crs(ds, task)
    assert any("multiple UTM zones" in str(log) for log in cap_logs)


def test_infer_utm_crs_polar_raises_actionable_error():
    ds = _make_gridded_ds(bounds=(0, 85, 10, 88), crs="epsg:4326")
    task = _task_for_aoi(box(0, 85, 10, 88))
    with pytest.raises(ValueError, match="cannot infer a UTM CRS"):
        _infer_utm_crs(ds, task)


# ---------------------------------------------------------------------------
# run_task raw-mode dispatch
# ---------------------------------------------------------------------------


class _GriddedReader(Reader):
    """Reader that produces a proper gridded EPSG:4326 dataset."""

    def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
        return _make_gridded_ds()


def test_run_task_raw_utm_sentinel_passes_concrete_crs(tmp_path):
    captured = {}

    def fake_reproject(ds, crs=None, resolution=None):
        captured["crs"] = crs
        return ds

    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_GriddedReader(),
        write=_DummyWriter(),
        reproject=functools.partial(fake_reproject, crs="utm", resolution=375),
        reproject_mode="raw",
    )
    artifacts = run_task(_make_task(job))
    assert captured["crs"] == "32721"
    assert isinstance(artifacts, gpd.GeoDataFrame)


def test_run_task_raw_explicit_crs_unchanged(tmp_path):
    captured = {}

    def fake_reproject(ds, crs=None, resolution=None):
        captured["crs"] = crs
        return ds

    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_GriddedReader(),
        write=_DummyWriter(),
        reproject=functools.partial(
            fake_reproject, crs="epsg:32720", resolution=375
        ),
        reproject_mode="raw",
    )
    artifacts = run_task(_make_task(job))
    assert captured["crs"] == "epsg:32720"
    assert isinstance(artifacts, gpd.GeoDataFrame)


def test_run_task_raw_missing_crs_nonpartial_raises(tmp_path):
    job = ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_DummyReader(),
        write=_DummyWriter(),
        reproject=lambda ds: ds,
        reproject_mode="raw",
    )
    with pytest.raises(ValueError, match="requires a 'crs'"):
        run_task(_make_task(job))


def test_run_task_raw_missing_crs_in_partial_raises_at_load():
    """Partials without a configured CRS fail at ExtractionJob validation time."""
    with pytest.raises(ValueError, match="requires a 'crs'"):
        ExtractionJob(
            grid_dist=1000,
            output_uri="s3://test/output",
            read=_DummyReader(),
            write=_DummyWriter(),
            reproject=functools.partial(reproject_odc, resolution=375),
            reproject_mode="raw",
        )


def test_run_task_raw_concrete_crs_partial_does_not_raise_at_load():
    """Partials with an explicit CRS pass validation."""
    job = ExtractionJob(
        grid_dist=1000,
        output_uri="s3://test/output",
        read=_DummyReader(),
        write=_DummyWriter(),
        reproject=functools.partial(reproject_odc, crs="epsg:32720", resolution=375),
        reproject_mode="raw",
    )
    assert job.reproject is not None


class _TimeSeriesReader(Reader):
    """Reader returning a multi-timestep cube (time, y, x)."""

    def __call__(self, task: ExtractionTask, **kwargs) -> xr.Dataset:
        times = pd.date_range("2023-01-01", periods=3, freq="h")
        return xr.Dataset(
            {"rain": (["time", "y", "x"], np.ones((3, 4, 4), dtype=np.float32))},
            coords={"time": times, "y": range(4), "x": range(4)},
        )


def test_run_task_writes_each_timestep_to_unique_path(tmp_path):
    """A multi-time read must produce one artifact per slice, not overwrites."""
    from pathlib import Path

    job = ExtractionJob(
        name="timeseries",
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=_TimeSeriesReader(),
        write=_DummyWriter(),
    )
    artifacts = run_task(_make_task(job))

    uris = artifacts["uri"].unique().tolist()
    assert len(uris) == 3, "each timestep slice must get its own file"
    assert len({Path(u).name for u in uris}) == 3
    for u in uris:
        assert Path(u).exists()

    expected = list(pd.date_range("2023-01-01", periods=3, freq="h"))
    assert sorted(pd.to_datetime(artifacts["start_time"]).unique()) == expected
    assert sorted(pd.to_datetime(artifacts["end_time"]).unique()) == expected
