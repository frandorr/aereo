"""Pluggy hookspec for prepare_tasks operations.

Defines the contract that prepare_tasks plugin implementations must fulfill.
External packages provide concrete implementations via `@hookimpl`.

Example::

    class MyPrepareTasksPlugin:
        @hookimpl
        def prepare_tasks(self, query: SearchQuery) -> list[ExtractionTask]:
            # custom task preparation logic
            ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from aer.extract import ExtractionTask  # pyright: ignore[reportMissingImports]
    from aer.search import SearchQuery  # pyright: ignore[reportMissingImports]

hookspec = pluggy.HookspecMarker("aer")


class PrepareTasksSpec:
    """Hookspec for prepare_tasks operations.

    Implementations receive a SearchQuery and return a list of ExtractionTasks
    ready for processing.
    """

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
