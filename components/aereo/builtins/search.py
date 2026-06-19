"""Aereo STAC search built-in plugin.

Provides the SearchSTAC provider for executing spatial and temporal queries
against generic STAC APIs and mapping the results to Aereo Asset representations.
"""

from __future__ import annotations

import hashlib
import warnings
from datetime import datetime, timezone
from typing import Any, cast

import geopandas as gpd
import pandas as pd
from aereo.interfaces import SearchProvider, build_collection_asset_filters
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pystac_client import Client
from pydantic import Field
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _extract_stac_crs(item: Any) -> str | None:
    """Extract the native CRS from a PySTAC item using the projection extension.

    Prefers ``proj:epsg`` and falls back to ``proj:code``. Returns ``None`` if
    neither is present.
    """
    properties = item.properties or {}
    epsg = properties.get("proj:epsg")
    if epsg is not None:
        return f"EPSG:{epsg}"
    code = properties.get("proj:code")
    if code is not None:
        return str(code)
    return None


class SearchSTAC(SearchProvider):
    """Search provider for generic STAC APIs.

    This plugin queries any generic STAC API catalog using pystac_client
    and returns assets as a validated GeoDataFrame.
    """

    stac_api_url: str
    pystac_open_params: dict[str, Any] = Field(default_factory=dict)

    def __call__(self) -> GeoDataFrame[AssetSchema]:
        """Execute a STAC search against a generic STAC API.

        Returns:
            A GeoDataFrame of matched assets.

        Raises:
            ValueError: If connection to the STAC API fails or the search query fails.
        """
        # 2. Derive collections and per-collection asset filters.
        collections, collection_asset_filters = build_collection_asset_filters(
            self.collections
        )

        # 4. Temporal constraints
        time_range = None
        q_start = None
        q_end = None
        if self.start_datetime and self.end_datetime:
            q_start = self.start_datetime.astimezone(timezone.utc)
            q_end = self.end_datetime.astimezone(timezone.utc)
            time_range = (
                f"{q_start.strftime(TIME_FORMAT)}/{q_end.strftime(TIME_FORMAT)}"
            )
        elif self.start_datetime:
            q_start = self.start_datetime.astimezone(timezone.utc)
            time_range = f"{q_start.strftime(TIME_FORMAT)}/.."
        elif self.end_datetime:
            q_end = self.end_datetime.astimezone(timezone.utc)
            time_range = f"../{q_end.strftime(TIME_FORMAT)}"

        # 5. Open STAC client
        client_kwargs: dict[str, Any] = dict(self.pystac_open_params)
        # Remove 'url' if present — stac_api_url is already passed positionally.
        client_kwargs.pop("url", None)
        if "headers" in client_kwargs and isinstance(client_kwargs["headers"], dict):
            client_kwargs["headers"] = {
                str(k): str(v) for k, v in client_kwargs["headers"].items()
            }

        try:
            client = Client.open(self.stac_api_url, **client_kwargs)
        except Exception as e:
            logger.error(
                "Failed to connect to STAC API", url=self.stac_api_url, error=str(e)
            )
            raise ValueError(
                f"Failed to connect to STAC API at {self.stac_api_url}: {e}"
            ) from e

        # 6. Build search query keyword arguments
        searchkwargs: dict[str, Any] = {}
        if collections:
            searchkwargs["collections"] = collections
        if time_range:
            searchkwargs["datetime"] = time_range
        if self.intersects is not None:
            searchkwargs["intersects"] = cast(
                BaseGeometry, self.intersects
            ).__geo_interface__

        # Merge in search_params
        searchkwargs.update(self.search_params)

        # 7. Execute search
        try:
            search_req = client.search(**searchkwargs)
            items = list(search_req.items())
        except Exception as e:
            logger.error("STAC search query failed", error=str(e))
            raise ValueError(f"STAC search query failed: {e}") from e

        if not items:
            return self.empty_result()

        # 8. Generate one row per requested asset for each matched item
        return self._parse_stac_items_to_assets(
            items=items,
            collection_asset_filters=collection_asset_filters,
            q_start=q_start,
            q_end=q_end,
        )

    def _parse_stac_items_to_assets(
        self,
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

            # Determine assets to extract using per-collection filters.
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
                # No filter defined for this collection — ultimate fallback.
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
            return self.empty_result()

        gdf = gpd.GeoDataFrame(rows, geometry="geometry")
        # Only expose crs when at least one item provided it. A column of all
        # nulls is equivalent to "not provided" for downstream grouping.
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
    """Parse UMM (Unified Metadata Model) spatial extent into a Shapely geometry.

    Tries to find GPolygons -> Boundary -> Points and constructs Polygon(s).
    If multiple GPolygons are present, returns a MultiPolygon.
    Falls back to BoundingRectangles if no GPolygons found.
    If none found, raises NoSpatialMetadataError.
    """
    spatial = umm.get("SpatialExtent", {})
    horiz = spatial.get("HorizontalSpatialDomain", {})
    geometry = horiz.get("Geometry", {})

    polygons: list[Polygon] = []

    # Check for GPolygons
    if "GPolygons" in geometry:
        for p in geometry["GPolygons"]:
            boundary = p.get("Boundary", {})
            points = boundary.get("Points", [])
            if len(points) >= 3:
                coords = [(pt["Longitude"], pt["Latitude"]) for pt in points]
                polygons.append(Polygon(coords))

    if polygons:
        return _to_polygon_or_multipolygon(polygons)

    # Check for BoundingRectangles
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
    """Extract metadata from a single earthaccess granule into a row dict.

    Args:
        g: An earthaccess granule object.
        collections: Collection short names used as a fallback.
        intersects: Optional AOI geometry used as a fallback for missing UMM
            spatial metadata.

    Returns:
        A metadata row dict, or ``None`` if the granule should be skipped.
    """
    meta = g["meta"]
    umm = g["umm"]

    # The Granule UR or concept-id works as a unique identifier
    cid = meta.get("concept-id") or meta.get("native-id", "unknown")
    unique_id = hashlib.md5(cid.encode("utf-8")).hexdigest()

    # Collection short name
    coll_ref = umm.get("CollectionReference", {})
    collection_name = coll_ref.get("ShortName", collections[0])

    # Parse temporal
    temp_ext = umm.get("TemporalExtent", {})
    range_dt = temp_ext.get("RangeDateTime", {})
    start_str = range_dt.get("BeginningDateTime")
    end_str = range_dt.get("EndingDateTime")

    # Skip granules with missing temporal metadata
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
        # If UMM parsing fails, fallback to the requested intersects geometry
        geom = intersects if intersects is not None else Polygon()

    # Find S3 and HTTPS links independently
    s3_links = g.data_links(access="direct")
    https_links = g.data_links(access="external")

    if not s3_links and not https_links:
        logger.debug("no_links_found", concept_id=cid)
        return None

    s3_url = s3_links[0] if s3_links else None
    https_url = https_links[0] if https_links else None
    href = s3_url if s3_url else https_url

    # S3 credentials endpoint for NASA Earthdata direct access
    s3_credentials_url = g.get_s3_credentials_endpoint()

    # Estimate size
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


class SearchEarthaccess(SearchProvider):
    """Search provider for NASA Earthdata using the earthaccess library.

    All search parameters are configurable as Pydantic fields so that the
    provider can be instantiated via Hydra or directly in code.
    Requires the `earthaccess` library to be installed.
    """

    def __call__(self) -> GeoDataFrame[AssetSchema]:
        """Search NASA Earthdata using earthaccess."""
        try:
            import earthaccess  # type: ignore
        except ImportError as e:
            raise ImportError(
                "The 'earthaccess' library is required to use SearchEarthaccess. "
                "Please install it (e.g., 'pip install earthaccess')."
            ) from e

        collections, _ = build_collection_asset_filters(self.collections)
        if not collections:
            return self.empty_result()

        kwargs: dict[str, Any] = {"short_name": collections}

        if self.start_datetime is not None and self.end_datetime is not None:
            kwargs["temporal"] = (
                self.start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                self.end_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            )

        if self.intersects is not None:
            bounds = getattr(self.intersects, "bounds", None)
            if bounds is not None:
                kwargs["bounding_box"] = bounds

        kwargs.update(self.search_params)

        try:
            granules = earthaccess.search_data(**kwargs)
        except Exception as e:
            logger.error("earthaccess search failed", error=str(e), **kwargs)
            return self.empty_result()

        if not granules:
            return self.empty_result()

        rows = []
        for g in granules:
            row = _process_granule(
                g, collections, cast(BaseGeometry | None, self.intersects)
            )
            if row is not None:
                rows.append(row)

        if not rows:
            return self.empty_result()

        gdf = gpd.GeoDataFrame(rows, geometry="geometry")
        gdf["start_time"] = pd.to_datetime(gdf["start_time"])
        gdf["end_time"] = pd.to_datetime(gdf["end_time"])

        return cast(GeoDataFrame, AssetSchema.validate(gdf))
