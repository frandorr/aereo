"""Core per-task extraction pipeline execution.

Defines :func:`run_task`, the plain per-task pipeline that executes
read -> [preprocess] -> [reproject] -> [postprocess] -> write.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, cast

import geopandas as gpd
import pandas as pd
import rioxarray  # noqa: F401
import xarray as xr
from aereo.eoids import build_eoids_path
from aereo.grid import GridCell, build_grid_cells, intersect_cells
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import box


def _resolve_aoi(task: ExtractionTask) -> Any:
    """Return the AOI geometry used to build the MajorTOM grid.

    Prefers ``job.target_aoi``. Falls back to the union of task asset geometries.
    """
    job = task.job
    if job.target_aoi is not None:
        return job.target_aoi
    if "geometry" in task.assets.columns and not task.assets.geometry.isna().all():
        return task.assets.geometry.union_all()
    return None


def _build_grid_cells(task: ExtractionTask) -> Sequence[GridCell]:
    """Build grid cells for the task's AOI and grid parameters."""
    job = task.job
    aoi = _resolve_aoi(task)
    if aoi is None:
        return []
    if job.resolution is None:
        raise ValueError(
            "resolution is required when building grid cells for reprojection or "
            "artifact indexing."
        )
    return build_grid_cells(
        aoi=aoi,
        grid_dist=job.grid_dist,
        resolution=job.resolution,
        margin=job.margin,
    )


def _derive_time_bounds(
    task: ExtractionTask,
) -> tuple[datetime | None, datetime | None]:
    """Derive start/end time from task assets."""
    assets = task.assets
    start_time = None
    end_time = None
    if "start_time" in assets.columns:
        start_time = pd.to_datetime(assets["start_time"]).min().to_pydatetime()
    if "end_time" in assets.columns:
        end_time = pd.to_datetime(assets["end_time"]).max().to_pydatetime()
    return start_time, end_time


def _derive_source_ids(task: ExtractionTask) -> str:
    """Derive comma-separated source IDs from task assets."""
    if "id" not in task.assets.columns:
        return ""
    ids = task.assets["id"].dropna().astype(str).unique()
    return ",".join(sorted(ids))


def _derive_collection(task: ExtractionTask) -> str | None:
    """Derive collection from task assets."""
    if "collection" not in task.assets.columns:
        return None
    collections = task.assets["collection"].dropna().unique()
    return str(collections[0]) if len(collections) > 0 else None


def _build_output_path(
    ds: xr.Dataset,
    task: ExtractionTask,
    cell_id: str | None = None,
) -> Path:
    """Build the EOIDS output path for a dataset slice."""
    job = task.job
    start_time, end_time = _derive_time_bounds(task)
    collections = None
    if "collection" in task.assets.columns:
        collections = [
            str(c) for c in task.assets["collection"].dropna().unique().tolist()
        ]

    return build_eoids_path(
        local_dir=job.output_uri,
        job_name=job.name,
        resolution=job.resolution or 0.0,
        collections=collections,
        variables=[str(v) for v in ds.data_vars],
        cell_id=cell_id,
        start_time=start_time,
        end_time=end_time,
        suffix="tif",
    )


def _write_single_timestep(
    ds: xr.Dataset,
    task: ExtractionTask,
    cell_id: str | None = None,
) -> str:
    """Write a single time-slice dataset and return the written path."""
    path = _build_output_path(ds, task, cell_id=cell_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = task.job.write(ds, str(path), **(task.job.write_kwargs or {}))
    return str(written)


def _read_written_footprint(path: str) -> tuple[tuple[float, float, float, float], str]:
    """Return (bounds, crs) for a written raster file."""

    da = xr.open_dataarray(path)
    try:
        bounds = da.rio.bounds()
        crs = da.rio.crs.to_string()
        return bounds, crs
    finally:
        da.close()


def _artifact_rows(
    path: str,
    task: ExtractionTask,
    grid_cells: Sequence[GridCell],
    cell_id: str | None = None,
) -> GeoDataFrame[ArtifactSchema]:
    """Build ArtifactSchema rows for a written file.

    If *cell_id* is provided (grid mode), emit a single row for that cell.
    Otherwise intersect the file footprint with the grid and emit one row per
    intersecting cell.
    """
    bounds, file_crs = _read_written_footprint(path)
    source_ids = _derive_source_ids(task)
    start_time, end_time = _derive_time_bounds(task)
    collection = _derive_collection(task)
    grid_dist = task.job.grid_dist

    if cell_id is not None:
        target_cells = [c for c in grid_cells if c.id == cell_id]
    else:
        target_cells = intersect_cells(bounds, grid_cells, crs=file_crs)

    records = []
    for cell in target_cells:
        record = {
            "id": f"{cell.id}_{uuid.uuid4().hex[:8]}",
            "source_ids": source_ids,
            "start_time": start_time,
            "end_time": end_time,
            "uri": path,
            "collection": collection,
            "geometry": box(*bounds),
            "grid_cell": cell.id,
            "grid_dist": grid_dist,
            "cell_geometry": cell.cell_geometry,
            "cell_utm_crs": cell.utm_crs,
            "cell_utm_footprint": cell.utm_footprint,
        }
        records.append(record)

    if not records:
        return ArtifactSchema.empty_geodataframe()

    df = pd.DataFrame(records)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=file_crs)
    return cast(GeoDataFrame[ArtifactSchema], ArtifactSchema.validate(gdf))


