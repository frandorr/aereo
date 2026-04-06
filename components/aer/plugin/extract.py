"""Pluggy hookspec for extract operations.

Defines the contract that extract plugin implementations must fulfill.
External packages provide concrete implementations via `@hookimpl`.

Example::

    class MyExtractPlugin:
        @hookimpl
        def extract(self, task: ExtractionTask) -> ExtractionTask:
            # custom extraction logic
            ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pluggy

if TYPE_CHECKING:
    from aer.extract import ExtractionTask  # pyright: ignore[reportMissingImports]

hookspec = pluggy.HookspecMarker("aer")


class ExtractSpec:
    """Hookspec for extract operations.

    Implementations receive an ExtractionTask and return it with updated
    status after performing extraction.
    """

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
