"""Core pluggy hookspecs for the aer plugin system.

Defines the hook specifications that external packages implement
to provide custom search, task preparation, and extraction logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from pandera.typing.geopandas import GeoDataFrame

    from aer.extract import ExtractionTask  # pyright: ignore[reportMissingImports]
    from aer.search import SearchQuery  # pyright: ignore[reportMissingImports]

# Pluggy project identifier
PROJECT_NAME = "aer"

# Markers for defining hookspecs and hook implementations
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class AerSpec:
    """Pluggy hookspec definitions for aer plugin system.

    External packages implement these hooks using `@hookimpl` to provide
    custom search, task preparation, and extraction logic.

    Example::

        class MySearchPlugin:
            @hookimpl
            def search(self, query: SearchQuery) -> GeoDataFrame:
                # custom search implementation
                ...
    """

    @hookspec
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search for satellite data matching the query.

        Parameters
        ----------
        query :
            A SearchQuery describing the search parameters.

        Returns
        -------
        GeoDataFrame
            Search results validated against SearchResultSchema.
        """
        ...

    @hookspec
    def prepare_tasks(self, query: SearchQuery) -> list[ExtractionTask]:
        """Prepare extraction tasks from search results.

        Parameters
        ----------
        query :
            A SearchQuery describing the search parameters.

        Returns
        -------
        list[ExtractionTask]
            Extraction tasks ready for processing.
        """
        ...

    @hookspec
    def extract(self, task: ExtractionTask) -> ExtractionTask:
        """Extract data for a single extraction task.

        Parameters
        ----------
        task :
            An ExtractionTask with search results and output directory.

        Returns
        -------
        ExtractionTask
            The task with updated status (SUCCESS/FAILED).
        """
        ...
