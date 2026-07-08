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
from aereo.interfaces import ExtractionTask, Processor
from aereo.spatial import get_utm_epsg_from_geometry, reproject_geom
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import box


def _resolve_aoi(task: ExtractionTask) -> Any:
    """Return the AOI geometry used to build the MajorTOM grid.

    Prefers the task-specific ``task.aoi``, then ``job.target_aoi``, and finally
    falls back to the union of task asset geometries.
    """
    if task.aoi is not None:
        return task.aoi
    job = task.job
    if job.target_aoi is not None:
        return job.target_aoi
    if "geometry" in task.assets.columns and not task.assets.geometry.isna().all():
        return task.assets.geometry.union_all()
    return None


def _build_grid_cells(task: ExtractionTask) -> Sequence[GridCell]:
    """Build raw grid cells for the task's AOI and grid parameters.

    If the task carries an explicit ``grid_cells`` list (the normal case for
    tasks produced by ``build_grouped_tasks``), those cells are returned
    directly. This avoids rediscovering neighbouring cells when the task AOI
    is a WGS84 bounding box of UTM-aligned cells.
    """
    if task.grid_cells is not None:
        return task.grid_cells

    job = task.job
    aoi = _resolve_aoi(task)
    if aoi is None:
        return []
    if job.margin:
        utm_epsg = get_utm_epsg_from_geometry(aoi)
        aoi_utm = reproject_geom(aoi, src_epsg="epsg:4326", dst_epsg=utm_epsg)
        aoi_utm = aoi_utm.buffer(job.margin)
        aoi = reproject_geom(aoi_utm, src_epsg=utm_epsg, dst_epsg="epsg:4326")
    return build_grid_cells(
        aoi=aoi,
        grid_dist=job.grid_dist,
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
        resolution=job.resolution,
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
    written = task.job.write(ds, str(path))
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


def _run_processors(
    ds: xr.Dataset,
    processors: Processor | Sequence[Processor] | None,
) -> xr.Dataset:
    """Apply a single processor or sequence of processors to a dataset."""
    if processors is None:
        return ds
    processor_list = processors if isinstance(processors, Sequence) else [processors]
    for processor in processor_list:
        ds = processor(ds)
    return ds


def _has_lonlat_coords(ds: xr.Dataset) -> bool:
    """Return True if *ds* has longitude/latitude or lons/lats coordinates."""
    return ("longitude" in ds or "lons" in ds) and ("latitude" in ds or "lats" in ds)


def _crop_dataset_to_cell(
    ds: xr.Dataset,
    cell: GridCell,
    buffer: float,
    geobox: Any | None = None,
) -> xr.Dataset:
    """Return *ds* cropped to the output GeoBox plus a degree buffer.

    Pixels outside the buffered bounds are masked and dropped. When *geobox* is
    provided, the crop region is the GeoBox extent reprojected to WGS84 and then
    buffered; otherwise the cell's WGS84 geometry is used. Using the GeoBox
    guarantees that source data extends beyond the output grid edges, which
    prevents interpolation artifacts (white/replicated border pixels) in the
    reprojected output.
    """
    if "longitude" in ds:
        lons = ds["longitude"]
        lats = ds["latitude"]
    else:
        lons = ds["lons"]
        lats = ds["lats"]

    if geobox is not None:
        from aereo.spatial import reproject_geom

        bb = geobox.boundingbox
        utm_box = box(bb.left, bb.bottom, bb.right, bb.top)
        wgs84_box = reproject_geom(
            utm_box,
            src_epsg=str(geobox.crs).lower(),
            dst_epsg="epsg:4326",
        )
        min_lon, min_lat, max_lon, max_lat = wgs84_box.buffer(buffer).bounds
    else:
        min_lon, min_lat, max_lon, max_lat = cell.cell_geometry.buffer(buffer).bounds
    mask = (lons >= min_lon) & (lons <= max_lon) & (lats >= min_lat) & (lats <= max_lat)
    return ds.where(mask, drop=True)


def _run_grid_reproject(
    ds: xr.Dataset,
    task: ExtractionTask,
    grid_cells: Sequence[GridCell],
) -> GeoDataFrame[ArtifactSchema]:
    """Run reprojection in grid mode: one file per cell.

    The full source dataset is read once, then each cell is cropped to its
    buffered WGS84 bounds before reprojection. This matches the optimised
    workflow for VIIRS-style swath data.
    """
    job = task.job
    reproject = job.reproject
    assert reproject is not None

    artifacts: list[GeoDataFrame[ArtifactSchema]] = []
    if job.resolution is None:
        raise ValueError("resolution is required when using reproject_mode='grid'.")
    for cell in grid_cells:
        geobox = cell.to_geobox(
            resolution=job.resolution,
            margin=job.grid_cells_margin,
            alignment_resolution=job.alignment_resolution,
        )
        if _has_lonlat_coords(ds):
            cell_ds = _crop_dataset_to_cell(
                ds, cell, buffer=job.crop_buffer, geobox=geobox
            )
        else:
            cell_ds = ds
        cell_ds = reproject(
            cell_ds,
            geobox=geobox,
        )

        cell_ds = _run_processors(cell_ds, job.postprocess)

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

    ds = job.read(task).compute()

    ds = _run_processors(ds, job.preprocess)

    grid_cells: Sequence[GridCell] = []
    if job.reproject is not None or job.write is not None:
        grid_cells = _build_grid_cells(task)

    reproject = job.reproject
    if reproject is not None:
        if job.reproject_mode == "grid":
            return _run_grid_reproject(ds, task, grid_cells)
        if job.reproject_mode == "raw":
            ds = reproject(ds)
        else:
            raise ValueError(
                "reproject is set but reproject_mode must be 'raw' or 'grid'"
            )

    ds = _run_processors(ds, job.postprocess)

    if job.write is None:
        return ArtifactSchema.empty_geodataframe()

    return _write_dataset(ds, task, grid_cells)
