"""Built-in reader plugins for the AEREO pipeline.

This module provides a default Reader implementation that uses ``odc.stac``
to load pixel data from STAC items in native CRS as an xarray.Dataset.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import infer_dataset_time_bounds
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame

try:
    from odc.stac import load as odc_load
except ImportError:  # pragma: no cover
    odc_load = None  # type: ignore[assignment]


def _to_native(obj: Any) -> Any:
    """Recursively convert numpy containers in *obj* to plain Python types.

    Parquet round-trips can leave list fields as ``np.ndarray`` instances.
    ``pystac.Item.from_dict`` expects JSON-like structures, so this helper
    normalises arrays/scalars before reconstruction.
    """
    if isinstance(obj, np.ndarray):
        return [_to_native(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    return obj


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def read_odc_stac(
    files: list[str],
    assets: GeoDataFrame[AssetSchema] | None = None,
    odc_params: dict[str, Any] | None = None,
) -> xr.Dataset:
    """Load STAC assets using ``odc.stac.load``.

    Reconstructs :class:`pystac.Item` objects from the ``stac_item`` column of
    *assets* and returns a dataset tagged with temporal bounds in ``ds.attrs``.

    Args:
        files: List of source filenames/URLs. Not used directly by this reader,
            but accepted to conform to the reader contract.
        assets: GeoDataFrame of source assets. Must contain a ``stac_item``
            column with serialised STAC item dictionaries.
        odc_params: Extra keyword arguments passed to ``odc.stac.load``.

    Returns:
        xr.Dataset (potentially dask-backed) in the native CRS of the
        STAC items.

    Raises:
        ImportError: If ``odc-stac`` or ``pystac`` is not installed.
        ValueError: If *assets* is None, no ``stac_item`` column is found, or
            no valid STAC items can be reconstructed.
    """
    import pystac

    if odc_load is None:  # pragma: no cover
        raise ImportError(
            "odc-stac is required for read_odc_stac. "
            "Install it with: pip install 'aereo[stac]'"
        )

    if assets is None:
        raise ValueError(
            "read_odc_stac requires the 'assets' GeoDataFrame passed by the orchestrator."
        )

    if "stac_item" not in assets.columns:
        raise ValueError(
            "read_odc_stac requires a 'stac_item' column in assets. "
            "Ensure the search plugin (e.g. SearchSTAC) stores full STAC "
            "item dictionaries there."
        )

    seen_ids: set[str] = set()
    items: list[pystac.Item] = []
    for raw in assets["stac_item"]:
        if raw is None:
            continue
        item = pystac.Item.from_dict(_to_native(raw))
        if item.id not in seen_ids:
            seen_ids.add(item.id)
            items.append(item)

    if not items:
        raise ValueError("No valid STAC items found in assets['stac_item'].")

    params = dict(odc_params) if odc_params is not None else {}

    if "chunks" not in params:
        params["chunks"] = {}

    if "bands" not in params and "channel_id" in assets.columns:
        params["bands"] = list(assets["channel_id"].unique())

    ds: xr.Dataset = odc_load(items, **params)

    infer_dataset_time_bounds(ds)

    return ds
