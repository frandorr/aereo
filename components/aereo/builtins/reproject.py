"""Built-in reprojector plugins for the AEREO pipeline.

This module provides spatial reprojection plugins using odc-geo to warp and align
native-resolution spatial datasets to target grid cell definitions.
"""

from __future__ import annotations

from typing import Any, Mapping

from aereo.interfaces import AereoDataset, Reprojector


class ReprojectODC(Reprojector):
    """Default reprojector using ``odc-geo``.

    Expects *geobox* to be an ``odc.geo.geobox.GeoBox`` instance.
    """

    supported_collections = ("*",)

    def reproject(
        self,
        ds: AereoDataset,
        geobox: Any,
        params: Mapping[str, Any],
    ) -> AereoDataset:
        """Reproject *ds* to *geobox* using ``odc.geo.xr.reproject``.

        Args:
            ds: Input dataset.
            geobox: Target ``odc.geo.geobox.GeoBox``.
            params: Plugin parameters. Supports ``resampling``
                (default ``"nearest"``).

        Returns:
            Reprojected dataset.
        """
        from odc.geo.xr import reproject as odc_reproject  # type: ignore[reportAttributeAccessIssue]

        resampling = params.get("resampling", "nearest")
        return odc_reproject(ds, geobox, resampling=resampling)
