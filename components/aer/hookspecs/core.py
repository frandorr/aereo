"""Core pluggy hookspecs for the aer plugin system.

Defines the hook specifications that external packages implement
to provide custom search, task preparation, and extraction logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pluggy
from aer.schemas import ArtifactSchema, AssetSchema

if TYPE_CHECKING:
    from pandera.typing.geopandas import GeoDataFrame

# Pluggy project identifier - all aer plugins use this namespace
PROJECT_NAME = "aer"

# Markers for defining hookspecs and hook implementations
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


@hookspec
def supported_collections() -> Sequence[str]:
    """Return a list of collection identifiers that this plugin supports.
    This is used to determine which plugins to invoke for a given function based on the collections specified.

    Returns:
        A list of collection identifiers (strings) that this plugin supports.
    """
    ...


@hookspec
def search(
    collections: Sequence[str],
    intersects: dict[str, Any] | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    search_params: Mapping[str, Any] | None,
) -> GeoDataFrame[AssetSchema]:
    """Search for collections data matching the query.

    Args:
        collections: List of collection identifiers to search within.
        intersects: Optional GeoJSON-like geometry dict to filter results by spatial intersection.
            formatted according to `RFC 7946, section 3.1 (GeoJSON) <https://tools.ietf.org/html/rfc7946>`_.
        start_datetime: Optional start datetime to filter results by temporal range.
        end_datetime: Optional end datetime to filter results by temporal range.
        search_params: Additional parameters for the search, specific to
            the collection or provider.

    Returns:
        A GeoDataFrame of search results, where each row represents a dataset
        or asset that matches the search criteria, and includes metadata such
        as collection, geometry, time range, and any other relevant attributes.
    """
    ...


@hookspec
def prepare_for_extraction(
    search_results: GeoDataFrame[AssetSchema],
    prepare_params: dict[str, Any] | None,
) -> list[GeoDataFrame[AssetSchema]]:
    """Prepare search results for extraction by grouping/filtering/transforming/etc
    them into one or more GeoDataFrames of extraction tasks.
    Each GeoDataFrame represents a batch of results that can be processed together for extraction.

    Args:
        search_results: The GeoDataFrame of search results to prepare for extraction.
        prepare_params: Additional parameters for preparation,
            user defined and specific to the collection, provider, outputs, etc.

    Returns:
        A list of GeoDataFrames, each containing a batch of search results to be extracted together.
        If you wish to extract each result individually, return a list where each element
        is a single-row GeoDataFrame (e.g., `[results.iloc[[i]] for i in range(len(results))]`).

    """
    ...


@hookspec
def extract(
    assets_batch: GeoDataFrame[AssetSchema],
    extract_params: dict[str, Any] | None,
) -> GeoDataFrame[ArtifactSchema]:
    """Extract data for a batch of assets.
    Args:
        assets_batch: A GeoDataFrame containing a batch of assets to extract.
            This is one of the GeoDataFrames returned by the `prepare_for_extraction` hook.
        extract_params: Additional parameters for extraction,
            user defined and specific to the collection, provider, outputs, etc.

    Returns:
        A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
        and its corresponding grid_cell, and includes metadata such as collection, geometry,
        time range, and any other relevant attributes.
    """
    ...
