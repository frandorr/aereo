"""Core per-task extraction pipeline execution.

Defines :func:`run_task`, the plain per-task pipeline that executes
read -> [preprocess] -> [reproject] -> [postprocess] -> write.
"""

from __future__ import annotations

import functools
import inspect
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, cast

import geopandas as gpd
import numpy as np
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
from structlog import get_logger

logger = get_logger()

UTM_SENTINEL = "utm"


def _raw_reproject_crs(reproject: Any) -> str | None:
    """Return the CRS configured on a raw-mode reproject callable.

    Returns the ``crs`` keyword baked into the callable when it is an
    introspectable ``functools.partial`` (the shape Hydra ``_partial_: true``
    produces). Returns ``None`` when no ``crs`` is bound or the callable
    cannot be introspected.
    """
    if isinstance(reproject, functools.partial):
        crs = reproject.keywords.get("crs")
        return str(crs) if crs is not None else None
    return None


def _callable_accepts_crs(reproject: Any) -> bool:
    """Return True if the callable accepts a ``crs`` keyword argument."""
    try:
        sig = inspect.signature(reproject)
    except (ValueError, TypeError):
        return False
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if param.name == "crs":
            return True
    return False


def _infer_utm_crs(ds: xr.Dataset, task: ExtractionTask) -> str:
    """Infer a UTM EPSG code from the dataset footprint or task AOI.

    The footprint is derived, in priority order, from:

    1. ``ds.rio.bounds()`` for regular gridded datasets, reprojected to WGS84
       when the dataset's native CRS is not already EPSG:4326.
    2. The finite min/max of ``lons``/``lats`` (or ``longitude``/``latitude``)
       variables for swath datasets.
    3. The task AOI from :func:`_resolve_aoi`.

    A footprint wider than 6° of longitude logs a warning because a single UTM
    zone is unlikely to be appropriate. Polar or otherwise undeterminable
    footprints raise an actionable :class:`ValueError`.
    """
    geom = None
    if hasattr(ds, "rio"):
        try:
            crs = ds.rio.crs
            if crs is not None:
                bounds = ds.rio.bounds()
                src_crs = str(crs).lower()
                geom = box(*bounds)
                if src_crs != "epsg:4326":
                    geom = reproject_geom(geom, src_epsg=src_crs, dst_epsg="epsg:4326")
        except Exception:
            pass

    if geom is None:
        if ("longitude" in ds and "latitude" in ds) or ("lons" in ds and "lats" in ds):
            lons_var = "longitude" if "longitude" in ds else "lons"
            lats_var = "latitude" if "latitude" in ds else "lats"
            lons = ds[lons_var].values
            lats = ds[lats_var].values
            valid = np.isfinite(lons) & np.isfinite(lats)
            if valid.any():
                geom = box(
                    float(lons[valid].min()),
                    float(lats[valid].min()),
                    float(lons[valid].max()),
                    float(lats[valid].max()),
                )

    if geom is None:
        aoi = _resolve_aoi(task)
        if aoi is not None:
            geom = aoi

    if geom is None:
        raise ValueError(
            "cannot infer a UTM CRS for this dataset footprint; configure an explicit "
            "`crs` in the reproject config or use reproject_mode='grid'"
        )

    min_lon, _min_lat, max_lon, _max_lat = geom.bounds
    if max_lon - min_lon > 6:
        logger.warning(
            "raw_reproject_wide_footprint",
            min_lon=min_lon,
            max_lon=max_lon,
            span=max_lon - min_lon,
            message=(
                "The dataset footprint spans multiple UTM zones; an explicit CRS or "
                "reproject_mode='grid' may give better results."
            ),
        )

    try:
        epsg = get_utm_epsg_from_geometry(geom)
    except Exception as exc:
        raise ValueError(
            "cannot infer a UTM CRS for this dataset footprint; configure an explicit "
            "`crs` in the reproject config or use reproject_mode='grid'"
        ) from exc

    logger.info("raw_reproject_inferred_crs", crs=epsg)
    return epsg


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
    slice_time: datetime | None = None,
) -> Path:
    """Build the EOIDS output path for a dataset slice.

    When ``slice_time`` is given (a single timestep of a multi-time dataset),
    it replaces the task-level time bounds so each timestep slice gets a
    unique path instead of overwriting the same file.
    """
    job = task.job
    if slice_time is not None:
        start_time: datetime | None = slice_time
        end_time: datetime | None = slice_time
    else:
        start_time, end_time = _derive_time_bounds(task)
    collections = None
    if "collection" in task.assets.columns:
        collections = [
            str(c) for c in task.assets["collection"].dropna().unique().tolist()
        ]

    return build_eoids_path(
        local_dir=job.output_uri,
        job_name=job.name,
        resolution=job.grid_resolution,
        collections=collections,
        cell_id=cell_id,
        start_time=start_time,
        end_time=end_time,
        suffix="tif",
    )


