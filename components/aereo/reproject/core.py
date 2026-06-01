"""Built-in reproject module for AEREO extraction pipelines.

Provides Hamilton nodes for reprojecting an :class:`~xarray.Dataset` to a
target :class:`~odc.geo.geobox.GeoBox` using ``odc-geo``.

Registered under the ``aereo.reproject`` entry-point group.
"""

from __future__ import annotations

from typing import Any

supported_collections: tuple[str, ...] = ("*",)


def reproject_to_grid(
    ds: Any,
    geobox: Any,
    resampling: str = "nearest",
) -> Any:
    """Reproject *ds* to the target *geobox* using ``odc-geo``.

    Args:
        ds: Source dataset (typically an ``xarray.Dataset`` with
            ``rioxarray`` CRS metadata).
        geobox: Target grid definition (typically an
            ``odc.geo.geobox.GeoBox`` instance).
        resampling: Resampling algorithm forwarded to
            :func:`odc.geo.xr.reproject` (e.g. ``"nearest"``, ``"bilinear"``,
            ``"average"``).

    Returns:
        The reprojected dataset aligned to *geobox*.
    """
    from odc.geo.xr import xr_reproject  # type: ignore[reportAttributeAccessIssue]

    return xr_reproject(ds, geobox, resampling=resampling)
