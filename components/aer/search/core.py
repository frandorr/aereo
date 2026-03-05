import importlib.metadata
from typing import Any, ClassVar, Literal, Protocol

import attrs
import geopandas as gpd
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoDataFrame, GeoSeries
from structlog import get_logger

from aer.spatial import GridSpatialExtent
from aer.spectral import Product
from aer.temporal import TimeRange

logger = get_logger()


class SearchResultSchema(pa.DataFrameModel):  # type: ignore[misc]
    """Schema defining the minimum required columns for search results.

    Extra columns (e.g. ``grid_cells``) are allowed thanks to
    ``strict = False``.  Types are coerced so that, for example, a plugin
    returning ``size_mb`` as an integer will have it automatically cast to
    ``float``.

    The ``geometry`` column holds the granule footprint polygon (nullable
    because some products like GOES may not carry granule-level geometry).
    """

    product_name: Series[pa.String] = pa.Field(nullable=True)
    granule_id: Series[pa.String] = pa.Field(nullable=True)
    concept_id: Series[pa.String] = pa.Field(nullable=True)
    start_time: Series[pa.DateTime] = pa.Field(nullable=True)
    end_time: Series[pa.DateTime] = pa.Field(nullable=True)
    s3_url: Series[pa.String] = pa.Field(nullable=True)
    https_url: Series[pa.String] = pa.Field(nullable=True)
    size_mb: Series[float] = pa.Field(nullable=True)
    geometry: GeoSeries[Any] = pa.Field(nullable=True)

    class Config:
        strict = False
        coerce = True


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
    ) -> gpd.GeoDataFrame: ...


@attrs.define(frozen=True, slots=True)
class SearchMethod:
    """An extensible registry of satellite data search methods.

    Plugin authors can register new search capabilities by decorating or wrapping
    their functions with this registry.

    Example:
        def my_custom_search(products, time_range, **kwargs):
            return gpd.GeoDataFrame(...)

        MY_SEARCH = SearchMethod.register("my_search", my_custom_search)
    """

    name: str
    search_fn: SearchFunction

    _registry: ClassVar[dict[str, "SearchMethod"]] = {}
    _plugins_loaded: ClassVar[bool] = False
    _ENTRYPOINT_GROUP: ClassVar[str] = "aer.plugins.search"

    @classmethod
    def _ensure_plugins_loaded(cls) -> None:
        if not cls._plugins_loaded:
            # Query entry points using the standard package metadata method!
            entry_points = importlib.metadata.entry_points(group=cls._ENTRYPOINT_GROUP)

            for entry in entry_points:
                try:
                    search_fn = (
                        entry.load()
                    )  # This now returns the search_earthaccess function
                    # Use the entry.name ("earthaccess") from pyproject.toml as the source of truth
                    cls.register(name=entry.name, search_fn=search_fn)
                except Exception as exc:
                    logger.error(
                        "Failed to load plugin", plugin=entry.name, error=str(exc)
                    )

            cls._plugins_loaded = True

    @classmethod
    def register(cls, name: str, search_fn: SearchFunction | None = None) -> Any:
        """Register a new search method or return an existing one."""

        def decorator(fn: SearchFunction) -> "SearchMethod":
            if name in cls._registry:
                if cls._registry[name].search_fn is not fn:
                    raise ValueError(
                        f"Search method '{name}' is already registered with a different function."
                    )
                return cls._registry[name]

            method = cls(name=name, search_fn=fn)
            cls._registry[name] = method
            return method

        if search_fn is None:
            return decorator
        return decorator(search_fn)

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

    def __call__(
        self,
        products: list[Product],
        time_range: TimeRange,
        spatial_extent: GridSpatialExtent | None = None,
        cell_overlap_mode: CellOverlapMode = "contains",
        **kwargs: Any,
    ) -> GeoDataFrame[SearchResultSchema]:
        """Allow calling the SearchMethod object directly just like a function.

        The returned GeoDataFrame is validated against ``SearchResultSchema``.
        Missing required columns or un-coercible types raise
        ``pandera.errors.SchemaError``.
        """
        gdf = self.search_fn(
            products=products,
            time_range=time_range,
            spatial_extent=spatial_extent,
            cell_overlap_mode=cell_overlap_mode,
            **kwargs,
        )
        return GeoDataFrame[SearchResultSchema](gdf)
