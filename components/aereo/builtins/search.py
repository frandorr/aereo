from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence, cast

import geopandas as gpd
from aereo.interfaces import SearchProvider, build_collection_asset_filters
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pystac_client import Client
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from structlog import get_logger
from pydantic import Field

logger = get_logger()

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SearchSTAC(SearchProvider):
    """Search provider for generic STAC APIs.

    This plugin queries any generic STAC API catalog using pystac_client
    and returns assets as a validated GeoDataFrame.
    """

    stac_api_url: str
    collections: Mapping[str, Sequence[str]] | Sequence[str] | None = None
    intersects: BaseGeometry | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    pystac_open_params: dict[str, Any] = Field(default_factory=dict)
    pystac_search_params: dict[str, Any] = Field(default_factory=dict)

    def __call__(self) -> GeoDataFrame[AssetSchema]:
        """Execute a STAC search against a generic STAC API.

        Returns:
            A GeoDataFrame of matched assets.
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
            searchkwargs["intersects"] = self.intersects.__geo_interface__

        # Merge in pystac_search_params
        searchkwargs.update(self.pystac_search_params)

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

            # Parse start/end time from properties
            properties = item.properties or {}
            item_start = None
            item_end = None

            for prop_key in ("start_datetime", "datetime"):
                val = properties.get(prop_key)
                if val:
                    try:
                        if isinstance(val, str):
                            if val.endswith("Z"):
                                val = val[:-1] + "+00:00"
                            item_start = datetime.fromisoformat(val)
                        elif isinstance(val, datetime):
                            item_start = val
                        break
                    except Exception:
                        pass

            for prop_key in ("end_datetime", "datetime"):
                val = properties.get(prop_key)
                if val:
                    try:
                        if isinstance(val, str):
                            if val.endswith("Z"):
                                val = val[:-1] + "+00:00"
                            item_end = datetime.fromisoformat(val)
                        elif isinstance(val, datetime):
                            item_end = val
                        break
                    except Exception:
                        pass

            # Fallbacks if properties are missing
            if item_start is None:
                item_start = item.datetime or q_start or datetime.now(timezone.utc)
            if item_end is None:
                item_end = item.datetime or q_end or datetime.now(timezone.utc)

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
                        "stac_item": stac_item_dict,
                    }
                )

        if not rows:
            return self.empty_result()

        gdf = gpd.GeoDataFrame(rows, geometry="geometry")
        return cast(GeoDataFrame, AssetSchema.validate(gdf))