def _write_dataset(
    ds: xr.Dataset,
    task: ExtractionTask,
    grid_cells: Sequence[GridCell],
    cell_id: str | None = None,
) -> GeoDataFrame[ArtifactSchema]:
    """Write a dataset (splitting time if needed) and build artifact rows."""
    if "time" in ds.dims:
        artifacts: list[GeoDataFrame[ArtifactSchema]] = []
        for t in ds.time.values:
            slice_ds = ds.sel(time=t).drop_vars("time", errors="ignore")
            path = _write_single_timestep(slice_ds, task, cell_id=cell_id)
            artifacts.append(_artifact_rows(path, task, grid_cells, cell_id=cell_id))
        return _concat_artifacts(artifacts)

    path = _write_single_timestep(ds, task, cell_id=cell_id)
    return _artifact_rows(path, task, grid_cells, cell_id=cell_id)


def _concat_artifacts(
    artifacts: list[GeoDataFrame[ArtifactSchema]],
) -> GeoDataFrame[ArtifactSchema]:
    """Concatenate artifact GeoDataFrames."""
    if not artifacts:
        return ArtifactSchema.empty_geodataframe()
    gdf = gpd.GeoDataFrame(
        pd.concat(artifacts, ignore_index=True),
        geometry="geometry",
    )
    return cast(GeoDataFrame[ArtifactSchema], ArtifactSchema.validate(gdf))


def _run_grid_reproject(
    ds: xr.Dataset,
    task: ExtractionTask,
    grid_cells: Sequence[GridCell],
) -> GeoDataFrame[ArtifactSchema]:
    """Run reprojection in grid mode: one file per cell."""
    job = task.job
    reproject = job.reproject
    assert reproject is not None

    bounds = ds.rio.bounds()
    file_crs = ds.rio.crs.to_string()
    cells = intersect_cells(bounds, grid_cells, crs=file_crs)

    artifacts: list[GeoDataFrame[ArtifactSchema]] = []
    for cell in cells:
        kwargs = dict(job.reproject_kwargs or {})
        kwargs["geobox"] = cell.to_geobox()
        cell_ds = reproject(ds, **kwargs)

        if job.postprocess:
            cell_ds = job.postprocess(cell_ds, **(job.postprocess_kwargs or {}))

        artifacts.append(_write_dataset(cell_ds, task, grid_cells, cell_id=cell.id))

    return _concat_artifacts(artifacts)


def run_task(task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
    """Execute the extraction pipeline for a single task.

    Execution order:
        read -> preprocess -> reproject -> postprocess -> write

    Args:
        task: The extraction task to execute.

    Returns:
        A ``GeoDataFrame[ArtifactSchema]`` containing all extracted artifacts.

    Raises:
        ValueError: If the pipeline has no reader or if reprojection is
            requested without resolution.
    """
    job = task.job

    if job.read is None:
        raise ValueError("Pipeline must contain a Reader stage.")

    files = task.assets["href"].tolist()
    ds = job.read(files, assets=task.assets, **(job.read_kwargs or {}))

    if job.preprocess:
        ds = job.preprocess(ds, **(job.preprocess_kwargs or {}))

    grid_cells: Sequence[GridCell] = []
    if job.reproject is not None or job.write is not None:
        grid_cells = _build_grid_cells(task)

    reproject = job.reproject
    if reproject is not None:
        if job.reproject_mode == "grid":
            return _run_grid_reproject(ds, task, grid_cells)
        if job.reproject_mode == "raw":
            ds = reproject(ds, **(job.reproject_kwargs or {}))
        else:
            raise ValueError(
                "reproject is set but reproject_mode must be 'raw' or 'grid'"
            )

    if job.postprocess:
        ds = job.postprocess(ds, **(job.postprocess_kwargs or {}))

    if job.write is None:
        return ArtifactSchema.empty_geodataframe()

    return _write_dataset(ds, task, grid_cells)
