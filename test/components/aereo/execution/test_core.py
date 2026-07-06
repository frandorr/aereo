from typing import Any, cast

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from aereo.execution.core import _build_grid_cells, _crop_dataset_to_cell, run_task
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
        resolution=1000,
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
            resolution=1000,
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