def _write_single_timestep(
    ds: xr.Dataset,
    task: ExtractionTask,
    cell_id: str | None = None,
    slice_time: datetime | None = None,
) -> str:
    """Write a single time-slice dataset and return the written path."""
    path = _build_output_path(ds, task, cell_id=cell_id, slice_time=slice_time)
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
    slice_time: datetime | None = None,
) -> GeoDataFrame[ArtifactSchema]:
    """Build ArtifactSchema rows for a written file.

    If *cell_id* is provided (grid mode), emit a single row for that cell.
    Otherwise intersect the file footprint with the grid and emit one row per
    intersecting cell. When *slice_time* is given (a timestep of a multi-time
    dataset), the artifact bounds are that timestep instead of the task-level
    asset window.
    """
    bounds, file_crs = _read_written_footprint(path)
    source_ids = _derive_source_ids(task)
    if slice_time is not None:
        start_time: datetime | None = slice_time
        end_time: datetime | None = slice_time
    else:
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
    """Write a dataset (splitting time if needed) and build artifact rows.

    Each timestep slice is written to its own path (named after the slice
    timestamp) and catalogued with that timestamp as its time bounds.
    """
    if "time" in ds.dims:
        artifacts: list[GeoDataFrame[ArtifactSchema]] = []
        for t in ds.time.values:
            slice_ds = ds.sel(time=t).drop_vars("time", errors="ignore")
            slice_time = pd.Timestamp(t).to_pydatetime()
            path = _write_single_timestep(slice_ds, task, cell_id=cell_id, slice_time=slice_time)
            artifacts.append(
                _artifact_rows(path, task, grid_cells, cell_id=cell_id, slice_time=slice_time)
            )
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
    if job.grid_resolution is None:
        raise ValueError("grid_resolution is required when using reproject_mode='grid'.")
    for cell in grid_cells:
        geobox = cell.to_geobox(
            resolution=job.grid_resolution,
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
            requested without grid_resolution.
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
            configured_crs = _raw_reproject_crs(reproject)
            if configured_crs == UTM_SENTINEL:
                inferred = _infer_utm_crs(ds, task)
                ds = reproject(ds, crs=inferred)
            elif configured_crs is None and not _callable_accepts_crs(reproject):
                raise ValueError(
                    "reproject_mode='raw' requires a 'crs' in the reproject "
                    "config: an explicit CRS (e.g. 'epsg:32720'), 'utm' to infer "
                    "the UTM zone from the data, or use reproject_mode='grid' "
                    "which infers UTM per grid cell."
                )
            else:
                ds = reproject(ds)
        else:
            raise ValueError(
                "reproject is set but reproject_mode must be 'raw' or 'grid'"
            )

    ds = _run_processors(ds, job.postprocess)

    if job.write is None:
        return ArtifactSchema.empty_geodataframe()

    return _write_dataset(ds, task, grid_cells)
