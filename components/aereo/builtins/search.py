"""Aereo STAC search built-in plugin.

Provides the ``search_stac`` and ``search_earthaccess`` providers for executing
spatial and temporal queries against STAC APIs and NASA Earthdata, mapping the
results to Aereo Asset representations.
"""

from __future__ import annotations

import hashlib
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

import geopandas as gpd
import pandas as pd
from aereo.interfaces import build_collection_asset_filters, empty_asset_result
from aereo.interfaces.utils import normalize_geometry_input
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call
from pystac_client import Client
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_PROJ_EPSG_KEY = "proj:epsg"
_PROJ_CODE_KEY = "proj:code"
_EPSG_PREFIX = "EPSG:"


def _extract_stac_crs(item: Any) -> str | None:
    """Extract the native CRS from a PySTAC item using the projection extension.

    Args:
        item: A PySTAC item.

    Returns:
        The CRS string (e.g. ``"EPSG:4326"``) or ``None`` if not present.
    """
    properties = item.properties or {}
    epsg = properties.get(_PROJ_EPSG_KEY)
    if epsg is not None:
        return f"{_EPSG_PREFIX}{epsg}"
    code = properties.get(_PROJ_CODE_KEY)
    if code is not None:
        return str(code)
    return None


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def search_stac(
    collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
    intersects: BaseGeometry | dict[str, Any] | str | Path | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    stac_api_url: str,
    pystac_open_params: dict[str, Any] | None = None,
    search_params: dict[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]:
    """Search a generic STAC API and return assets as a GeoDataFrame.

    Args:
        collections: Mapping of collection -> asset keys, or list of collections.
        intersects: AOI geometry as a Shapely object, GeoJSON dict, or path.
        start_datetime: Optional start of temporal window.
        end_datetime: Optional end of temporal window.
        stac_api_url: URL of the STAC API catalog.
        pystac_open_params: Extra arguments forwarded to ``pystac_client.Client.open``.
        search_params: Extra arguments forwarded to ``client.search``.

    Returns:
        A GeoDataFrame of matched assets.

    Raises:
        ValueError: If connection to the STAC API fails or the search query fails.
    """
    collections, collection_asset_filters = build_collection_asset_filters(collections)

    time_range = None
    q_start = None
    q_end = None
    if start_datetime and end_datetime:
        q_start = start_datetime.astimezone(timezone.utc)
        q_end = end_datetime.astimezone(timezone.utc)
        time_range = f"{q_start.strftime(TIME_FORMAT)}/{q_end.strftime(TIME_FORMAT)}"
    elif start_datetime:
        q_start = start_datetime.astimezone(timezone.utc)
        time_range = f"{q_start.strftime(TIME_FORMAT)}/.."
    elif end_datetime:
        q_end = end_datetime.astimezone(timezone.utc)
        time_range = f"../{q_end.strftime(TIME_FORMAT)}"

    client_kwargs: dict[str, Any] = dict(pystac_open_params or {})
    client_kwargs.pop("url", None)
    if "headers" in client_kwargs and isinstance(client_kwargs["headers"], dict):
        client_kwargs["headers"] = {
            str(k): str(v) for k, v in client_kwargs["headers"].items()
        }

    try:
        client = Client.open(stac_api_url, **client_kwargs)
    except Exception as e:
        logger.error("Failed to connect to STAC API", url=stac_api_url, error=str(e))
        raise ValueError(f"Failed to connect to STAC API at {stac_api_url}: {e}") from e

    searchkwargs: dict[str, Any] = {}
    if collections:
        searchkwargs["collections"] = collections
    if time_range:
        searchkwargs["datetime"] = time_range

    normalized_intersects = normalize_geometry_input(intersects)
    if normalized_intersects is not None:
        searchkwargs["intersects"] = normalized_intersects.__geo_interface__

    searchkwargs.update(search_params or {})

    try:
        search_req = client.search(**searchkwargs)
        items = list(search_req.items())
    except Exception as e:
        logger.error("STAC search query failed", error=str(e))
        raise ValueError(f"STAC search query failed: {e}") from e

    if not items:
        return empty_asset_result()

    return _parse_stac_items_to_assets(
        items=items,
        collection_asset_filters=collection_asset_filters,
        q_start=q_start,
        q_end=q_end,
    )


def _parse_stac_items_to_assets(
    items: list[Any],
    collection_asset_filters: dict[str, Any],
    q_start: datetime | None,
    q_end: datetime | None,
) -> GeoDataFrame[AssetSchema]:
    """Parse PySTAC items into a GeoDataFrame of Aereo assets.

    Args:
        items: A list of PySTAC items returned by the search query.
        collection_asset_filters: Mapping of collections to allowed asset keys.
        q_start: The fallback start datetime.
        q_end: The fallback end datetime.

    Returns:
        A GeoDataFrame of matched assets conforming to AssetSchema.
    """
    rows = []
    for item in items:
        item_geometry = shape(item.geometry) if item.geometry else None
        stac_item_dict = item.to_dict()

        allowed = (
            collection_asset_filters.get(item.collection_id)
            if item.collection_id is not None
            else None
        )
        if allowed is None:
            assets_to_use = list(item.assets.keys())
        elif allowed:
            assets_to_use = [a for a in allowed if a in item.assets]
        else:
            if item.assets:
                assets_to_use = [next(iter(item.assets.keys()))]
            else:
                assets_to_use = []

        item_start = (
            item.common_metadata.start_datetime
            or item.datetime
            or q_start
            or datetime.now(timezone.utc)
        )
        item_end = (
            item.common_metadata.end_datetime
            or item.datetime
            or q_end
            or datetime.now(timezone.utc)
        )

        item_crs = _extract_stac_crs(item)
        for asset_key in assets_to_use:
            asset = item.assets[asset_key]
            rows.append(
                {
                    "id": f"{item.id}_{asset_key}",
                    "collection": item.collection_id,
                    "geometry": item_geometry,
                    "start_time": item_start,
                    "end_time": item_end,
                    "href": asset.href,
                    "channel_id": asset_key,
                    "crs": item_crs,
                    "stac_item": stac_item_dict,
                }
            )

    if not rows:
        return empty_asset_result()

    gdf = gpd.GeoDataFrame(rows, geometry="geometry")
    if "crs" in gdf.columns.tolist() and bool(gdf["crs"].isna().all()):
        gdf = gdf.drop(columns=["crs"])
    return cast(GeoDataFrame, AssetSchema.validate(gdf))


class NoSpatialMetadataError(Exception):
    """Raised when a UMM representation does not contain spatial metadata."""


def _to_polygon_or_multipolygon(polygons: list[Polygon]) -> BaseGeometry:
    """Return a single Polygon or a MultiPolygon from a list of polygons."""
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


def _parse_umm_polygon(umm: dict[str, Any]) -> BaseGeometry:
    """Parse UMM (Unified Metadata Model) spatial extent into a Shapely geometry."""
    spatial = umm.get("SpatialExtent", {})
    horiz = spatial.get("HorizontalSpatialDomain", {})
    geometry = horiz.get("Geometry", {})

    polygons: list[Polygon] = []

    if "GPolygons" in geometry:
        for p in geometry["GPolygons"]:
            boundary = p.get("Boundary", {})
            points = boundary.get("Points", [])
            if len(points) >= 3:
                coords = [(pt["Longitude"], pt["Latitude"]) for pt in points]
                polygons.append(Polygon(coords))

    if polygons:
        return _to_polygon_or_multipolygon(polygons)

    if "BoundingRectangles" in geometry:
        for rect in geometry["BoundingRectangles"]:
            min_x = rect.get("WestBoundingCoordinate")
            max_x = rect.get("EastBoundingCoordinate")
            min_y = rect.get("SouthBoundingCoordinate")
            max_y = rect.get("NorthBoundingCoordinate")
            if all(v is not None for v in (min_x, max_x, min_y, max_y)):
                polygons.append(
                    Polygon(
                        [
                            (min_x, min_y),
                            (max_x, min_y),
                            (max_x, max_y),
                            (min_x, max_y),
                        ]
                    )
                )

    if polygons:
        return _to_polygon_or_multipolygon(polygons)

    raise NoSpatialMetadataError("Could not find GPolygon or BoundingRectangle in UMM")


def _process_granule(
    g: Any,
    collections: list[str],
    intersects: BaseGeometry | None,
) -> dict[str, Any] | None:
    """Extract metadata from a single earthaccess granule into a row dict."""
    meta = g["meta"]
    umm = g["umm"]

    cid = meta.get("concept-id") or meta.get("native-id", "unknown")
    unique_id = hashlib.md5(cid.encode("utf-8")).hexdigest()

    coll_ref = umm.get("CollectionReference", {})
    collection_name = coll_ref.get("ShortName", collections[0])

    temp_ext = umm.get("TemporalExtent", {})
    range_dt = temp_ext.get("RangeDateTime", {})
    start_str = range_dt.get("BeginningDateTime")
    end_str = range_dt.get("EndingDateTime")

    if not start_str or not end_str:
        msg = (
            f"Skipping granule {cid} from collection {collection_name}: "
            f"missing or incomplete temporal metadata (start={start_str}, end={end_str})."
        )
        warnings.warn(msg, UserWarning, stacklevel=2)
        logger.warning(
            "skipping_granule_missing_temporal",
            granule_id=cid,
            collection=collection_name,
            start=start_str,
            end=end_str,
        )
        return None

    try:
        geom = _parse_umm_polygon(umm)
    except NoSpatialMetadataError:
        geom = intersects if intersects is not None else Polygon()

    s3_links = g.data_links(access="direct")
    https_links = g.data_links(access="external")

    if not s3_links and not https_links:
        logger.debug("no_links_found", concept_id=cid)
        return None

    s3_url = s3_links[0] if s3_links else None
    https_url = https_links[0] if https_links else None
    href = s3_url if s3_url else https_url

    s3_credentials_url = g.get_s3_credentials_endpoint()
    size_mb = g.size()

    return {
        "id": unique_id,
        "collection": collection_name,
        "geometry": geom,
        "start_time": start_str,
        "end_time": end_str,
        "href": href,
        "s3_url": s3_url,
        "https_url": https_url,
        "s3_credentials_url": s3_credentials_url,
        "size_mb": size_mb,
        "granule_id": cid,
    }


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def search_earthaccess(
    collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
    intersects: BaseGeometry | dict[str, Any] | str | Path | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    search_params: dict[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]:
    """Search NASA Earthdata using the earthaccess library.

    Args:
        collections: Mapping of collection -> asset keys, or list of collections.
        intersects: AOI geometry as a Shapely object, GeoJSON dict, or path.
        start_datetime: Optional start of temporal window.
        end_datetime: Optional end of temporal window.
        search_params: Extra arguments forwarded to ``earthaccess.search_data``.

    Returns:
        A GeoDataFrame of matched assets.

    Raises:
        ImportError: If the ``earthaccess`` library is not installed.
    """
    try:
        import earthaccess  # type: ignore
    except ImportError as e:
        raise ImportError(
            "The 'earthaccess' library is required to use search_earthaccess. "
            "Please install it (e.g., 'pip install earthaccess')."
        ) from e

    collections, _ = build_collection_asset_filters(collections)
    if not collections:
        return empty_asset_result()

    kwargs: dict[str, Any] = {"short_name": collections}

    if start_datetime is not None and end_datetime is not None:
        kwargs["temporal"] = (
            start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        )

    normalized_intersects = normalize_geometry_input(intersects)
    if normalized_intersects is not None:
        bounds = getattr(normalized_intersects, "bounds", None)
        if bounds is not None:
            kwargs["bounding_box"] = bounds

    kwargs.update(search_params or {})

    try:
        granules = earthaccess.search_data(**kwargs)
    except Exception as e:
        logger.error("earthaccess search failed", error=str(e), **kwargs)
        return empty_asset_result()

    if not granules:
        return empty_asset_result()

    rows = []
    for g in granules:
        row = _process_granule(
            g, collections, cast(BaseGeometry | None, normalized_intersects)
        )
        if row is not None:
            rows.append(row)

    if not rows:
        return empty_asset_result()

    gdf = gpd.GeoDataFrame(rows, geometry="geometry")
    gdf["start_time"] = pd.to_datetime(gdf["start_time"])
    gdf["end_time"] = pd.to_datetime(gdf["end_time"])

    return cast(GeoDataFrame, AssetSchema.validate(gdf))
