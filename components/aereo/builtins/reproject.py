"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to a target geobox, CRS, or resolution.
"""

from __future__ import annotations

import hashlib
import weakref
from functools import lru_cache
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


def _array_hash(arr: np.ndarray) -> str:
    """Return a stable hash string for a numpy array.

    Uses SHA-1 over the array buffer; this avoids copying the array to bytes and
    is fast enough to use as a cache key for large swath coordinate arrays.
    """
    return hashlib.sha1(arr).hexdigest()


class _SwathKey:
    """Hashable, equality-comparable key for caching a swath KDTree.

    Holds weak references to the source arrays so the cache does not keep the
    original lons/lats alive once the caller drops them. The KDTree itself
    retains the ECEF points it needs.

    An optional boolean *mask* can be included in the key so that a separate
    tree is built for data variables with different valid-pixel patterns
    (e.g. VIIRS bow-tie NaNs). Variables that share the same mask reuse the
    same cached tree.
    """

    __slots__ = (
        "lons_hash",
        "lats_hash",
        "mask_hash",
        "_lons_ref",
        "_lats_ref",
        "_mask_ref",
        "_hash",
    )

    def __init__(
        self,
        lons: np.ndarray,
        lats: np.ndarray,
        mask: np.ndarray | None = None,
    ) -> None:
        self.lons_hash = _array_hash(lons)
        self.lats_hash = _array_hash(lats)
        self.mask_hash = _array_hash(mask) if mask is not None else ""
        self._lons_ref = weakref.ref(lons)
        self._lats_ref = weakref.ref(lats)
        self._mask_ref = weakref.ref(mask) if mask is not None else None
        self._hash = hash((self.lons_hash, self.lats_hash, self.mask_hash))

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _SwathKey):
            return NotImplemented
        return (self.lons_hash, self.lats_hash, self.mask_hash) == (
            other.lons_hash,
            other.lats_hash,
            other.mask_hash,
        )

    def resolve(self) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """Return the source arrays and mask, raising if they were collected."""
        lons = self._lons_ref()
        lats = self._lats_ref()
        mask = self._mask_ref() if self._mask_ref is not None else None
        if (
            lons is None
            or lats is None
            or (self._mask_ref is not None and mask is None)
        ):
            raise RuntimeError("Swath coordinate arrays were garbage collected")
        return lons, lats, mask


@lru_cache(maxsize=8)
def _build_cached_swath_kdtree(key: _SwathKey) -> Any:
    """Build a pykdtree KDTree on the valid pixels of a full swath.

    When the key contains a boolean *mask*, only pixels where the mask is True
    are inserted into the tree. This lets us exclude NaN data pixels (e.g.
    VIIRS bow-tie gaps) from the nearest-neighbour search, matching the
    behaviour of pyresample's nearest-neighbour resampler.

    ``functools.lru_cache`` provides the thread-safe cache and guarantees that
    concurrent callers with the same key wait for a single build instead of
    duplicating work.
    """
    import pykdtree.kdtree

    lons, lats, mask = key.resolve()
    valid = np.isfinite(lons) & np.isfinite(lats)
    if mask is not None:
        valid = valid & mask
    if not valid.any():
        raise ValueError("No valid swath pixels available for KDTree construction.")
    swath_xyz = _lonlat_to_xyz(lons[valid], lats[valid])
    return pykdtree.kdtree.KDTree(swath_xyz)


def _get_cached_swath_kdtree(
    lons: np.ndarray,
    lats: np.ndarray,
    mask: np.ndarray | None = None,
) -> Any:
    """Return a cached KDTree for the given swath coordinates, building if needed."""
    key = _SwathKey(lons, lats, mask)
    return _build_cached_swath_kdtree(key)


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
    """Reproject a swath dataset using a pykdtree nearest-neighbour search.

    The input dataset must contain ``lons`` and ``lats`` variables (or
    coordinates) that define the swath geometry for every pixel.

    This is the AEREO builtins equivalent of the manual pykdtree reprojection
    shown in ``examples/viirs_pykdtree_reproject.py``:

    1. Build a ``pykdtree.KDTree`` on the valid swath pixels in ECEF space.
       Pixels whose data value is NaN are excluded from the tree, so a target
       pixel maps to the nearest *valid* source pixel rather than the nearest
       NaN. This matches the behaviour of pyresample's nearest-neighbour
       resampler and avoids propagating VIIRS bow-tie gaps into the output.
    2. Query the tree with target grid points to obtain nearest neighbours.
    3. Remap each data variable and mask distant matches.

    The KDTree is cached in a process-level cache keyed by a hash of the swath
    ``lons``/``lats`` arrays and the per-variable valid-data mask. Variables
    that share the same mask reuse the same tree, so the same swath reused
    across multiple ``ExtractionTask`` objects only pays the tree construction
    cost once per unique mask.

    Args:
        ds: Input swath dataset with ``lons`` and ``lats``.
        geobox: Target ``odc.geo.GeoBox`` (optional). Used in grid mode.
        crs: Target CRS string (optional). Used in raw mode with ``resolution``.
        resolution: Target resolution in metres (optional). Used in raw mode.
        buffer: Deprecated. Kept for backward compatibility; no longer used
            because the tree is built on the full swath and cached.
        max_distance: Maximum swath-to-target distance in metres before a
            target pixel is filled with ``fill_value``.
        fill_value: Value for out-of-bounds / distant pixels.

    Returns:
        Reprojected ``xr.Dataset`` on a regular ``y``/``x`` grid.
    """
    _ = buffer  # noqa: F841

    # check if lons or longitudes and lats or latitudes exist in the dataset
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

    valid = np.isfinite(lons) & np.isfinite(lats)
    target_xyz = _lonlat_to_xyz(target_lons.ravel(), target_lats.ravel())

    swath_shape = lons.shape
    target_shape = target_lons.shape

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

        # Exclude NaN data pixels from the NN search so bow-tie gaps do not
        # pollute the output. Integer arrays are treated as fully valid.
        extra_shape = arr.shape[:-2]

        if np.issubdtype(arr.dtype, np.floating):
            data_valid = np.isfinite(arr)
        else:
            data_valid = np.ones(arr.shape, dtype=bool)
        # Reduce any leading dimensions to a single 2-D spatial mask. If a
        # spatial pixel is invalid in any extra dimension, it is excluded from
        # the tree for this variable.
        if data_valid.ndim > 2:
            data_valid = data_valid.all(axis=tuple(range(data_valid.ndim - 2)))
        combined_valid = valid & data_valid

        if not combined_valid.any():
            # No valid data pixels for this variable in the cropped region.
            # Emit a filled output grid rather than skipping the variable, so
            # that grid cells which only contain bow-tie gaps do not abort the
            # whole reprojection.
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

        tree = _get_cached_swath_kdtree(lons, lats, combined_valid)
        distances, indices = tree.query(target_xyz, k=1, sqr_dists=True)
        distance_mask = distances.reshape(target_shape) > (max_distance**2)

        n_extra = int(np.prod(extra_shape, dtype=np.int64)) if extra_shape else 1
        flat = arr.reshape((n_extra, *swath_shape))
        valid_values = flat[..., combined_valid]

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


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def reproject_pyresample(
    ds: xr.Dataset,
    geobox: Any | None = None,
    crs: str | None = None,
    resolution: float | None = None,
    max_distance: float = 3_000.0,
    fill_value: Any = np.nan,
    mask_invalid: bool = True,
    nprocs: int = 1,
) -> xr.Dataset:
    """Reproject a swath dataset using pyresample's nearest-neighbour resampler.

    This is a reference implementation intended for benchmarking and comparison
    with ``reproject_swath``. It builds a ``pyresample.SwathDefinition`` from
    the source lon/lat arrays and a ``pyresample.AreaDefinition`` from the
    target geobox, then calls ``pyresample.kd_tree.resample_nearest``.

    By default, NaN and infinite source pixels are masked before resampling so
    that bow-tie gaps do not pollute the output. This matches the behaviour of
    ``reproject_swath``. Set ``mask_invalid=False`` to get plain pyresample
    nearest-neighbour behaviour, where a target pixel whose nearest source is
    NaN receives NaN.

    Args:
        ds: Input swath dataset with ``lons`` and ``lats`` (or ``longitude``
            and ``latitude``).
        geobox: Target ``odc.geo.GeoBox`` (optional). Used in grid mode.
        crs: Target CRS string (optional). Used in raw mode with ``resolution``.
        resolution: Target resolution in metres (optional). Used in raw mode.
        max_distance: Maximum source-to-target distance in metres before a
            target pixel is filled with ``fill_value`` (passed as
            ``radius_of_influence`` to pyresample).
        fill_value: Value for out-of-bounds / distant pixels.
        mask_invalid: If True, mask NaN/inf source pixels before resampling.
        nprocs: Number of processor cores for pyresample (default 1).

    Returns:
        Reprojected ``xr.Dataset`` on a regular ``y``/``x`` grid.
    """
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
        raise ValueError("reproject_pyresample expects 2-D 'lons' and 'lats' arrays.")

    target_geobox = _resolve_target_geobox(lons, lats, geobox, crs, resolution)
    x_coords, y_coords, target_lons, target_lats = _target_grid_from_geobox(
        target_geobox
    )

    swath_def = SwathDefinition(lons=lons.ravel(), lats=lats.ravel())
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
            flat = np.ma.masked_invalid(flat)

        resampled = resample_nearest(
            swath_def,
            flat,
            area_def,
            radius_of_influence=max_distance,
            fill_value=fill_value,
            nprocs=nprocs,
        )

        resampled_arr = np.ma.filled(resampled, fill_value=fill_value)
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
