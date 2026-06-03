"""Built-in search provider plugins for the AEREO pipeline.

This module provides search provider plugins such as generic STAC API searchers
to query metadata repositories for target assets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence, cast

import geopandas as gpd
from aereo.interfaces import AereoProfile, PluginParam, SearchProvider
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pystac_client import Client
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SearchSTAC(SearchProvider, plugin_abstract=False):
    """Search provider for generic STAC APIs.

    This plugin queries any generic STAC API catalog using pystac_client
    and returns assets as a validated GeoDataFrame.
    """

    supported_collections: Sequence[str] = ["*"]

    required_params = [
        PluginParam(
            name="stac_api_url",
            type="str",
            description="The base URL of the STAC catalog API.",
            required=True,
        )
    ]
    optional_params = [
        PluginParam(
            name="assets",
            type="list[str]",
            description="List of asset keys to filter/retrieve. If not specified, defaults to the first available asset.",
            required=False,
        ),
        PluginParam(
            name="pystac_open_params",
            type="dict",
            description="Additional parameters forwarded to Client.open().",
            required=False,
        ),
        PluginParam(
            name="pystac_search_params",
            type="dict",
            description="Additional parameters forwarded to Client.search().",
            required=False,
        ),
    ]

    def search(
        self,
        profiles: Sequence[AereoProfile],
        intersects: BaseGeometry | None = None,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        search_params: Mapping[str, Any] | None = None,
    ) -> GeoDataFrame[AssetSchema]:
        """Execute a STAC search against a generic STAC API.

        Args:
            profiles: Sequence of AereoProfile objects defining what to search for.
            intersects: Geometry to filter by.
            start_datetime: Inclusive start of the temporal query range.
            end_datetime: Inclusive end of the temporal query range.
            search_params: Additional parameters for the search. Must include
                'stac_api_url' and optionally 'headers' and 'assets'.
                All other parameters are forwarded to the STAC search query.

        Returns:
            A GeoDataFrame of matched assets.
        """
        if search_params is None:
            search_params = {}

        stac_api_url = search_params.get("stac_api_url")
        if not stac_api_url:
            raise ValueError("stac_api_url must be provided in search_params.")

        # 1. Extract parameters
        assets = search_params.get("assets")
        pystac_open_params = search_params.get("pystac_open_params") or {}
        pystac_search_params = search_params.get("pystac_search_params") or {}

        # 2. Derive collections from all profile mappings
        collections: list[str] = []
        for profile in profiles:
            if profile.collections:
                collections.extend(str(c) for c in profile.collections.keys())
        collections = list(dict.fromkeys(collections))  # preserve order, dedupe

        # 3. Derive requested channel ids from profiles
        requested_channel_ids: set[str] = set()
        for profile in profiles:
            if profile.collections:
                for variables in profile.collections.values():
                    if variables:
                        requested_channel_ids.update(str(v) for v in variables)

        # 4. Temporal constraints
        time_range = None
        q_start = None
        q_end = None
        if start_datetime and end_datetime:
            q_start = start_datetime.astimezone(timezone.utc)
            q_end = end_datetime.astimezone(timezone.utc)
            time_range = (
                f"{q_start.strftime(TIME_FORMAT)}/{q_end.strftime(TIME_FORMAT)}"
            )
        elif start_datetime:
            q_start = start_datetime.astimezone(timezone.utc)
            time_range = f"{q_start.strftime(TIME_FORMAT)}/.."
        elif end_datetime:
            q_end = end_datetime.astimezone(timezone.utc)
            time_range = f"../{q_end.strftime(TIME_FORMAT)}"

        # 5. Open STAC client
        client_kwargs: dict[str, Any] = dict(pystac_open_params)
        # Remove 'url' if present — stac_api_url is already passed positionally.
        client_kwargs.pop("url", None)
        if "headers" in client_kwargs and isinstance(client_kwargs["headers"], dict):
            client_kwargs["headers"] = {
                str(k): str(v) for k, v in client_kwargs["headers"].items()
            }

        try:
            client = Client.open(stac_api_url, **client_kwargs)
        except Exception as e:
            logger.error(
                "Failed to connect to STAC API", url=stac_api_url, error=str(e)
            )
            raise ValueError(
                f"Failed to connect to STAC API at {stac_api_url}: {e}"
            ) from e

        # 6. Build search query keyword arguments
        searchkwargs: dict[str, Any] = {}
        if collections:
            searchkwargs["collections"] = collections
        if time_range:
            searchkwargs["datetime"] = time_range
        if intersects is not None:
            searchkwargs["intersects"] = intersects.__geo_interface__

        # Merge in pystac_search_params
        searchkwargs.update(pystac_search_params)

        # Forward other params excluding plugin-specific ones
        plugin_specific = {
            "stac_api_url",
            "assets",
            "pystac_open_params",
            "pystac_search_params",
        }
        for key, value in search_params.items():
            if key not in plugin_specific:
                if key not in searchkwargs:
                    searchkwargs[key] = value

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

            # Determine assets to extract
            if assets:
                assets_to_use = [a for a in assets if a in item.assets]
            elif requested_channel_ids:
                assets_to_use = [a for a in requested_channel_ids if a in item.assets]
            else:
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
