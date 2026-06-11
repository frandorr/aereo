"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to target grid cell definitions.
"""

from __future__ import annotations

from typing import Any

import xarray as xr
from aereo.interfaces import ExtractionTask, Reprojector


class ReprojectODC(Reprojector):
    """Default reprojector using ``odc-geo``."""

    resampling: str = "nearest"
    fill_value: Any = None
    dtype: Any = None

    def __call__(
        self,
        ds: xr.Dataset,
        task: ExtractionTask,
    ) -> dict[str, xr.Dataset]:
        """Reproject *ds* for every patch in *task* using ``odc.geo.xr.reproject``.

        Args:
            ds: Input dataset.
            task: Extraction task containing the patches to reproject.

        Returns:
            Mapping from ``patch.id`` to the reprojected ``xr.Dataset``.
        """
        from odc.geo.xr import xr_reproject  # type: ignore[reportAttributeAccessIssue]

        kwargs: dict[str, Any] = {"resampling": self.resampling}
        if self.fill_value is not None:
            kwargs["fill_value"] = self.fill_value
        if self.dtype is not None:
            kwargs["dtype"] = self.dtype

        output: dict[str, xr.Dataset] = {}
        for patch in task.patches:
            output[patch.id] = xr_reproject(ds, patch.geobox, **kwargs)
        return output
