from typing import Any, ClassVar, Literal, Protocol

import attrs
import pandas as pd

from aer.plugins.core import load_entrypoint_group
from aer.spatial import GridSpatialExtent
from aer.spectral import Product
from aer.temporal import TimeRange

CellOverlapMode = Literal["contains", "intersects"]


class SearchFunction(Protocol):
    """Protocol for search functions, allowing plugin extensions."""

    def __call__(
        self,
        products: list[Product],
        time_range: TimeRange,
        spatial_extent: GridSpatialExtent | None = None,
        cell_overlap_mode: CellOverlapMode = "contains",
        **kwargs: Any,
    ) -> pd.DataFrame: ...


@attrs.define(frozen=True, slots=True)
class SearchMethod:
    """An extensible registry of satellite data search methods.

    Plugin authors can register new search capabilities by decorating or wrapping
    their functions with this registry.

    Example:
        def my_custom_search(products, time_range, **kwargs):
            return pd.DataFrame(...)

        MY_SEARCH = SearchMethod.register("my_search", my_custom_search)
    """

    name: str
    search_fn: SearchFunction

    _registry: ClassVar[dict[str, "SearchMethod"]] = {}
    _plugins_loaded: ClassVar[bool] = False
    _ENTRYPOINT_GROUP: ClassVar[str] = "aer.plugins.search"

    @classmethod
    def _ensure_plugins_loaded(cls) -> None:
        """Helper to discover plugins once per runtime."""
        if not cls._plugins_loaded:
            load_entrypoint_group(cls._ENTRYPOINT_GROUP)
            cls._plugins_loaded = True

    @classmethod
    def register(cls, name: str, search_fn: SearchFunction) -> "SearchMethod":
        """Register a new search method or return an existing one."""
        if name in cls._registry:
            if cls._registry[name].search_fn is not search_fn:
                # If the name is already taken but the function is different, raise an error.
                # However, if the function is the same, just return the existing method.
                raise ValueError(
                    f"Search method '{name}' is already registered with a different function."
                )
            return cls._registry[name]

        method = cls(name=name, search_fn=search_fn)
        cls._registry[name] = method
        return method

    @classmethod
    def get(cls, name: str) -> "SearchMethod":
        """Retrieve a registered search method by name."""
        cls._ensure_plugins_loaded()
        if name not in cls._registry:
            raise KeyError(f"Search method '{name}' is not registered.")
        return cls._registry[name]

    @classmethod
    def all(cls) -> list["SearchMethod"]:
        """Return all registered search methods."""
        cls._ensure_plugins_loaded()
        return list(cls._registry.values())

    def __call__(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
        """Allow calling the SearchMethod object directly just like a function."""
        return self.search_fn(*args, **kwargs)
