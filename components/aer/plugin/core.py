"""Core pluggy hookspecs for the aer plugin system.

Defines the hook specifications that external packages implement
to provide custom search, task preparation, and extraction logic.

Example for external plugin developers::

    from aer.plugin import hookimpl, AerSpec
    from pandera.typing.geopandas import GeoDataFrame
    from aer.search import SearchQuery

    class MySearchPlugin:
        @hookimpl
        def search(self, query: SearchQuery) -> GeoDataFrame:
            # Your search implementation here
            return results

To register your plugin, create a pyproject.toml entry point::

    [project.entry-points."aer.plugins"]
    my_plugin = "my_package.module:MySearchPlugin"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from pandera.typing.geopandas import GeoDataFrame

    from aer.extract import ExtractionTask  # pyright: ignore[reportMissingImports]
    from aer.search import SearchQuery  # pyright: ignore[reportMissingImports]

# Pluggy project identifier - all aer plugins use this namespace
PROJECT_NAME = "aer"

# Markers for defining hookspecs and hook implementations
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class AerSpec:
    """Hook specifications for the aer plugin system.

        External packages implement these hooks using ``@hookimpl`` to provide
    custom search, task preparation, and extraction logic.

        Example::

            class MyPlugin:
                @hookimpl
                def search(self, query: SearchQuery) -> GeoDataFrame:
                    # custom search implementation
                    return results

        The plugin manager will collect all implementations and call them
            in order (respecting tryfirst/trylast priorities).
    """

    @hookspec
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search for satellite data matching the query.

                Parameters
                ----------
                query : SearchQuery
                    Query describing the search parameters (collections, time range,
                    spatial extent, etc.).

                Returns
                -------
                GeoDataFrame
        Search results validated against SearchResultSchema. Must include
        columns: collection, id, datetime, geometry, and any provider-specific
                    metadata.

                Example::

                    @hookimpl
                    def search(self, query: SearchQuery) -> GeoDataFrame:
                        # Fetch data from your API
                        results = my_api.search(
                            collections=query.collections,
                            datetime=query.datetime,
                            intersects=query.intersects,
                        )
                        # Return as GeoDataFrame with SearchResultSchema
                        return GeoDataFrame(results)
        """
        ...

    @hookspec
    def prepare_tasks(self, query: SearchQuery) -> list[ExtractionTask]:
        """Prepare extraction tasks from search results.

                This hook transforms search results into discrete extraction tasks
                that can be processed independently. Useful for batch processing
                or parallel extraction workflows.

                Parameters
                ----------
                query : SearchQuery
                    The original search query (may include result data).

                Returns
                -------
                list[ExtractionTask]
        Extraction tasks ready for processing. Each task should specify
                    the data source, output location, and any processing parameters.

                Example::

                    @hookimpl
                    def prepare_tasks(self, query: SearchQuery) -> list[ExtractionTask]:
                        return [
                            ExtractionTask(
                                source_url=item.s3_url,
                                output_path=f"/data/{item.id}.nc",
                                parameters={"channels": query.channels},
                            )
                            for item in query.results
                        ]
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
