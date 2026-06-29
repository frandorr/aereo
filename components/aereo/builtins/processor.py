"""Built-in processor plugins for the AEREO pipeline.

This module provides data transform plugins such as band selection, QA masking,
NDVI calculation, scaling normalization, and temporal compositing.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from pydantic import ConfigDict, validate_call

_MINMAX = "minmax"
_ZSCORE = "zscore"
_DEFAULT_NORMALIZE_METHOD = _MINMAX

_MEDIAN = "median"
_MEAN = "mean"
_MAX = "max"
_MIN = "min"
_DEFAULT_COMPOSITE_METHOD = _MEDIAN


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def select_bands(ds: xr.Dataset, bands: list[str]) -> xr.Dataset:
    """Pre-reproject processor that keeps only specified data variables.

    Dropping bands before reprojection reduces the data volume that the
    expensive reproject step must process.

    Args:
        ds: Input dataset.
        bands: List of band names to keep.

    Returns:
        A new dataset containing only the requested variables.

    Raises:
        ValueError: If requested bands are not found.
    """
    keep = [str(b) for b in bands]
    missing = [b for b in keep if b not in ds.data_vars]
    if missing:
        raise ValueError(
            f"select_bands: requested bands not found in dataset: {missing}"
        )

    return ds[keep]


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def qa_mask(ds: xr.Dataset, qa_band: str, qa_mask_bits: list[int]) -> xr.Dataset:
    """Pre-reproject processor that masks cloudy/invalid pixels using a QA band.

    Pixels where the QA band matches any of the specified bit-masks are set to
    NaN in all *other* data variables. The QA band itself is dropped after
    masking.

    Args:
        ds: Input dataset containing a QA variable.
        qa_band: Name of the QA variable.
        qa_mask_bits: List of bit indices to mask.

    Returns:
        Dataset with masked pixels set to NaN. The QA band is removed.

    Raises:
        ValueError: If required params are missing or the QA band does not exist.
    """
    if qa_band not in ds.data_vars:
        raise ValueError(
            f"qa_mask: QA band '{qa_band}' not found in dataset. Available: {list(ds.data_vars)}"
        )

    qa = ds[qa_band]
    mask = np.zeros(qa.shape, dtype=bool)
    qa_arr = qa.values
    for bit in qa_mask_bits:
        mask |= ((qa_arr >> bit) & 1).astype(bool)

    masked = ds.drop_vars(qa_band)
    for var in masked.data_vars:
        masked[var] = masked[var].where(~mask)

    return masked


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def ndvi(ds: xr.Dataset, ndvi_nir_band: str, ndvi_red_band: str) -> xr.Dataset:
    """Post-reproject processor that computes the Normalised Difference Vegetation Index.

    NDVI is computed on co-registered pixels after reprojection so that the
    band math is physically correct. The source red and NIR bands are dropped
    and only the ``ndvi`` variable is retained.

    Args:
        ds: Input dataset containing red and NIR variables.
        ndvi_nir_band: Name of the NIR band.
        ndvi_red_band: Name of the red band.

    Returns:
        Dataset with a single ``ndvi`` variable. Source bands are removed.

    Raises:
        ValueError: If NIR/red bands are not found.
    """
    if ndvi_nir_band not in ds.data_vars:
        raise ValueError(
            f"ndvi: NIR band '{ndvi_nir_band}' not found. Available: {list(ds.data_vars)}"
        )
    if ndvi_red_band not in ds.data_vars:
        raise ValueError(
            f"ndvi: red band '{ndvi_red_band}' not found. Available: {list(ds.data_vars)}"
        )

    nir = ds[ndvi_nir_band]
    red = ds[ndvi_red_band]
    denom = nir + red
    ndvi_val = (nir - red) / denom
    ndvi_val = ndvi_val.where(denom != 0)

    result = ds.drop_vars([ndvi_nir_band, ndvi_red_band])
    result["ndvi"] = ndvi_val
    return result


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def normalize(
    ds: xr.Dataset, normalize_method: str = _DEFAULT_NORMALIZE_METHOD
) -> xr.Dataset:
    """Post-reproject processor that normalises pixel values per band.

    Supports min-max scaling and z-score normalisation. NaN pixels are ignored
    when computing statistics.

    Args:
        ds: Input dataset.
        normalize_method: Scaling method ('minmax' or 'zscore').

    Returns:
        Dataset with normalised variables.

    Raises:
        ValueError: If the method is unknown.
    """
    method = normalize_method

    if method not in (_MINMAX, _ZSCORE):
        raise ValueError(
            f"normalize: unknown method '{method}'. Use 'minmax' or 'zscore'."
        )

    normalized = ds.copy()
    for var in normalized.data_vars:
        da = normalized[var]
        if method == _MINMAX:
            vmin = da.min(skipna=True)
            vmax = da.max(skipna=True)
            denom = vmax - vmin
            denom = denom.where(denom != 0, 1)
            normalized[var] = (da - vmin) / denom
        else:  # _ZSCORE
            mean = da.mean(skipna=True)
            std = da.std(skipna=True)
            std = std.where(std != 0, 1)
            normalized[var] = (da - mean) / std

    return normalized


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def composite(
    ds: xr.Dataset, composite_method: str = _DEFAULT_COMPOSITE_METHOD
) -> xr.Dataset:
    """Post-reproject processor that creates a temporal composite.

    Reduces the ``time`` dimension using a statistical method (median, mean, or
    max). Useful for creating cloud-free or best-pixel composites.

    Args:
        ds: Input dataset with a ``time`` dimension.
        composite_method: Statistical compositing method ('median', 'mean', 'max', or 'min').

    Returns:
        Dataset with the ``time`` dimension reduced to a single step.

    Raises:
        ValueError: If the method is unknown or ``time`` is missing.
    """
    method = composite_method

    if "time" not in ds.dims:
        raise ValueError("composite requires a 'time' dimension in the dataset.")

    if method == _MEDIAN:
        return ds.median(dim="time", keep_attrs=True)
    if method == _MEAN:
        return ds.mean(dim="time", keep_attrs=True)
    if method == _MAX:
        return ds.max(dim="time", keep_attrs=True)
    if method == _MIN:
        return ds.min(dim="time", keep_attrs=True)

    raise ValueError(
        f"composite: unknown method '{method}'. Use '{_MEDIAN}', '{_MEAN}', '{_MAX}', or '{_MIN}'."
    )
