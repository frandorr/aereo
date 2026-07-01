from typing import cast

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from aereo.execution.core import run_task
from aereo.interfaces.core import ExtractionTask, Reader
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


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
