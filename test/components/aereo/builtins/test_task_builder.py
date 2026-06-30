"""Tests for aereo.builtins.task_builder."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import geopandas as gpd
import pytest
from shapely.geometry import box

from aereo.builtins.read import read_odc_stac
from aereo.builtins.task_builder import build_grouped_tasks
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame


def _make_job(
    output_uri: str = "s3://test/output",
    target_aoi: Any = None,
) -> ExtractionJob:
    """Return a minimal ExtractionJob for task-builder tests."""
    kwargs: dict[str, Any] = {}
    if target_aoi is not None:
        kwargs["target_aoi"] = target_aoi
    return ExtractionJob(
        name="test-job",
        grid_dist=10_000,
        output_uri=output_uri,
        read=read_odc_stac,
        write=lambda ds, path, **kwargs: str(path),
        **kwargs,
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
    """Each task carries extraction configuration derived from the parent job."""
    assets = _make_assets(geometries=[box(2.0, 45.0, 2.1, 45.1)])
    job = _make_job()

    builder = build_grouped_tasks
    tasks = list(builder(assets, job))

    assert len(tasks) == 1
    assert tasks[0].job is job
    assert tasks[0].job.name == job.name
    assert tasks[0].aoi is not None
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


def test_grouped_task_builder_chunks_by_cells_per_task():
    """A group that intersects more cells than cells_per_task is split into tasks."""
    assets = _make_assets(geometries=[box(0.0, 0.0, 0.2, 0.2)])
    job = _make_job(target_aoi=box(0.0, 0.0, 0.2, 0.2))

    tasks = list(build_grouped_tasks(assets, job, cells_per_task=4))

    # A 0.2x0.2 degree box at the equator with 10 km cells yields 9 cells.
    assert len(tasks) == 3
    for task in tasks:
        assert task.aoi is not None
        assert task.task_context["grid_cells"]
        assert len(task.task_context["grid_cells"]) <= 4


def test_grouped_task_builder_one_task_when_cells_fit():
    """A single chunk is created when all cells fit within cells_per_task."""
    assets = _make_assets(geometries=[box(0.0, 0.0, 0.2, 0.2)])
    job = _make_job(target_aoi=box(0.0, 0.0, 0.2, 0.2))

    tasks = list(build_grouped_tasks(assets, job, cells_per_task=100))

    assert len(tasks) == 1
    assert len(tasks[0].task_context["grid_cells"]) == 9


def test_grouped_task_builder_cells_per_task_one():
    """Setting cells_per_task=1 yields one task per intersecting cell."""
    assets = _make_assets(geometries=[box(0.0, 0.0, 0.2, 0.2)])
    job = _make_job(target_aoi=box(0.0, 0.0, 0.2, 0.2))

    tasks = list(build_grouped_tasks(assets, job, cells_per_task=1))

    assert len(tasks) == 9
    for task in tasks:
        assert len(task.task_context["grid_cells"]) == 1


def test_grouped_task_builder_uses_asset_target_aoi_intersection():
    """Cells are selected from the intersection of asset footprints and target AOI."""
    assets = _make_assets(geometries=[box(0.0, 0.0, 1.0, 1.0)])
    job = _make_job(target_aoi=box(0.0, 0.0, 0.2, 0.2))

    tasks = list(build_grouped_tasks(assets, job, cells_per_task=100))

    assert len(tasks) == 1
    assert tasks[0].aoi is not None
    # The task AOI should be within / aligned with the target AOI cells, not the
    # full asset footprint.
    assert tasks[0].aoi.within(box(0.0, 0.0, 0.3, 0.3))


def test_grouped_task_builder_rejects_non_positive_cells_per_task():
    """A non-positive cells_per_task raises ValueError."""
    assets = _make_assets(geometries=[box(0.0, 0.0, 0.2, 0.2)])
    job = _make_job()

    with pytest.raises(ValueError, match="cells_per_task must be a positive integer"):
        list(build_grouped_tasks(assets, job, cells_per_task=0))


def test_grouped_task_builder_no_init_params():
    """The removed init_params keyword is no longer accepted."""
    assets = _make_assets(geometries=[box(0.0, 0.0, 0.2, 0.2)])
    job = _make_job()

    with pytest.raises(Exception, match="init_params"):
        list(
            build_grouped_tasks(
                assets,
                job,
                init_params={},  # pyright: ignore[reportCallIssue]
            )
        )
