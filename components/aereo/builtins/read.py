"""Built-in reader plugins for the AEREO pipeline.

This module provides a default Reader implementation that uses ``odc.stac``
to load pixel data from STAC items in native CRS as an xarray.Dataset.
"""

from __future__ import annotations

from typing import Any

import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import ExtractionTask, infer_dataset_time_bounds

try:
    from odc.stac import load as odc_load
except ImportError:  # pragma: no cover
    odc_load = None  # type: ignore[assignment]

try:
    from odc.loader import configure_rio
except ImportError:  # pragma: no cover
    configure_rio = None  # type: ignore[assignment]

_RIO_CONFIGURED = False


def _ensure_rio_configured(gdal_env: dict[str, Any] | None = None) -> None:
    """Pre-initialize odc.loader's GDAL/rasterio session once per process.

    This avoids a deadlock that can occur when ``odc.stac.load`` initializes
    the ThreadSession lazily inside nested ``rio_env`` context managers on
    some GDAL/rasterio combinations.

    Args:
        gdal_env: Optional GDAL configuration options to merge with the
            cloud defaults (e.g. ``{"GDAL_HTTP_MAX_RETRY": "3"}``). These
            are passed to ``odc.loader.configure_rio`` and become the
            process-wide default for rasterio sessions used by odc-stac.
    """
    global _RIO_CONFIGURED
    if configure_rio is None:
        return
    if not _RIO_CONFIGURED or gdal_env is not None:
        configure_rio(cloud_defaults=True, **(gdal_env or {}))
        _RIO_CONFIGURED = True


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def read_odc_stac(
    task: ExtractionTask,
    gdal_env: dict[str, Any] | None = None,
    **kwargs: Any,
) -> xr.Dataset:
    """Load STAC assets using ``odc.stac.load``.

    Reconstructs :class:`pystac.Item` objects from ``task.stac_items`` and
    returns a dataset tagged with temporal bounds in ``ds.attrs``.

    Args:
        task: The extraction task containing STAC items and read context.
        gdal_env: Optional GDAL configuration options to merge with odc-stac's
            cloud defaults (e.g. ``{"GDAL_HTTP_MAX_RETRY": "3"}``). These are
            forwarded to ``odc.loader.configure_rio`` and become the process-wide
            default for rasterio sessions used by this reader.
        **kwargs: Keyword arguments forwarded to ``odc.stac.load``. AEREO
            injects sensible defaults for ``chunks``, ``bands``, and ``bbox``
            only when they are not already provided.

    Returns:
        xr.Dataset (potentially dask-backed) in the native CRS of the
        STAC items.

    Raises:
        ImportError: If ``odc-stac`` is not installed.
        ValueError: If ``task.stac_items`` is empty.
    """
    if odc_load is None:  # pragma: no cover
        raise ImportError(
            "odc-stac is required for read_odc_stac. "
            "Install it with: pip install 'aereo[stac]'"
        )

    items = task.stac_items
    if not items:
        raise ValueError(
            "read_odc_stac requires at least one STAC item in task.stac_items. "
            "Ensure the search plugin (e.g. search_stac) stores full STAC "
            "item dictionaries in the assets."
        )

    params = dict(kwargs)

    if "chunks" not in params:
        params["chunks"] = {}

    if "bands" not in params and "channel_id" in task.assets.columns:
        params["bands"] = list(task.assets["channel_id"].unique())

    if task.bbox is not None and "bbox" not in params:
        params["bbox"] = task.bbox

    _ensure_rio_configured(gdal_env)

    ds: xr.Dataset = odc_load(items, **params)

    infer_dataset_time_bounds(ds)
    # remove time dimension, we are working only with a single time slice per task
    if "time" in ds.dims:
        ds = ds.isel(time=0).drop_vars("time", errors="ignore")

    return ds
