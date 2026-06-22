"""Tests for the synthetic Lambda test pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import geopandas as gpd
from aereo.grid import ExtractionPatch
from aereo.interfaces import ExtractConfig, ExtractionTask, GridConfig, PatchConfig
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema, ArtifactSchema
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
    patch = ExtractionPatch(
        id="0U_0R",
        d=50_000,
        cell_geometry=Polygon([[0, 0], [0.005, 0], [0.005, 0.005], [0, 0.005]]),
        resolution=100.0,
        margin=0.0,
        padding=0,
    )
    job = ExtractionJob(
        name="test-job",
        grid_config=GridConfig(target_grid_dist=50_000),
        patch_config=PatchConfig(resolution=100.0),
        output_uri=str(tmp_path / "output"),
        search=None,
        extract=ExtractConfig(
            read=TestReader(),
            reproject=TestReprojector(),
            write=TestWriter(),
        ),
    )
    return ExtractionTask(
        assets=GeoDataFrame[AssetSchema](df),
        job=job,
        patches=[patch],
        task_context={"job_id": "test-job", "chunk_id": 0},
    )


def test_reader_returns_dataset_with_time_bounds():
    ds = TestReader()(_make_task(Path("/tmp")))
    assert "band1" in ds.data_vars
    assert ds.attrs["start_time"] is not None
    assert ds.attrs["end_time"] is not None


def test_reprojector_returns_one_dataset_per_patch():
    task = _make_task(Path("/tmp"))
    ds = TestReader()(task)
    result = TestReprojector()(ds, task)
    assert set(result) == {patch.id for patch in task.patches}


def test_writer_creates_file_and_valid_artifact(tmp_path: Path):
    task = _make_task(tmp_path)
    ds = TestReader()(task)
    reprojected = TestReprojector()(ds, task)
    patch = task.patches[0]

    artifacts = TestWriter()(reprojected[patch.id], task, patch)

    ArtifactSchema.validate(artifacts)
    assert len(artifacts) == 1
    assert artifacts["collection"].iloc[0] == "test"
    artifact_uri = artifacts["uri"].iloc[0]
    assert Path(artifact_uri).exists()


def test_full_pipeline_via_task_runner(tmp_path: Path):
    from aereo.backends import TaskRunner

    task = _make_task(tmp_path)
    runner = TaskRunner()
    artifacts = runner.run(task)

    ArtifactSchema.validate(artifacts)
    assert len(artifacts) == 1
    assert Path(artifacts["uri"].iloc[0]).exists()
