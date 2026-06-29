"""Utility functions for the interfaces component."""

from __future__ import annotations

import json
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Sequence,
)

import xarray as xr
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

if TYPE_CHECKING:
    import geopandas as gpd

_YAML_INSTALL_MSG = (
    "YAML support requires PyYAML. Install it with: pip install 'aereo[yaml]'"
)

_RIOXARRAY_INSTALL_MSG = "rioxarray support requires rioxarray. Install it with: pip install 'aereo[rioxarray]'"


def _import_rioxarray() -> Any:
    """Import rioxarray with a clear error message if missing."""
    try:
        import rioxarray
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


def normalize_geometry_input(
    value: BaseGeometry | dict[str, Any] | str | Path | None,
) -> BaseGeometry | None:
    """Normalize a geometry input into a Shapely ``BaseGeometry``.

    Supports:

    * ``BaseGeometry`` instances (returned unchanged)
    * GeoJSON-like ``dict``
    * A ``str`` or ``Path`` pointing to a GeoJSON file (``.geojson`` or ``.json``)

    Args:
        value: Geometry input to normalize.

    Returns:
        A Shapely geometry, or ``None`` if the input was ``None``.

    Raises:
        ValueError: If the input cannot be parsed into a geometry.
    """
    if value is None:
        return None

    if isinstance(value, BaseGeometry):
        return value

    if isinstance(value, Path):
        return _geometry_from_geojson_path(value)

    if isinstance(value, str):
        if _looks_like_geojson_path(value):
            return _geometry_from_geojson_path(Path(value))
        raise ValueError(
            "Invalid geometry input type: str. "
            "Expected a path to a GeoJSON file (ending in .geojson or .json) "
            "or a file-system path containing a separator."
        )

    if isinstance(value, dict):
        return shape(value)

    raise ValueError(
        f"Invalid geometry input type: {type(value).__name__}. "
        "Expected BaseGeometry, GeoJSON dict, or path to a GeoJSON file."
    )


def _looks_like_geojson_path(value: str) -> bool:
    """Return True if *value* looks like a GeoJSON file path."""
    lowered = value.lower()
    return lowered.endswith((".geojson", ".json")) or "/" in value or "\\" in value


def _geometry_from_geojson_path(path: Path) -> BaseGeometry:
    """Load a GeoJSON file and return its geometry as a Shapely object."""
    if not path.exists():
        raise ValueError(f"Geometry file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    geojson = _extract_geometry_from_geojson(data)
    if geojson is None:
        raise ValueError(f"Could not extract a geometry from {path}")
    return shape(geojson)


def _extract_geometry_from_geojson(
    data: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract a GeoJSON geometry dict from Feature, FeatureCollection, or raw geometry."""
    if data.get("type") == "FeatureCollection":
        features = data.get("features") or []
        if not features:
            return None
        return features[0].get("geometry")
    if data.get("type") == "Feature":
        return data.get("geometry")
    if "type" in data and data["type"] in (
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    ):
        return data
    return None


def _union_all(geom_series: gpd.GeoSeries) -> BaseGeometry:
    """Return the union of a geometry series, handling API differences.

    Args:
        geom_series: GeoPandas ``GeoSeries`` to union.

    Returns:
        A Shapely geometry representing the union.
    """
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


def resolve_callable(val: Any) -> Any:
    """Resolve a callable from a string, dict target, or direct callable.

    Args:
        val: The value to resolve.

    Returns:
        The resolved callable.
    """
    import importlib

    if callable(val):
        return val

    if isinstance(val, str):
        if ":" in val:
            module_name, func_name = val.split(":", 1)
        else:
            module_name, func_name = val.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        return func

    if isinstance(val, dict) or (hasattr(val, "keys") and hasattr(val, "get")):
        d = dict(val)
        target = d.pop("_target_", None)
        if not target:
            raise ValueError(
                "Dictionary-based configuration must include a '_target_' key."
            )

        func = resolve_callable(target)
        kwargs = {k: v for k, v in d.items() if not k.startswith("_")}
        if kwargs:
            return partial(func, **kwargs)
        return func

    raise ValueError(f"Cannot resolve callable from type: {type(val).__name__}")


def update_callable(callable_obj: Any, **kwargs: Any) -> Any:
    """Update a callable (standard function or partial) with new keywords.

    Args:
        callable_obj: The callable to update.
        **kwargs: The keyword arguments to update it with.

    Returns:
        A new callable with updated keyword arguments.
    """
    if isinstance(callable_obj, partial):
        new_keywords = {**callable_obj.keywords, **kwargs}
        return partial(callable_obj.func, *callable_obj.args, **new_keywords)
    if callable(callable_obj):
        return partial(callable_obj, **kwargs)
    return partial(resolve_callable(callable_obj), **kwargs)


def _is_function_target(target: str) -> bool:
    """Return True if *target* resolves to a function (not a class).

    Args:
        target: Import path string.

    Returns:
        True for functions/methods, False for classes or other callables.
    """
    import inspect

    obj = resolve_callable(target)
    if isinstance(obj, partial):
        obj = obj.func
    return inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isbuiltin(obj)


def _prepare_config_for_instantiate(cfg: Any) -> Any:
    """Recursively mark function targets with ``_partial_: true``.

    Hydra's ``instantiate`` calls functions by default. AEREO's functional
    plugins are configured as ``_target_`` paths and should be returned as
    partially-bound callables instead, so users do not need to add the
    ``_partial_`` key themselves.

    Args:
        cfg: Configuration container (dict, list, or scalar).

    Returns:
        The same shape with ``_partial_: true`` injected for function targets.
    """
    if isinstance(cfg, dict):
        d = dict(cfg)
        target = d.get("_target_")
        if isinstance(target, str) and _is_function_target(target):
            d["_partial_"] = True
        return {k: _prepare_config_for_instantiate(v) for k, v in d.items()}
    if isinstance(cfg, list):
        return [_prepare_config_for_instantiate(v) for v in cfg]
    return cfg
