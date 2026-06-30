"""Core interface definitions, plugin types, and data models for AEREO.

Defines configuration schemas, plugin protocols, and task structures
like SearchProvider, Reader, Writer, Reprojector, and Processor.
"""

from __future__ import annotations

from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Mapping,
    Protocol,
    Sequence,
    cast,
    runtime_checkable,
)

if TYPE_CHECKING:
    from aereo.pipeline import ExtractionJob

import attrs
import xarray as xr
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field
from shapely.geometry.base import BaseGeometry

DEFAULT_CELLS_PER_TASK: int = 50
WGS84_CRS: str = "epsg:4326"


class PatchConfig(BaseModel):
    """Configuration for physical ML patch extraction dimensions.

    This governs the physical map-math to transform a geographic grid
    cell into a rigid bounding box suitable for tensor extraction.
    """

    model_config = {"extra": "forbid", "frozen": True}

    resolution: float = Field(
        description="Spatial resolution of the extracted patch in metres."
    )
    padding: int = Field(
        default=0,
        description="Additional padding pixels added to the extracted bounding box.",
    )
    margin: float = Field(
        default=0.0,
        description="Percentage margin added to the patch's nominal size (e.g. 5.0 for 5%).",
    )
    conform_to: tuple[int, int] | None = Field(
        default=None,
        description="Force the output tensor to this exact shape (H, W).",
    )

    @classmethod
    def _from_raw(cls, data: dict[str, Any]) -> "PatchConfig":
        if not isinstance(data, dict):
            raise ValueError("PatchConfig data must be a dict.")
        if "patch_config" in data:
            data = data["patch_config"]
        if isinstance(data, dict):
            data = dict(data)
            data.pop("_target_", None)
        return cls.model_validate(data)


AereoPlugin = Any


@runtime_checkable
class Reader(Protocol):
    """Reads source files and returns an ``xr.Dataset``."""

    def __call__(self, *args: Any, **kwargs: Any) -> xr.Dataset:
        """Read source filenames/assets and return a dataset.

        The orchestrator passes the filename list derived from
        ``task.assets["href"]`` and any bound kwargs. Additional configuration
        (bands, CRS, resolution, STAC items, etc.) is supplied through
        ``**kwargs`` or via ``functools.partial``.
        """
        ...


@runtime_checkable
class Processor(Protocol):
    """Pure ``xarray.Dataset -> xarray.Dataset`` transform."""

    def __call__(self, *args: Any, **kwargs: Any) -> xr.Dataset:
        """Transform a dataset and return a new dataset."""
        ...


@runtime_checkable
class Reprojector(Protocol):
    """Reprojects/resamples an ``xarray.Dataset`` to a target definition."""

    def __call__(self, *args: Any, **kwargs: Any) -> xr.Dataset:
        """Reproject a dataset and return a new dataset.

        The orchestrator may inject ``geobox`` when ``ExtractionJob.reproject_mode``
        is ``"grid"``. Otherwise the caller is responsible for providing target
        parameters such as ``crs`` and ``resolution`` through ``**kwargs``.
        """
        ...


