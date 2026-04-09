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

from typing import TYPE_CHECKING, Any

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

# Marker for plugin supported_products attribute
SUPPORTED_PRODUCTS_ATTR = "supported_products"

# Product type alias - simple string identifier for satellite products
# Examples: "goes-16", "modis", "viirs"
Product = str


def get_supported_products(plugin: Any) -> list[str]:
    """Extract supported_products list from a plugin instance.

    Plugins MUST declare ``supported_products`` as a class attribute
    containing a list of product identifier strings.

    Args:
        plugin: A plugin instance with a supported_products attribute.

    Returns:
        List of product identifier strings the plugin supports.

    Raises:
        ValueError: If the plugin does not have a supported_products attribute.
    """
    if not hasattr(plugin, SUPPORTED_PRODUCTS_ATTR):
        raise ValueError(
            f"Plugin {type(plugin).__name__} must declare supported_products "
            f"class attribute as a list of product identifiers"
        )
    products = getattr(plugin, SUPPORTED_PRODUCTS_ATTR)
    if not isinstance(products, list):
        raise ValueError(
            f"Plugin {type(plugin).__name__}.supported_products must be a list, "
            f"got {type(products).__name__}"
        )
    return products


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


@attrs.frozen
class ExtractionTask:
    """Data class representing an extraction task.
    Search results are split into subsets based on spatial and temporal criteria, and each subset is represented as an ExtractionTask.
    Each subset intersects with grid cells and are extracted to a specific output path.
    """

    search_results: GeoDataFrame[SearchResultSchema]
    intersecting_cells: list[GridCell]
    output_path: str


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
            search_params: Additional parameters for search (e.g., cloud cover, specific metadata filters).

        Returns:
            GeoDataFrame: Search results as a GeoDataFrame with SearchResultSchema.

        Example::

            @hookimpl
            def search(
                self,
                collections: list[str],
                intersects: GeomLike | None,
                time_range: TimeRange | None,
                search_params: dict | None = None,
            ) -> GeoDataFrame:
                # Example search implementation using a hypothetical API client
                api_client = MySatelliteAPIClient()
                results = api_client.search(
                    collections=collections,
                    intersects=intersects,
                    time_range=time_range,
                    cloud_cover=search_params.get("cloud_cover") if search_params else None,
                )
                return results.to_geodataframe(schema=SearchResultSchema)
        """
        ...

    @hookspec
    def prepare_tasks(
        self,
        search_results: GeoDataFrame[SearchResultSchema],
        intersects: GeomLike,
        output_path: str,
    ) -> list[ExtractionTask]:
        """
        Prepare extraction tasks from search results.

        This hook transforms search results into discrete extraction tasks
        that can be processed independently. It can involve splitting results based on spatial and temporal criteria
        (or auxiliary files), determining intersecting grid cells, and defining output paths for each task.

        Args:
            search_results (GeoDataFrame[SearchResultSchema]): The search results to prepare tasks from.
            intersects (GeomLike): The spatial geometry to intersect with for task preparation.
            output_path (str): Base output path where extracted files should be saved.
        Returns:
            list[ExtractionTask]: A list of prepared extraction tasks ready for processing.
        Example:
            @hookimpl
            def prepare_tasks(self, search_results: GeoDataFrame[SearchResultSchema]) -> list[ExtractionTask]:
                tasks = []
                for _, result in search_results.iterrows():
                    # Determine intersecting grid cells for the result geometry
                    intersecting_cells = find_intersecting_cells(result.geometry, intersects)
                    # Define output path for this result                    result_output_path = f"{output_path}/{result.id}"
                    # Create an extraction task                    task = ExtractionTask(
                        search_results=result,
                        intersecting_cells=intersecting_cells,
                        output_path=result_output_path,
                    )
                    tasks.append(task)
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
            Task containing source URL, output path, and processing parameters.
            The task includes the target grid cell in 'overlapping_spatial_extent'.

        Returns
        -------
        ExtractionTask
            The same task instance with updated status (SUCCESS or FAILED)
            and output paths populated.

        Example::

            @hookimpl
            def extract(self, task: ExtractionTask) -> ExtractionTask:
                try:
                    # Download from source
                    data = download(task.source_url)
                    # Reproject to target grid
                    reprojected = reproject(data, task.target_grid)
                    # Save to output
                    save(reprojected, task.output_path)
                    task.status = "SUCCESS"
                    task.output_files = [task.output_path]
                except Exception as e:
                    task.status = "FAILED"
                    task.error = str(e)
                return task
        """
        ...
