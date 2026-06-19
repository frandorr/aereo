"""Utility functions for the interfaces component."""

from __future__ import annotations

import json
from datetime import datetime
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
