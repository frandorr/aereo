"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to target grid cell definitions.
"""

from __future__ import annotations

from typing import Any

import xarray as xr
from pydantic import ConfigDict, validate_call
from aereo.interfaces import ExtractionTask


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def reproject_odc(
    ds: xr.Dataset,
    task: ExtractionTask,
    resampling: str = "nearest",
    fill_value: Any = None,
    dtype: Any = None,
) -> dict[str, xr.Dataset]:
    """Reproject *ds* for every patch in *task* using ``odc.geo.xr.reproject``.

    Args:
        ds: Input dataset.
        task: Extraction task containing the patches to reproject.
        resampling: Resampling method (e.g. 'nearest', 'bilinear').
        fill_value: Optional fill value for out-of-bounds pixels.
        dtype: Optional output dtype.

    Returns:
        Mapping from ``patch.id`` to the reprojected ``xr.Dataset``.
    """
    from odc.geo.xr import xr_reproject  # type: ignore[reportAttributeAccessIssue]

    kwargs: dict[str, Any] = {"resampling": resampling}
    if fill_value is not None:
        kwargs["fill_value"] = fill_value
    if dtype is not None:
        kwargs["dtype"] = dtype

    output: dict[str, xr.Dataset] = {}
    for patch in task.patches:
        output[patch.id] = xr_reproject(ds, patch.geobox, **kwargs)
    return output
