"""Tests for the synthetic Lambda test pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import geopandas as gpd
from aereo.interfaces import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon
from test_pipeline import TestReader, TestReprojector, TestWriter


def _make_task(tmp_path: Path) -> ExtractionTask:
    df = gpd.GeoDataFrame(
        {
            "id": ["asset_1"],
            "collection": ["test"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
            "end_time": [datetime(2023, 1, 1, 12, 30)],
            "href": ["s3://bucket/key.tif"],
        },
        geometry=[Polygon([[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01]])],
        crs="EPSG:4326",
    )
    job = ExtractionJob(
        name="test-job",
        grid_dist=50_000,
        output_uri=str(tmp_path / "output"),
        resolution=100.0,
        read=TestReader(),
        write=TestWriter(),
    )
    return ExtractionTask(
        id="task-0",
        assets=GeoDataFrame[AssetSchema](df),
        job=job,
        task_context={"job_id": "test-job", "chunk_id": 0},
    )


def test_reader_returns_dataset_with_time_bounds():
    ds = TestReader()(["s3://bucket/key.tif"])
    assert "band1" in ds.data_vars
    assert ds.attrs["start_time"] is not None
    assert ds.attrs["end_time"] is not None


def test_reprojector_returns_dataset_unchanged():
    ds = TestReader()(["s3://bucket/key.tif"])
    result = TestReprojector()(ds)
    assert result is ds


def test_writer_creates_file(tmp_path: Path):
    ds = TestReader()(["s3://bucket/key.tif"])
    out_path = tmp_path / "out" / "test.tif"
    written = TestWriter()(ds, out_path)

    assert Path(written).exists()


def test_full_pipeline_via_run_task(tmp_path: Path):
    from aereo.execution import run_task

    task = _make_task(tmp_path)
    artifacts = run_task(task)

    assert len(artifacts) >= 1
    assert Path(artifacts["uri"].iloc[0]).exists()