@runtime_checkable
class Writer(Protocol):
    """Serialises an ``xarray.Dataset`` to a single file."""

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Write a dataset to a path and return the written path.

        The orchestrator is responsible for constructing the path (e.g. EOIDS
        layout) and for splitting time dimensions before calling the writer. The
        writer receives a dataset without a ``time`` dimension and returns the
        path it wrote to.
        """
        ...


@runtime_checkable
class TaskBuilder(Protocol):
    """Builds a sequence of extraction tasks from search results.

    Task builders are job-level plugins: they run once per job, grouping and
    chunking search-result assets into ``ExtractionTask`` objects that the
    per-task extraction pipeline can execute.
    """

    def __call__(
        self,
        search_results: GeoDataFrame[AssetSchema],
        job: ExtractionJob,
    ) -> Sequence[ExtractionTask]:
        """Build extraction tasks from *search_results* using *job* configuration.

        Args:
            search_results: GeoDataFrame of assets returned by a search provider.
            job: Parent extraction job supplying grid, output, and reader/writer
                configuration.

        Returns:
            A sequence of prepared extraction tasks.
        """
        ...


@runtime_checkable
class SearchProvider(Protocol):
    """Interface for search providers.

    Search providers are callables that receive collection, spatial, and
    temporal constraints and return a GeoDataFrame of matched assets.
    """

    def __call__(
        self,
        collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        **kwargs: Any,
    ) -> GeoDataFrame[AssetSchema]:
        """Execute search based on the provided constraints.

        Args:
            collections: Mapping of collection -> asset keys, or list of collections.
            intersects: AOI geometry.
            start_datetime: Optional start of temporal window.
            end_datetime: Optional end of temporal window.
            **kwargs: Implementation-specific parameters (e.g. ``stac_api_url``).

        Returns:
            GeoDataFrame of matched assets.
        """
        ...


def empty_asset_result() -> GeoDataFrame[AssetSchema]:
    """Return an empty GeoDataFrame with AssetSchema columns."""
    import geopandas as gpd

    columns = list(AssetSchema.to_schema().columns.keys())
    if "geometry" not in columns:
        columns.append("geometry")
    gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry")
    return cast(GeoDataFrame[AssetSchema], AssetSchema.validate(gdf))


def build_collection_asset_filters(
    collections_config: Mapping[str, Sequence[str]] | Sequence[str] | None,
) -> tuple[list[str], dict[str, set[str] | None]]:
    """Derive collection list and per-collection asset filters from configuration mapping or sequence.

    Args:
        collections_config: Mapping of collection -> list of asset/channel keys,
            or sequence of collection names.

    Returns:
        A ``(collections, asset_filters)`` tuple.
    """
    if collections_config is None:
        return [], {}

    if isinstance(collections_config, Mapping):
        asset_filters: dict[str, set[str] | None] = {}
        for coll, vars_list in collections_config.items():
            if vars_list and "*" not in vars_list:
                asset_filters[coll] = set(str(v) for v in vars_list)
            else:
                asset_filters[coll] = None
        return list(collections_config.keys()), asset_filters

    collections = list(dict.fromkeys(collections_config))
    return collections, {coll: None for coll in collections}


@attrs.frozen
class ExtractionTask:
    """A serializable unit of extraction work.

    Attributes:
        id: Stable identifier generated by the task builder.
        assets: GeoDataFrame of source assets to read. The orchestrator derives
            filenames from ``assets["href"]``.
        job: Parent ``ExtractionJob`` that owns this task's extraction configuration.
        task_context: Optional metadata (e.g. ``chunk_id``, ``total_chunks``)
            carried with the task for tracing and logging.
    """

    id: str
    assets: GeoDataFrame[AssetSchema]
    job: ExtractionJob
    task_context: dict[str, Any] = attrs.field(factory=dict)

    @property
    def read(self) -> Reader:
        """Reader callable delegated to ``job``."""
        return self.job.read

    @property
    def write(self) -> Writer | None:
        """Writer callable delegated to ``job`` (may be ``None``)."""
        return self.job.write

    @property
    def output_uri(self) -> str:
        """Destination URI for extracted artifacts (delegated to ``job``)."""
        return self.job.output_uri

    @property
    def grid_dist(self) -> int:
        """Grid cell size in metres shared by all tasks in this run (delegated to ``job``)."""
        return self.job.grid_dist

    def __attrs_post_init__(self) -> None:
        """Validate task invariants after construction.

        Raises:
            ValueError: If assets is empty or assets have mixed native CRS.
        """
        if self.assets is None or len(self.assets) == 0:
            raise ValueError("assets cannot be empty")

        if any(col == "crs" for col in self.assets.columns):
            if bool(self.assets["crs"].isna().any()):
                raise ValueError(
                    "assets['crs'] contains null values. "
                    "Either populate crs for all assets or omit the column entirely."
                )
            unique_crs = self.assets["crs"].unique()
            if len(unique_crs) > 1:
                raise ValueError(
                    "All assets in an ExtractionTask must share the same native CRS, "
                    f"but found: {sorted(unique_crs)}."
                )

    def __repr__(self) -> str:
        n_assets = len(self.assets) if self.assets is not None else 0
        return (
            f"{self.__class__.__name__}("
            f"id={self.id!r}, "
            f"n_assets={n_assets}, "
            f"read={self.read is not None}, "
            f"write={self.write is not None}, "
            f"output_uri='{self.output_uri}'"
            f")"
        )
