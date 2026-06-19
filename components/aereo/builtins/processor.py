"""Built-in processor plugins for the AEREO pipeline.

This module provides data transform plugins such as band selection, QA masking,
NDVI calculation, scaling normalization, and temporal compositing.
"""

from __future__ import annotations


import numpy as np
import xarray as xr

from aereo.interfaces import Processor

_MINMAX = "minmax"
_ZSCORE = "zscore"
_DEFAULT_NORMALIZE_METHOD = _MINMAX

_MEDIAN = "median"
_MEAN = "mean"
_MAX = "max"
_MIN = "min"
_DEFAULT_COMPOSITE_METHOD = _MEDIAN


class SelectBands(Processor):
    """Pre-reproject processor that keeps only specified data variables.

    Dropping bands before reprojection reduces the data volume that the
    expensive reproject step must process.
    """

    bands: list[str]

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Keep only the bands listed in *bands*.

        Args:
            ds: Input dataset.

        Returns:
            A new dataset containing only the requested variables.

        Raises:
            ValueError: If requested bands are not found.
        """
        keep = [str(b) for b in self.bands]
        missing = [b for b in keep if b not in ds.data_vars]
        if missing:
            raise ValueError(
                f"SelectBands: requested bands not found in dataset: {missing}"
            )

        return ds[keep]


class QAMask(Processor):
    """Pre-reproject processor that masks cloudy/invalid pixels using a QA band.

    Pixels where the QA band matches any of the specified bit-masks are set to
    NaN in all *other* data variables.  The QA band itself is dropped after
    masking.
    """

    qa_band: str
    qa_mask_bits: list[int]

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Apply QA-based masking.

        Args:
            ds: Input dataset containing a QA variable.

        Returns:
            Dataset with masked pixels set to NaN.  The QA band is removed.

        Raises:
            ValueError: If required params are missing or the QA band does not exist.
        """
        if self.qa_band not in ds.data_vars:
            raise ValueError(
                f"QAMask: QA band '{self.qa_band}' not found in dataset. Available: {list(ds.data_vars)}"
            )

        qa = ds[self.qa_band]
        mask = np.zeros(qa.shape, dtype=bool)
        qa_arr = qa.values
        for bit in self.qa_mask_bits:
            mask |= ((qa_arr >> bit) & 1).astype(bool)

        masked = ds.drop_vars(self.qa_band)
        for var in masked.data_vars:
            masked[var] = masked[var].where(~mask)

        return masked


class NDVI(Processor):
    """Post-reproject processor that computes the Normalised Difference Vegetation Index.

    NDVI is computed on co-registered pixels after reprojection so that the
    band math is physically correct.  The source red and NIR bands are dropped
    and only the ``ndvi`` variable is retained.
    """

    ndvi_nir_band: str
    ndvi_red_band: str

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Compute NDVI = (NIR - Red) / (NIR + Red).

        Args:
            ds: Input dataset containing red and NIR variables.

        Returns:
            Dataset with a single ``ndvi`` variable.  Source bands are removed.

        Raises:
            ValueError: If NIR/red bands are not found.
        """
        if self.ndvi_nir_band not in ds.data_vars:
            raise ValueError(
                f"NDVI: NIR band '{self.ndvi_nir_band}' not found. Available: {list(ds.data_vars)}"
            )
        if self.ndvi_red_band not in ds.data_vars:
            raise ValueError(
                f"NDVI: red band '{self.ndvi_red_band}' not found. Available: {list(ds.data_vars)}"
            )

        nir = ds[self.ndvi_nir_band]
        red = ds[self.ndvi_red_band]
        denom = nir + red
        ndvi = (nir - red) / denom
        ndvi = ndvi.where(denom != 0)

        result = ds.drop_vars([self.ndvi_nir_band, self.ndvi_red_band])
        result["ndvi"] = ndvi
        return result


class Normalize(Processor):
    """Post-reproject processor that normalises pixel values per band.

    Supports min-max scaling and z-score normalisation.  NaN pixels are ignored
    when computing statistics.
    """

    normalize_method: str = _DEFAULT_NORMALIZE_METHOD

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Normalise each data variable.

        Args:
            ds: Input dataset.

        Returns:
            Dataset with normalised variables.

        Raises:
            ValueError: If the method is unknown.
        """
        method = self.normalize_method

        if method not in (_MINMAX, _ZSCORE):
            raise ValueError(
                f"Normalize: unknown method '{method}'. Use 'minmax' or 'zscore'."
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


class Composite(Processor):
    """Post-reproject processor that creates a temporal composite.

    Reduces the ``time`` dimension using a statistical method (median, mean, or
    max).  Useful for creating cloud-free or best-pixel composites.
    """

    composite_method: str = _DEFAULT_COMPOSITE_METHOD

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Reduce the ``time`` dimension to a single composite.

        Args:
            ds: Input dataset with a ``time`` dimension.

        Returns:
            Dataset with the ``time`` dimension reduced to a single step.

        Raises:
            ValueError: If the method is unknown or ``time`` is missing.
        """
        method = self.composite_method

        if "time" not in ds.dims:
            raise ValueError("Composite requires a 'time' dimension in the dataset.")

        if method == _MEDIAN:
            return ds.median(dim="time", keep_attrs=True)
        if method == _MEAN:
            return ds.mean(dim="time", keep_attrs=True)
        if method == _MAX:
            return ds.max(dim="time", keep_attrs=True)
        if method == _MIN:
            return ds.min(dim="time", keep_attrs=True)

        raise ValueError(
            f"Composite: unknown method '{method}'. Use '{_MEDIAN}', '{_MEAN}', '{_MAX}', or '{_MIN}'."
        )
