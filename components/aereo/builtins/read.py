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


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def read_odc_stac(
    task: ExtractionTask,
    **kwargs: Any,
) -> xr.Dataset:
    """Load STAC assets using ``odc.stac.load``.

    Reconstructs :class:`pystac.Item` objects from ``task.stac_items`` and
    returns a dataset tagged with temporal bounds in ``ds.attrs``.

    Args:
        task: The extraction task containing STAC items and read context.
        **kwargs: Extra keyword arguments passed to ``odc.stac.load``.
            Use ``odc_params`` to forward a dict of options. User-provided
            ``bbox`` and ``bands`` take precedence over values inferred from
            ``task``.

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

    odc_params = kwargs.get("odc_params")
    params = dict(odc_params) if odc_params is not None else {}

    if "chunks" not in params:
        params["chunks"] = {}

    if "bands" not in params and "channel_id" in task.assets.columns:
        params["bands"] = list(task.assets["channel_id"].unique())

    if task.bbox is not None and "bbox" not in params:
        params["bbox"] = task.bbox

    ds: xr.Dataset = odc_load(items, **params)

    infer_dataset_time_bounds(ds)
    # remove time dimension, we are working only with a single time slice per task
    if "time" in ds.dims:
        ds = ds.isel(time=0).drop_vars("time", errors="ignore")

    return ds
