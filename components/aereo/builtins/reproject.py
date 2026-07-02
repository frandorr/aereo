"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to a target geobox, CRS, or resolution.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr
from pydantic import ConfigDict, validate_call


_R_EARTH: float = 6_371_000.0


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def reproject_odc(
    ds: xr.Dataset,
    geobox: Any | None = None,
    crs: str | None = None,
    resolution: float | None = None,
    resampling: str = "nearest",
    fill_value: Any = None,
    dtype: Any = None,
) -> xr.Dataset:
    """Reproject *ds* using ``odc.geo.xr.reproject``.

    Exactly one of *geobox* or both *crs* and *resolution* should be provided.
    When *geobox* is supplied (the normal case in ``reproject_mode="grid"``),
    the dataset is warped to that geobox. Otherwise it is warped to the
    requested CRS and resolution using the dataset's own extent.

    Args:
        ds: Input dataset.
        geobox: Target ``odc.geo.GeoBox`` (optional).
        crs: Target CRS string (optional).
        resolution: Target resolution in metres (optional).
        resampling: Resampling method (e.g. 'nearest', 'bilinear').
        fill_value: Optional fill value for out-of-bounds pixels.
        dtype: Optional output dtype.

    Returns:
        Reprojected ``xr.Dataset``.
    """
    from odc.geo.geobox import GeoBox  # type: ignore[reportMissingTypeStubs]
    from odc.geo.xr import xr_reproject  # type: ignore[reportAttributeAccessIssue]

    kwargs: dict[str, Any] = {"resampling": resampling}
    if fill_value is not None:
        kwargs["fill_value"] = fill_value
    if dtype is not None:
        kwargs["dtype"] = dtype

    if geobox is not None:
        return xr_reproject(ds, geobox, **kwargs)

    if crs is None or resolution is None:
        raise ValueError(
            "reproject_odc requires either 'geobox' or both 'crs' and 'resolution'."
        )

    target_geobox = GeoBox.from_bbox(
        ds.rio.bounds(),
        crs=crs,
        resolution=resolution,
    )
    return xr_reproject(ds, target_geobox, **kwargs)


def _as_numpy(da: xr.DataArray) -> np.ndarray:
    """Return a dense numpy array from an xarray DataArray."""
    if da.chunks is not None:
        return np.asarray(da.compute().values)
    return np.asarray(da.values)


