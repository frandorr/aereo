"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to a target geobox, CRS, or resolution.
"""

from __future__ import annotations

from typing import Any

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
