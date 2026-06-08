"""Utility functions for the interfaces component."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Sequence,
)

import xarray as xr
from shapely.geometry.base import BaseGeometry

_YAML_INSTALL_MSG = (
    "YAML support requires PyYAML. Install it with: pip install 'aereo[yaml]'"
)

_RIOXARRAY_INSTALL_MSG = "rioxarray support requires rioxarray. Install it with: pip install 'aereo[rioxarray]'"


def _import_rioxarray() -> Any:
    """Import rioxarray with a clear error message if missing."""
    try:
        import rioxarray  # noqa: F401
    except ImportError as exc:
        raise ImportError(_RIOXARRAY_INSTALL_MSG) from exc
    return rioxarray


def validate_aereo_dataset(
    ds: Any,
    *,
    require_crs: bool = True,
    require_dims: Sequence[str] | None = ("band", "y", "x"),
) -> None:
    """Validate that *ds* conforms to the AEREO xarray conventions.

    Args:
        ds: The dataset to validate.
        require_crs: If True, ensure ``ds.rio.crs`` is set.
        require_dims: If given, ensure all listed dimensions exist.

    Raises:
        ValueError: If any convention is violated.
        ImportError: If ``rioxarray`` is not installed and *require_crs* is True.
    """
    import xarray as xr

    if not isinstance(ds, xr.Dataset):
        raise ValueError(f"Expected xarray.Dataset, got {type(ds).__name__}")

    if require_crs:
        _import_rioxarray()
        # Access the rio accessor to trigger its import side-effects
        if ds.rio.crs is None:
            raise ValueError(
                "xarray.Dataset must have a CRS set via rioxarray (ds.rio.crs)"
            )

    if require_dims:
        missing = [d for d in require_dims if d not in ds.dims]
        if missing:
            raise ValueError(f"xarray.Dataset missing required dimensions: {missing}")


def set_dataset_time_bounds(
    ds: xr.Dataset, start_time: datetime, end_time: datetime
) -> xr.Dataset:
    """Set the start and end time bounds in the dataset's attributes.

    Args:
        ds: The xarray.Dataset.
        start_time: The start time.
        end_time: The end time.

    Returns:
        The dataset with time bounds set in its attributes.
    """
    ds.attrs["start_time"] = start_time
    ds.attrs["end_time"] = end_time
    return ds


def infer_dataset_time_bounds(ds: xr.Dataset) -> xr.Dataset:
    """Infer and set the start and end time bounds in the dataset's attributes.

    If a ``time`` coordinate is present, uses its minimum and maximum values.
    Otherwise, leaves the dataset attributes unchanged.

    Args:
        ds: The xarray.Dataset.

    Returns:
        The dataset with inferred time bounds set in its attributes (if possible).
    """
    import pandas as pd

    if "time" in ds.coords:
        times = ds.coords["time"].values
        if len(times) > 0:
            ds.attrs["start_time"] = pd.Timestamp(times.min()).to_pydatetime()
            ds.attrs["end_time"] = pd.Timestamp(times.max()).to_pydatetime()
    return ds


def _skip_empty(geom: BaseGeometry | None) -> bool:
    """Return True if *geom* is None or empty."""
    return geom is None or geom.is_empty


def _load_json_file(path: str | Path) -> dict[str, Any]:
    """Load and parse a JSON file."""
    path = Path(path)
    return json.loads(path.read_text())


def _union_all(geom_series) -> BaseGeometry:
    """Return the union of a geometry series, handling API differences."""
    if hasattr(geom_series, "union_all"):
        return geom_series.union_all()
    return geom_series.unary_union


def _import_yaml() -> Any:
    """Import yaml with a clear error message if PyYAML is missing."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(_YAML_INSTALL_MSG) from exc
    return yaml
