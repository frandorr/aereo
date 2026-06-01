"""Built-in processor functions for the AEREO Hamilton pipeline.

Each function takes an :class:`xarray.Dataset` and returns a modified
:class:`xarray.Dataset`.  They are discovered via the ``aereo.process``
entry-point group and wired into the extraction DAG by the processor
compiler.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from structlog import get_logger

logger = get_logger()

# Module-level variable consumed by plugin discovery machinery.
supported_collections: tuple[str, ...] = ("*",)


def select_bands(ds: xr.Dataset, bands: list[str] | None = None) -> xr.Dataset:
    """Keep only the specified data variables.

    Dropping bands before reprojection reduces the data volume that the
    expensive reproject step must process.

    Args:
        ds: Input dataset.
        bands: Sequence of variable names to retain.  When ``None`` the
            dataset is returned unchanged.

    Returns:
        A new dataset containing only the requested variables.

    Raises:
        ValueError: If *bands* is empty or contains variable names not
            present in *ds*.
    """
    if bands is None:
        return ds

    if not bands:
        raise ValueError(
            "select_bands requires 'bands' to be a non-empty list of variable names."
        )

    keep = [str(b) for b in bands]
    missing = [b for b in keep if b not in ds.data_vars]
    if missing:
        raise ValueError(
            f"select_bands: requested bands not found in dataset: {missing}"
        )

    return ds[keep]


def mask_clouds(
    ds: xr.Dataset,
    qa_band: str | None = None,
    qa_mask_bits: list[int] | None = None,
) -> xr.Dataset:
    """Mask cloudy/invalid pixels using a QA band.

    Pixels where the QA band matches any of the specified bit-masks are
    set to NaN in all *other* data variables.  The QA band itself is
    dropped after masking.

    Args:
        ds: Input dataset containing a QA variable.
        qa_band: Name of the QA variable in *ds*.
        qa_mask_bits: Bit positions to mask.  A pixel is masked if
            ``(qa_value >> bit) & 1`` is 1 for *any* listed bit.

    Returns:
        Dataset with masked pixels set to NaN.  The QA band is removed.

    Raises:
        ValueError: If required parameters are missing or the QA band
            does not exist.
    """
    if qa_band is None or qa_mask_bits is None:
        raise ValueError(
            "mask_clouds requires 'qa_band' and 'qa_mask_bits' parameters."
        )

    if qa_band not in ds.data_vars:
        raise ValueError(
            f"mask_clouds: QA band '{qa_band}' not found in dataset. "
            f"Available: {list(ds.data_vars)}"
        )

    qa = ds[qa_band]
    mask = np.zeros(qa.shape, dtype=bool)
    for bit in qa_mask_bits:
        mask |= ((qa.values >> bit) & 1).astype(bool)

    masked = ds.drop_vars(qa_band)
    for var in masked.data_vars:
        masked[var] = masked[var].where(~mask)

    return masked


def compute_ndvi(
    ds: xr.Dataset,
    nir_band: str = "nir",
    red_band: str = "red",
) -> xr.Dataset:
    """Compute the Normalised Difference Vegetation Index.

    NDVI is computed on co-registered pixels after reprojection so that
    the band math is physically correct.  The source red and NIR bands
    are dropped and only the ``ndvi`` variable is retained.

    Args:
        ds: Input dataset containing red and NIR variables.
        nir_band: Name of the NIR variable.
        red_band: Name of the red variable.

    Returns:
        Dataset with a single ``ndvi`` variable.  Source bands are
        removed.

    Raises:
        ValueError: If required bands are not found.
    """
    if nir_band not in ds.data_vars:
        raise ValueError(
            f"compute_ndvi: NIR band '{nir_band}' not found. "
            f"Available: {list(ds.data_vars)}"
        )
    if red_band not in ds.data_vars:
        raise ValueError(
            f"compute_ndvi: red band '{red_band}' not found. "
            f"Available: {list(ds.data_vars)}"
        )

    nir = ds[nir_band]
    red = ds[red_band]
    ndvi = (nir - red) / (nir + red)
    ndvi = ndvi.where((nir + red) != 0)

    result = ds.drop_vars([nir_band, red_band])
    result["ndvi"] = ndvi
    return result


def compute_ndwi(
    ds: xr.Dataset,
    nir_band: str = "nir",
    swir_band: str = "swir",
) -> xr.Dataset:
    """Compute the Normalised Difference Water Index.

    NDWI = (NIR - SWIR) / (NIR + SWIR).  The source bands are dropped
    and only the ``ndwi`` variable is retained.

    Args:
        ds: Input dataset containing NIR and SWIR variables.
        nir_band: Name of the NIR variable.
        swir_band: Name of the SWIR variable.

    Returns:
        Dataset with a single ``ndwi`` variable.

    Raises:
        ValueError: If required bands are not found.
    """
    if nir_band not in ds.data_vars:
        raise ValueError(
            f"compute_ndwi: NIR band '{nir_band}' not found. "
            f"Available: {list(ds.data_vars)}"
        )
    if swir_band not in ds.data_vars:
        raise ValueError(
            f"compute_ndwi: SWIR band '{swir_band}' not found. "
            f"Available: {list(ds.data_vars)}"
        )

    nir = ds[nir_band]
    swir = ds[swir_band]
    ndwi = (nir - swir) / (nir + swir)
    ndwi = ndwi.where((nir + swir) != 0)

    result = ds.drop_vars([nir_band, swir_band])
    result["ndwi"] = ndwi
    return result


def normalize(
    ds: xr.Dataset,
    method: str = "minmax",
) -> xr.Dataset:
    """Normalise pixel values per band.

    Supports min-max scaling and z-score normalisation.  NaN pixels are
    ignored when computing statistics.

    Args:
        ds: Input dataset.
        method: Either ``"minmax"`` or ``"zscore"``.

    Returns:
        Dataset with normalised variables.

    Raises:
        ValueError: If the method is unknown.
    """
    if method not in ("minmax", "zscore"):
        raise ValueError(
            f"normalize: unknown method '{method}'. Use 'minmax' or 'zscore'."
        )

    normalized = ds.copy()
    for var in normalized.data_vars:
        da = normalized[var]
        if method == "minmax":
            vmin = da.min(skipna=True)
            vmax = da.max(skipna=True)
            denom = vmax - vmin
            denom = denom.where(denom != 0, 1)
            normalized[var] = (da - vmin) / denom
        else:  # zscore
            mean = da.mean(skipna=True)
            std = da.std(skipna=True)
            std = std.where(std != 0, 1)
            normalized[var] = (da - mean) / std

    return normalized


def composite(
    ds: xr.Dataset,
    method: str = "median",
) -> xr.Dataset:
    """Create a temporal composite by reducing the ``time`` dimension.

    Useful for creating cloud-free or best-pixel composites.

    Args:
        ds: Input dataset with a ``time`` dimension.
        method: One of ``"median"``, ``"mean"``, ``"max"``, ``"min"``.

    Returns:
        Dataset with the ``time`` dimension reduced to a single step.

    Raises:
        ValueError: If the method is unknown or ``time`` is missing.
    """
    if "time" not in ds.dims:
        raise ValueError("composite requires a 'time' dimension in the dataset.")

    if method == "median":
        return ds.median(dim="time", keep_attrs=True)
    if method == "mean":
        return ds.mean(dim="time", keep_attrs=True)
    if method == "max":
        return ds.max(dim="time", keep_attrs=True)
    if method == "min":
        return ds.min(dim="time", keep_attrs=True)

    raise ValueError(
        f"composite: unknown method '{method}'. Use 'median', 'mean', 'max', or 'min'."
    )