def _lonlat_to_xyz(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Convert geographic coordinates to ECEF cartesian coordinates (float32)."""
    lon_rad = np.deg2rad(lon)
    lat_rad = np.deg2rad(lat)
    x = _R_EARTH * np.cos(lat_rad) * np.cos(lon_rad)
    y = _R_EARTH * np.cos(lat_rad) * np.sin(lon_rad)
    z = _R_EARTH * np.sin(lat_rad)
    return np.column_stack((x, y, z)).astype(np.float32)


def _swath_bounds(
    lons: np.ndarray,
    lats: np.ndarray,
) -> tuple[float, float, float, float]:
    """Return the WGS84 bounding box of finite swath coordinates."""
    valid = np.isfinite(lons) & np.isfinite(lats)
    if not valid.any():
        raise ValueError("No valid lons/lats found.")
    return (
        float(lons[valid].min()),
        float(lats[valid].min()),
        float(lons[valid].max()),
        float(lats[valid].max()),
    )


def _crop_swath(
    lons: np.ndarray,
    lats: np.ndarray,
    bounds: tuple[float, float, float, float],
    buffer: float,
) -> tuple[np.ndarray, np.ndarray, slice, slice]:
    """Crop swath lons/lats to a bounding rectangle covering *bounds* + *buffer*.

    Returns the cropped arrays plus the row/column slices so matching data
    arrays can be cropped the same way.
    """
    min_lon, min_lat, max_lon, max_lat = bounds
    mask = (
        np.isfinite(lons)
        & np.isfinite(lats)
        & (lons >= min_lon - buffer)
        & (lons <= max_lon + buffer)
        & (lats >= min_lat - buffer)
        & (lats <= max_lat + buffer)
    )
    rows, cols = np.where(mask)
    if rows.size == 0 or cols.size == 0:
        raise ValueError("No swath pixels overlap the target bounds.")
    row_slice = slice(int(rows.min()), int(rows.max()) + 1)
    col_slice = slice(int(cols.min()), int(cols.max()) + 1)
    return lons[row_slice, col_slice], lats[row_slice, col_slice], row_slice, col_slice


def _target_grid_from_geobox(
    geobox: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return target x coords, y coords, and the corresponding lon/lat grids."""
    import pyproj

    keys = list(geobox.coordinates.keys())
    if "x" in keys and "y" in keys:
        x_coords = np.asarray(geobox.coordinates["x"].values)
        y_coords = np.asarray(geobox.coordinates["y"].values)
    elif "longitude" in keys and "latitude" in keys:
        x_coords = np.asarray(geobox.coordinates["longitude"].values)
        y_coords = np.asarray(geobox.coordinates["latitude"].values)
    else:
        raise ValueError(f"Unsupported geobox coordinate names: {keys}")

    xx, yy = np.meshgrid(x_coords, y_coords)
    transformer = pyproj.Transformer.from_crs(geobox.crs, "EPSG:4326", always_xy=True)
    target_lons, target_lats = transformer.transform(xx, yy)
    return x_coords, y_coords, target_lons, target_lats


def _resolve_target_geobox(
    lons: np.ndarray,
    lats: np.ndarray,
    geobox: Any | None,
    crs: str | None,
    resolution: float | None,
) -> Any:
    """Return the target geobox, building one from swath bounds when needed."""
    from odc.geo.geobox import GeoBox
    import pyproj

    if geobox is not None:
        return geobox

    if crs is None or resolution is None:
        raise ValueError(
            "reproject_swath requires either 'geobox' or both 'crs' and 'resolution'."
        )

    min_lon, min_lat, max_lon, max_lat = _swath_bounds(lons, lats)
    target_crs = pyproj.CRS.from_user_input(crs)
    transformer = pyproj.Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    x_min, y_min, x_max, y_max = transformer.transform_bounds(
        min_lon, min_lat, max_lon, max_lat
    )
    return GeoBox.from_bbox(
        (x_min, y_min, x_max, y_max),
        crs=target_crs,
        resolution=resolution,
    )


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def reproject_swath(
    ds: xr.Dataset,
    geobox: Any | None = None,
    crs: str | None = None,
    resolution: float | None = None,
    buffer: float = 0.05,
    max_distance: float = 3_000.0,
    fill_value: Any = np.nan,
) -> xr.Dataset:
    """Reproject a swath dataset using a cropped pykdtree nearest-neighbour search.

    The input dataset must contain ``lons`` and ``lats`` variables (or
    coordinates) that define the swath geometry for every pixel.

    This is the AEREO builtins equivalent of the manual pykdtree reprojection
    shown in ``examples/viirs_pykdtree_reproject.py``:

    1. Crop the swath to the target bounds plus a small buffer.
    2. Build a ``pykdtree.KDTree`` on the cropped swath in ECEF space.
    3. Query the tree with target grid points to obtain nearest neighbours.
    4. Remap each data variable and mask distant matches.

    Args:
        ds: Input swath dataset with ``lons`` and ``lats``.
        geobox: Target ``odc.geo.GeoBox`` (optional). Used in grid mode.
        crs: Target CRS string (optional). Used in raw mode with ``resolution``.
        resolution: Target resolution in metres (optional). Used in raw mode.
        buffer: Degrees of padding around the target bounds when cropping the
            swath before building the KDTree.
        max_distance: Maximum swath-to-target distance in metres before a
            target pixel is filled with ``fill_value``.
        fill_value: Value for out-of-bounds / distant pixels.

    Returns:
        Reprojected ``xr.Dataset`` on a regular ``y``/``x`` grid.
    """
    import pykdtree.kdtree

    if "lons" not in ds or "lats" not in ds:
        raise ValueError("reproject_swath requires 'lons' and 'lats' in the dataset.")

    lons = _as_numpy(ds["lons"])
    lats = _as_numpy(ds["lats"])
    if lons.ndim != 2 or lats.ndim != 2:
        raise ValueError("reproject_swath expects 2-D 'lons' and 'lats' arrays.")

    target_geobox = _resolve_target_geobox(lons, lats, geobox, crs, resolution)
    x_coords, y_coords, target_lons, target_lats = _target_grid_from_geobox(
        target_geobox
    )

    target_bounds = (
        float(np.nanmin(target_lons)),
        float(np.nanmin(target_lats)),
        float(np.nanmax(target_lons)),
        float(np.nanmax(target_lats)),
    )
    lons_crop, lats_crop, row_slice, col_slice = _crop_swath(
        lons, lats, bounds=target_bounds, buffer=buffer
    )

    valid = np.isfinite(lons_crop) & np.isfinite(lats_crop)
    swath_xyz = _lonlat_to_xyz(lons_crop[valid], lats_crop[valid])
    target_xyz = _lonlat_to_xyz(target_lons.ravel(), target_lats.ravel())

    tree = pykdtree.kdtree.KDTree(swath_xyz)
    distances, indices = tree.query(target_xyz, k=1, sqr_dists=True)

    swath_shape = lons.shape
    target_shape = target_lons.shape
    distance_mask = distances.reshape(target_shape) > (max_distance**2)

    data_vars: dict[str, xr.DataArray] = {}
    skip_vars = {"lons", "lats"}

    for name, da in ds.data_vars.items():
        var_name = str(name)
        if var_name in skip_vars:
            continue
        if da.shape[-2:] != swath_shape:
            continue

        arr = _as_numpy(da)
        if np.isnan(fill_value) and not np.issubdtype(arr.dtype, np.floating):
            arr = arr.astype(np.float64)

        extra_shape = arr.shape[:-2]
        n_extra = int(np.prod(extra_shape, dtype=np.int64)) if extra_shape else 1
        flat = arr.reshape((n_extra, *swath_shape))
        flat_crop = flat[..., row_slice, col_slice]
        valid_values = flat_crop[..., valid]

        remapped = np.full((n_extra, *target_shape), fill_value, dtype=arr.dtype)
        remapped_flat = remapped.reshape((n_extra, -1))
        remapped_flat[:, :] = valid_values[..., indices]
        if max_distance is not None and max_distance > 0:
            remapped_flat[:, distance_mask.ravel()] = fill_value
        remapped = remapped_flat.reshape((n_extra, *target_shape))
        remapped = remapped.reshape((*extra_shape, *target_shape))

        data_vars[var_name] = xr.DataArray(
            remapped,
            dims=tuple(str(d) for d in da.dims[:-2]) + ("y", "x"),
            coords={"y": y_coords, "x": x_coords},
            attrs=da.attrs,
            name=var_name,
        )

    if not data_vars:
        raise ValueError("No data variables found matching the swath shape.")

    out = xr.Dataset(data_vars, attrs=ds.attrs)
    out = out.rio.write_crs(str(target_geobox.crs))
    if fill_value is not None and not (
        isinstance(fill_value, float) and np.isnan(fill_value)
    ):
        for name in out.data_vars:
            out[str(name)].rio.write_nodata(fill_value, inplace=True)
    return out
