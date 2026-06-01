"""Built-in write module for AEREO extraction pipelines.

Provides Hamilton nodes for writing extracted datasets as Cloud-Optimized
GeoTIFF files with EOIDS naming convention.

Registered under the ``aereo.write`` entry-point group.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd
import rioxarray  # noqa: F401
import xarray as xr
from shapely.geometry import box
from structlog import get_logger

logger = get_logger()

# Module-level variable consumed by the plugin discovery machinery.
supported_collections: tuple[str, ...] = ("*",)


def _stack_dataset(ds: xr.Dataset) -> xr.DataArray:
    """Stack all data variables of *ds* along a new ``band`` dimension.

    Args:
        ds: Source dataset.

    Returns:
        A single DataArray with a ``band`` dimension.
    """
    data_arrays = [ds[var] for var in ds.data_vars]
    return xr.concat(data_arrays, dim="band")


def _derive_temporal_bounds(task: Any) -> tuple[Any, Any]:
    """Derive start/end time from *task.assets* if available.

    Args:
        task: Extraction task.

    Returns:
        Tuple of (start_time, end_time) or (None, None).
    """
    assets = getattr(task, "assets", None)
    if assets is None or len(assets) == 0:
        return None, None

    start_time = None
    end_time = None

    if "start_time" in assets.columns:
        start_time = pd.to_datetime(assets["start_time"].iloc[0])
    if "end_time" in assets.columns:
        end_time = pd.to_datetime(assets["end_time"].iloc[0])

    return start_time, end_time


def _derive_source_ids(task: Any) -> str:
    """Derive a comma-separated source-id string from *task.assets*.

    Args:
        task: Extraction task.

    Returns:
        Comma-separated source identifiers or an empty string.
    """
    assets = getattr(task, "assets", None)
    if assets is None or len(assets) == 0:
        return ""
    if "id" in assets.columns:
        return ",".join(assets["id"].astype(str).unique())
    return ""


def _derive_collection(task: Any) -> str | None:
    """Derive collection name from *task.profile* or *task.assets*.

    Args:
        task: Extraction task.

    Returns:
        Collection identifier or ``None``.
    """
    profile = getattr(task, "profile", None)
    if profile is not None and hasattr(profile, "collections"):
        cols = profile.collections
        if cols and hasattr(cols, "keys"):
            keys = list(cols.keys())
            if keys:
                return keys[0]

    assets = getattr(task, "assets", None)
    if assets is not None and len(assets) > 0 and "collection" in assets.columns:
        return str(assets["collection"].iloc[0])

    return None


def write_cogs(
    ds: Any,
    task: Any,
    compress: str = "deflate",
    zlevel: int = 1,
) -> gpd.GeoDataFrame:
    """Write *ds* as EOIDS-compliant COG files and return artifact metadata.

    Iterates over ``task.grid_cells`` (if any), builds an EOIDS path per
    cell, and persists the dataset as a Cloud-Optimized GeoTIFF.

    When *ds* is an :class:`~xarray.Dataset` with multiple data variables,
    the variables are stacked along a ``band`` dimension so that a single
    multi-band raster is produced per cell.

    Args:
        ds: The dataset to write (typically an ``xarray.Dataset`` or
            ``xarray.DataArray``).
        task: Extraction task containing ``uri``, ``profile``, and
            ``grid_cells``.
        compress: GDAL compression algorithm (default ``"deflate"``).
        zlevel: Compression level forwarded to the GDAL driver
            (default ``1``).

    Returns:
        GeoDataFrame of written artifacts with columns matching
        :class:`~aereo.schemas.ArtifactSchema`.
    """
    from aereo.eoids import build_eoids_path

    if ds is None:
        raise ValueError("write_cogs received None dataset.")

    profile = getattr(task, "profile", None)
    uri = getattr(task, "uri", None)
    cells = getattr(task, "grid_cells", None) or []

    if uri is None:
        raise ValueError("write_cogs requires task.uri to be set.")

    if profile is None:
        raise ValueError("write_cogs requires task.profile to be set.")

    start_time, end_time = _derive_temporal_bounds(task)
    source_ids = _derive_source_ids(task)
    collection = _derive_collection(task)

    # Resolve the data array to write.
    if isinstance(ds, xr.Dataset):
        if len(ds.data_vars) == 0:
            raise ValueError("write_cogs received an empty xarray.Dataset.")
        if len(ds.data_vars) == 1:
            data_array = next(iter(ds.data_vars.values()))
        else:
            data_array = _stack_dataset(ds)
    else:
        data_array = ds

    records: list[dict[str, Any]] = []

    # When no cells are present, write once without a cell_id.
    targets = cells if cells else [None]

    for cell in targets:
        cell_id = cell.id() if cell is not None else None
        cell_geom = cell.geom if cell is not None else None

        eoids_path = build_eoids_path(
            local_dir=uri,
            profile=profile,
            cell_id=cell_id,
            start_time=start_time,
            end_time=end_time,
        )

        # Ensure parent directories exist.
        eoids_path.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "writing_cog",
            path=str(eoids_path),
            cell_id=cell_id,
            compress=compress,
            zlevel=zlevel,
        )

        data_array.rio.to_raster(
            str(eoids_path),
            compress=compress,
            zlevel=zlevel,
        )

        # Geometry — prefer cell geometry, fall back to dataset bounds.
        if cell_geom is not None:
            geometry = cell_geom
            crs = "EPSG:4326"
        else:
            try:
                bounds = data_array.rio.bounds()
                geometry = box(*bounds)
                crs = data_array.rio.crs
            except Exception:
                geometry = None
                crs = "EPSG:4326"

        artifact_id = f"{profile.name}_{cell_id or 'nocell'}_{eoids_path.stem}"

        records.append(
            {
                "id": artifact_id,
                "source_ids": source_ids,
                "start_time": start_time,
                "end_time": end_time,
                "uri": str(eoids_path),
                "geometry": geometry,
                "collection": collection,
            }
        )

    if records:
        df = pd.DataFrame(records)
        gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=crs)
    else:
        gdf = gpd.GeoDataFrame(
            columns=[
                "id",
                "source_ids",
                "start_time",
                "end_time",
                "uri",
                "geometry",
                "collection",
            ],
            geometry="geometry",
        )

    return gdf
