"""Tests for aereo.builtins.task_builder."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import geopandas as gpd
import pytest
from shapely.geometry import box

from aereo.builtins.read import read_odc_stac
from aereo.builtins.task_builder import build_grouped_tasks
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


def _make_job(output_uri: str = "s3://test/output") -> ExtractionJob:
    """Return a minimal ExtractionJob for task-builder tests."""
    return ExtractionJob(
        name="test-job",
        grid_dist=10_000,
        output_uri=output_uri,
        read=read_odc_stac,
        write=lambda ds, path, **kwargs: str(path),
    )


def _make_assets(
    geometries: list,
    crs_values: list[str | None] | None = None,
    start_times: list[datetime] | None = None,
) -> GeoDataFrame[AssetSchema]:
    """Return a validated AssetSchema GeoDataFrame."""
    if start_times is None:
        start_times = [datetime(2023, 1, 1)] * len(geometries)
    rows = []
    for idx, (geom, start) in enumerate(zip(geometries, start_times)):
        row: dict = {
            "id": f"asset-{idx}",
            "collection": "test-collection",
            "geometry": geom,
            "start_time": start,
            "end_time": start,
            "href": f"https://example.com/{idx}.tif",
        }
        if crs_values is not None:
            row["crs"] = crs_values[idx]
        rows.append(row)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return cast(GeoDataFrame, AssetSchema.validate(gdf))


def test_grouped_task_builder_groups_by_crs():
    """Assets with the same start_time but different CRS split into separate tasks."""
    geometries = [
        box(2.0, 45.0, 2.1, 45.1),  # UTM zone 31N-ish
        box(8.0, 45.0, 8.1, 45.1),  # UTM zone 32N-ish
    ]
    assets = _make_assets(
        geometries=geometries,
        crs_values=["EPSG:32631", "EPSG:32632"],
    )

    builder = build_grouped_tasks
    tasks = list(builder(assets, _make_job()))

    assert len(tasks) == 2
    for task in tasks:
        assert task.assets["crs"].nunique() == 1


def test_grouped_task_builder_warns_without_crs():
    """A warning is emitted when the assets GeoDataFrame has no crs column."""
    assets = _make_assets(
        geometries=[box(2.0, 45.0, 2.1, 45.1)],
        crs_values=None,
    )

    builder = build_grouped_tasks
    with pytest.warns(UserWarning, match="no 'crs' column"):
        tasks = list(builder(assets, _make_job()))

    assert len(tasks) == 1


def test_grouped_task_builder_rejects_partial_crs():
    """A ValueError is raised if crs exists but contains nulls."""
    assets = _make_assets(
        geometries=[
            box(2.0, 45.0, 2.1, 45.1),
            box(2.2, 45.0, 2.3, 45.1),
        ],
        crs_values=["EPSG:32631", None],
    )

    builder = build_grouped_tasks
    with pytest.raises(ValueError, match="contains null values"):
        list(builder(assets, _make_job()))


def test_grouped_task_builder_includes_job_name():
    """Each task carries a reference to the parent job."""
    assets = _make_assets(geometries=[box(2.0, 45.0, 2.1, 45.1)])
    job = _make_job()

    builder = build_grouped_tasks
    tasks = list(builder(assets, job))

    assert len(tasks) == 1
    assert tasks[0].job is job
    assert tasks[0].id.startswith(job.name)


def test_grouped_task_builder_generates_unique_task_ids():
    """Task ids are unique across all tasks."""
    geometries = [
        box(2.0, 45.0, 2.1, 45.1),
        box(8.0, 45.0, 8.1, 45.1),
    ]
    assets = _make_assets(
        geometries=geometries,
        crs_values=["EPSG:32631", "EPSG:32632"],
    )

    builder = build_grouped_tasks
    tasks = list(builder(assets, _make_job()))

    ids = [t.id for t in tasks]
    assert len(ids) == len(set(ids))
