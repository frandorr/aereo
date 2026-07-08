"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to a target geobox, CRS, or resolution.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr
from pydantic import ConfigDict, validate_call


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
    mask_invalid: bool = True,
    nprocs: int = 1,
) -> xr.Dataset:
    """Reproject a swath dataset using pyresample's nearest-neighbour resampler.

    The input dataset must contain ``lons`` and ``lats`` variables (or
    coordinates) that define the swath geometry for every pixel.

    This is the AEREO builtins equivalent of pyresample-based swath
    reprojection. It builds a ``pyresample.SwathDefinition`` from the source
    lon/lat arrays and a ``pyresample.AreaDefinition`` from the target geobox,
    then calls ``pyresample.kd_tree.resample_nearest``.

    By default, NaN and infinite source pixels are excluded from the source
    geometry so that VIIRS bow-tie gaps do not pollute the output. Set
    ``mask_invalid=False`` to get plain pyresample nearest-neighbour behaviour,
    where a target pixel whose nearest source is NaN receives NaN.

    Args:
        ds: Input swath dataset with ``lons`` and ``lats`` (or ``longitude``
            and ``latitude``).
        geobox: Target ``odc.geo.GeoBox`` (optional). Used in grid mode.
        crs: Target CRS string (optional). Used in raw mode with ``resolution``.
        resolution: Target resolution in metres (optional). Used in raw mode.
        buffer: Deprecated. Kept for backward compatibility; no longer used.
        max_distance: Maximum source-to-target distance in metres before a
            target pixel is filled with ``fill_value`` (passed as
            ``radius_of_influence`` to pyresample).
        fill_value: Value for out-of-bounds / distant pixels.
        mask_invalid: If True, exclude NaN/inf source pixels from the search.
        nprocs: Number of processor cores for pyresample (default 1).

    Returns:
        Reprojected ``xr.Dataset`` on a regular ``y``/``x`` grid.
    """
    _ = buffer  # noqa: F841
    from pyresample import AreaDefinition, SwathDefinition  # type: ignore[reportMissingTypeStubs]
    from pyresample.kd_tree import resample_nearest  # type: ignore[reportMissingTypeStubs]

    if not (
        ("lons" in ds and "lats" in ds) or ("longitude" in ds and "latitude" in ds)
    ):
        raise ValueError(
            "Input dataset must contain 'lons' and 'lats' variables or coordinates."
        )

    lons_var = "lons" if "lons" in ds else "longitude"
    lats_var = "lats" if "lats" in ds else "latitude"
    lons = _as_numpy(ds[lons_var])
    lats = _as_numpy(ds[lats_var])

    if lons.ndim != 2 or lats.ndim != 2:
        raise ValueError("reproject_swath expects 2-D 'lons' and 'lats' arrays.")

    target_geobox = _resolve_target_geobox(lons, lats, geobox, crs, resolution)
    x_coords, y_coords, target_lons, target_lats = _target_grid_from_geobox(
        target_geobox
    )

    area_def = AreaDefinition(
        area_id="aereo_pyresample_target",
        description="AEREO pyresample target grid",
        proj_id="aereo",
        projection=str(target_geobox.crs),
        width=target_geobox.shape.x,
        height=target_geobox.shape.y,
        area_extent=(
            float(target_geobox.boundingbox.left),
            float(target_geobox.boundingbox.bottom),
            float(target_geobox.boundingbox.right),
            float(target_geobox.boundingbox.top),
        ),
    )

    swath_shape = lons.shape
    target_shape = (target_geobox.shape.y, target_geobox.shape.x)
    valid_coords = np.isfinite(lons) & np.isfinite(lats)

    data_vars: dict[str, xr.DataArray] = {}
    skip_vars = {lons_var, lats_var}

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

        # pyresample expects (n_pixels, n_channels) and returns (y, x, n_channels).
        flat = arr.reshape((n_extra, -1)).T

        if mask_invalid and np.issubdtype(arr.dtype, np.floating):
            data_valid = np.isfinite(arr)
            if data_valid.ndim > 2:
                data_valid = data_valid.all(axis=tuple(range(data_valid.ndim - 2)))
            combined_valid = valid_coords & data_valid
        else:
            combined_valid = None

        if combined_valid is not None:
            if not combined_valid.any():
                # No valid pixels for this variable; emit a filled grid.
                remapped = np.full(
                    (*extra_shape, *target_shape), fill_value, dtype=arr.dtype
                )
                data_vars[var_name] = xr.DataArray(
                    remapped,
                    dims=tuple(str(d) for d in da.dims[:-2]) + ("y", "x"),
                    coords={"y": y_coords, "x": x_coords},
                    attrs=da.attrs,
                    name=var_name,
                )
                continue

            flat = flat[combined_valid.ravel(), :]
            swath_def = SwathDefinition(
                lons=lons.ravel()[combined_valid.ravel()],
                lats=lats.ravel()[combined_valid.ravel()],
            )
        else:
            swath_def = SwathDefinition(lons=lons.ravel(), lats=lats.ravel())

        resampled = resample_nearest(
            swath_def,
            flat,
            area_def,
            radius_of_influence=max_distance,
            fill_value=fill_value,
            nprocs=nprocs,
        )

        resampled_arr = np.asarray(resampled)
        remapped = np.moveaxis(resampled_arr.reshape((*target_shape, n_extra)), -1, 0)
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


# Deprecated alias kept for backward compatibility during the transition.
reproject_pyresample = reproject_swath
