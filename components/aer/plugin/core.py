"""Core pluggy hookspecs for the aer plugin system.

Defines the hook specifications that external packages implement
to provide custom search, task preparation, and extraction logic.

Example for external plugin developers::

    from aer.plugin import hookimpl, AerSpec
    from pandera.typing.geopandas import GeoDataFrame
    from aer.search import SearchQuery

    class MySearchPlugin:
        # Plugins MUST declare supported_products class attribute
        supported_products: list[str] = ["goes-16", "goes-18"]

        @hookimpl
        def search(self, query: SearchQuery) -> GeoDataFrame:
            # Your search implementation here
            return results

To register your plugin, create a pyproject.toml entry point::

    [project.entry-points."aer.plugins"]
    my_plugin = "my_package.module:MySearchPlugin"

Note: All plugins MUST declare the ``supported_products`` class attribute
as a list of product identifier strings (e.g., ["goes-16", "modis"]).
This enables product-based plugin dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import attrs
import pandera.pandas as pa
import pluggy
from pandera.typing import Series
from pandera.typing.geopandas import GeoSeries

if TYPE_CHECKING:
    from aer.spatial import GeomLike, GridCell
    from aer.temporal import TimeRange
    from pandera.typing.geopandas import GeoDataFrame

# Pluggy project identifier - all aer plugins use this namespace
PROJECT_NAME = "aer"

# Marker for plugin supported_collections attribute
SUPPORTED_COLLECTIONS_ATTR = "supported_collections"

# Marker for plugin type (search vs extract)
PLUGIN_TYPE_ATTR = "plugin_type"

# Collection type alias - simple string identifier for satellite products/collections
# Examples: "goes-16", "modis", "viirs", "ABI-L1b-RadF"
Collection = str


def get_supported_collections(plugin: Any) -> list[str]:
    """Extract supported_collections list from a plugin.

    Plugins SHOULD declare ``supported_collections`` as a class attribute
    containing a list of collection identifier strings, but it can also
    be an instance attribute.

    Args:
        plugin: A plugin instance.

    Returns:
        List of collection identifier strings the plugin supports.

    Raises:
        ValueError: If the plugin does not have a valid supported_collections attribute.
    """
    if not hasattr(plugin, SUPPORTED_COLLECTIONS_ATTR):
        raise ValueError(
            f"Plugin {type(plugin).__name__} must declare '{SUPPORTED_COLLECTIONS_ATTR}' "
            f"attribute as a list of collection identifiers"
        )
    collections = cast(list, getattr(plugin, SUPPORTED_COLLECTIONS_ATTR))
    return collections


def get_plugin_type(pm: pluggy.PluginManager, plugin: object) -> set[str]:
    """Infer plugin type from hook implementations using pluggy's get_hookcallers.

    Args:
        pm: The pluggy PluginManager instance.
        plugin: A plugin instance.

    Returns:
        Set containing all hook names implemented by the plugin.
    """
    hookcallers = pm.get_hookcallers(plugin)
    if not hookcallers:
        return set()

    return {hc.name for hc in hookcallers if hasattr(hc, "name")}


# Markers for defining hookspecs and hook implementations
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class SearchResultSchema(pa.DataFrameModel):
    """Schema for search results returned by the `search` hook.

    This schema defines the expected structure of the GeoDataFrame returned
    by search implementations. It includes fields for collection identifiers,
    spatial geometry, temporal information, and any additional metadata needed
    for task preparation and extraction.

    Fields:
        id (str): Unique identifier for the search result (e.g., a product ID).
        collection (str): Identifier for the collection this result belongs to.
        geometry (geometry): Spatial geometry of the result (e.g., footprint).
        start_time (datetime): Start time of the data acquisition.
        end_time (datetime): End time of the data acquisition.
        href (str): URL or reference to the data source for extraction.
    """

    id: Series[pa.String] = pa.Field(nullable=False)
    collection: Series[pa.String] = pa.Field(nullable=False)
    geometry: GeoSeries = pa.Field(nullable=True)
    start_time: Series[pa.DateTime] = pa.Field(nullable=False)
    end_time: Series[pa.DateTime] = pa.Field(nullable=False)
    href: Series[pa.String] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class GriddedSearchResultSchema(SearchResultSchema):
    """Extended schema for search results that includes grid cell information.

    This schema is used when search results are prepared for task extraction
    and need to include information about which grid cells they intersect with.
    """

    grid_cells: Series[list[GridCell]] = pa.Field(nullable=True)


@attrs.frozen
class ExtractionTask:
    """Represents a unit of extraction work.

    The relationship between search_results and target_cells is intentionally
    unconstrained — plugins decide how to interpret it:
    - one task per (result, cell) pair
    - one task per result covering all cells
    - one task per cell covering all results
    - any other grouping that makes sense for the data source
    """

    search_results: GeoDataFrame[GriddedSearchResultSchema]
    extract_params: dict[str, Any] = attrs.Factory(dict)


class AerSpec:
    """Hook specifications for the aer plugin system.

    External packages implement these hooks using ``@hookimpl`` to provide
    custom search, task preparation, and extraction logic.

    Example::

        from aer.plugin import hookimpl, AerSpec
        from pandera.typing.geopandas import GeoDataFrame
        from aer.search import SearchQuery
        class MySearchPlugin:
            @hookimpl
            def search(self, collections: list[str],
                        intersects: GeomLike | None,
                        time_range: TimeRange | None,
                        search_params: dict | None = None) -> GeoDataFrame:
                # Your search implementation here
                return results


        The plugin manager will collect all implementations and call them
            in order (respecting tryfirst/trylast priorities).
    """

    @hookspec
    def search(
        self,
        collections: list[str],
        intersects: GeomLike | None,
        time_range: TimeRange | None,
        search_params: dict[str, Any] | None,
    ) -> GeoDataFrame[SearchResultSchema]:
        """Search for satellite data matching the query.

        Args:
            collections (list[str]): List of collection identifiers to search within.
            intersects (Intersects | None): Spatial geometry to intersect with.
            time_range (TimeRange | None): Temporal range to filter results.
            search_params (dict[str, Any]): Additional parameters for search (e.g., cloud cover, specific metadata filters).

        Returns:
            GeoDataFrame: Search results as a GeoDataFrame with SearchResultSchema.
        """
        ...

    @hookspec
    def prepare_tasks(
        self,
        search_results: GeoDataFrame[GriddedSearchResultSchema],
        extract_params: dict[str, Any] | None = None,
    ) -> list[ExtractionTask]:
        """
        Prepare extraction tasks from search results.

        This hook transforms search results into discrete extraction tasks
        that can be processed independently. It can involve splitting results based on spatial and temporal criteria
        (or auxiliary files), determining intersecting grid cells, and defining output paths for each task.

        Args:
            search_results (GeoDataFrame[GriddedSearchResultSchema]): The search results to prepare tasks from.
            it containe the grid_cells column which is a list of grid cells that intersect with the search result geometry.
            extract_params (dict[str, Any] | None): Additional parameters for task preparation
            (e.g., output directory structure, naming conventions, channels, grouping time windows, etc).
        Returns:
            list[ExtractionTask]: A list of prepared extraction tasks ready for processing.
        Example:
            @hookimpl
            def prepare_tasks(
                self,
                search_results: GeoDataFrame[GriddedSearchResultSchema],
                extract_params: dict[str, Any] | None = None,
            ) -> list[ExtractionTask]:
                # Filter to own collections first
                own_results = search_results[
                    search_results["collection"].isin(self.supported_collections)
                ]
                if own_results.empty:
                    return []

                # Then apply plugin-specific grouping strategy
                time_window = (extract_params or {}).get("time_window", "1h")
                return self._group_by_time_window(own_results, time_window)

            def _group_by_time_window(
                self,
                results: GeoDataFrame[SearchResultSchema],
                window: str,
            ) -> list[ExtractionTask]:
                tasks = []
                for _key, group in results.groupby(pd.Grouper(key="datetime", freq=window)):
                    if not group.empty:
                        tasks.append(ExtractionTask(items=group, window=window))
                return tasks

        """
        ...

    @hookspec
    def extract(self, task: ExtractionTask) -> ExtractionTask:
        """Extract data for a single extraction task.

        Performs the actual data extraction, reprojection to the standard
        grid, and format conversion. Updates the task status upon completion.

        Parameters
        ----------
        task : ExtractionTask
            The extraction task to process, containing search results and extract_params.
        Returns
        -------
        ExtractionTask
            The same task instance with updated status (SUCCESS or FAILED)
            and output paths populated.
        """
        ...
