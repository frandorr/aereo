"""Built-in writer plugins for the AEREO pipeline.

This module provides writer plugins such as GeoTIFF/COG writers to output spatial
datasets to the filesystem or object storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import xarray as xr
from pydantic import ConfigDict, validate_call


def _dataset_to_raster_bands(ds: xr.Dataset) -> xr.DataArray:
    """Combine all data variables in *ds* into a single multi-band DataArray.

    Each variable becomes one or more raster bands. Variables that already
    contain a ``band`` dimension with more than one band are expanded so that
    every original band becomes a separate raster band. The resulting
    DataArray has a ``band`` dimension whose coordinate values identify the
    source variable (and original band, when applicable).

    Args:
        ds: Dataset whose variables share the same spatial grid.

    Returns:
        A DataArray with ``band`` as the leading dimension, suitable for
        ``rio.to_raster()``.

    Raises:
        ValueError: If the dataset contains no data variables.
    """
    band_arrays: list[xr.DataArray] = []

    for var_name in ds.data_vars:
        da = ds[var_name]
        if "band" in da.dims and da.sizes["band"] != 1:
            for band_val in da.coords["band"].values:
                band_da = da.sel(band=band_val).drop_vars("band", errors="ignore")
                band_da = band_da.expand_dims(band=[f"{var_name}_{band_val}"])
                band_arrays.append(band_da)
        else:
            if "band" in da.dims:
                da = da.squeeze("band", drop=True)
            da = da.expand_dims(band=[str(var_name)])
            band_arrays.append(da)

    if not band_arrays:
        raise ValueError("Dataset contains no data variables to write.")

    combined = xr.concat(band_arrays, dim="band")
    combined = combined.transpose("band", ...)
    # Preserve dataset-level attributes (e.g. start_time/end_time set by the
    # orchestrator) as raster metadata tags. DataArray attrs are kept as a
    # fallback, but dataset attrs take precedence except for long_name, which
    # is derived from the band coordinate.
    attrs = dict(combined.attrs)
    attrs.update(ds.attrs)
    attrs["long_name"] = list(combined.coords["band"].values)
    combined.attrs = attrs
    return combined


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def write_geotiff(
    ds: xr.Dataset,
    path: str | Path,
    **kwargs: Any,
) -> str:
    """Write *ds* to a GeoTIFF at *path*.

    All variables are combined into a single multi-band raster. The caller
    (the AEREO orchestrator) is responsible for constructing *path*, splitting
    time dimensions, and building the artifact catalog.

    Args:
        ds: The xarray.Dataset to write. Must not contain a ``time`` dimension;
            the orchestrator calls this function once per time slice.
        path: Destination path to write.
        **kwargs: Keyword arguments forwarded to ``da.rio.to_raster()``.

    Returns:
        The path that was written.

    Raises:
        ValueError: If the dataset contains no data variables or has a
            ``time`` dimension.
    """
    import rioxarray  # noqa: F401

    path = Path(path)
    if "time" in ds.dims:
        raise ValueError(
            "write_geotiff does not accept datasets with a 'time' dimension; "
            "the orchestrator must split time slices before calling the writer."
        )

    combined_da = _dataset_to_raster_bands(ds)
    combined_da.rio.to_raster(str(path), **kwargs)
    return str(path)
