"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to target grid cell definitions.
"""

from __future__ import annotations

from typing import Any

from aereo.interfaces import AereoDataset, Reprojector


class ReprojectODC(Reprojector):
    """Default reprojector using ``odc-geo``.

    Expects *geobox* to be an ``odc.geo.geobox.GeoBox`` instance.
    """

    resampling: str = "nearest"
    fill_value: Any = None
    dtype: Any = None

    def __call__(
        self,
        ds: AereoDataset,
        geobox: Any,
    ) -> AereoDataset:
        """Reproject *ds* to *geobox* using ``odc.geo.xr.reproject``.

        Args:
            ds: Input dataset.
            geobox: Target ``odc.geo.geobox.GeoBox``.

        Returns:
            Reprojected dataset.
        """
        from odc.geo.xr import xr_reproject  # type: ignore[reportAttributeAccessIssue]

        kwargs: dict[str, Any] = {"resampling": self.resampling}
        if self.fill_value is not None:
            kwargs["fill_value"] = self.fill_value
        if self.dtype is not None:
            kwargs["dtype"] = self.dtype

        return xr_reproject(ds, geobox, **kwargs)
