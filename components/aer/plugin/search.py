"""Abstract base class for all search plugins in the aer plugin system.

Defines the interface contract that all search plugin implementations must
inherit from, ensuring consistent method signatures and enabling IDE support
and static analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pandera.typing.geopandas import GeoDataFrame

if TYPE_CHECKING:
    from aer.search import SearchQuery, SearchResultSchema


class SearchPlugin(ABC):
    """Base class for all search plugins.

    Subclasses must implement the ``search`` method. The method takes a
    :class:`SearchQuery` and returns a validated :class:`GeoDataFrame`
    conforming to :class:`SearchResultSchema`.

    Example::

        class MySearchPlugin(SearchPlugin):
            def search(self, query: SearchQuery) -> GeoDataFrame["SearchResultSchema"]:
                # implementation
                ...
    """

    @abstractmethod
    def search(self, query: SearchQuery) -> GeoDataFrame["SearchResultSchema"]:
        """Execute a search and return validated results.

        Parameters
        ----------
        query :
            A :class:`SearchQuery` describing the search parameters.

        Returns
        -------
        GeoDataFrame["SearchResultSchema"]
            Search results validated against :class:`SearchResultSchema`.
        """
        ...
