"""Core interface definitions, plugin types, and data models for AEREO.

Defines the GridConfig configuration schemas, Base plugin classes, and task structures
like SearchProvider, Reader, Writer, and Reprojector.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Literal,
    Mapping,
    Protocol,
    Sequence,
    cast,
    runtime_checkable,
)

from pydantic import BeforeValidator

from .utils import (
    _import_yaml,
    _load_json_file,
    resolve_callable,
)

if TYPE_CHECKING:
    from aereo.pipeline import ExtractionJob


import attrs
import xarray as xr
from aereo.grid import ExtractionPatch
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field
from shapely.geometry.base import BaseGeometry

GridFilterMode = Literal["intersection", "within", "coverage"]

DEFAULT_CELLS_PER_TASK: int = 50
WGS84_CRS: str = "epsg:4326"

# Default cell parameter for partitioning tasks.


class GridConfig(BaseModel):
    """Configuration for partitioning an AOI into a regular grid of cells.

    ``GridConfig`` controls how the area of interest is diced into
    mathematical geographic partitions (grid cells): their size, overlap,
    and which cells are kept after filtering against the AOI.
    """

    model_config = {"extra": "forbid", "frozen": True}

    target_grid_dist: int | None = Field(
        default=None,
        description="Grid cell size in metres. None means the user must choose explicitly (no defaults).",
    )
    target_grid_overlap: bool = Field(
        default=False,
        description="Whether grid cells overlap.",
    )
    grid_filter_mode: GridFilterMode = Field(
        default="intersection",
        description="How to filter grid cells against the AOI.",
    )
    min_coverage: float = Field(
        default=0.0,
        description="Minimum AOI coverage ratio required when grid_filter_mode='coverage'.",
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GridConfig":
        """Load a GridConfig from a YAML file.

        The file may contain either a top-level ``grid_config`` key mapping
        to a grid config dictionary, or the grid config fields directly.
        """
        yaml = _import_yaml()
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls._from_raw(data)

    @classmethod
    def from_yaml_string(cls, text: str) -> "GridConfig":
        """Load a GridConfig from a YAML string."""
        yaml = _import_yaml()
        data = yaml.safe_load(text)
        return cls._from_raw(data)

    @classmethod
    def from_json(cls, path: str | Path) -> "GridConfig":
        """Load a GridConfig from a JSON file."""
        data = _load_json_file(path)
        return cls._from_raw(data)

    @classmethod
    def _from_raw(cls, data: dict[str, Any]) -> "GridConfig":
        """Validate and construct a GridConfig from a raw dict.

        Supports the ``grid_config`` nested-key convention used by YAML files.

        Args:
            data: Raw dictionary, possibly containing a ``grid_config`` key.

        Returns:
            A validated GridConfig instance.

        Raises:
            ValueError: If data is not a dict.
        """
        if not isinstance(data, dict):
            raise ValueError("GridConfig data must be a dict.")
        if "grid_config" in data:
            data = data["grid_config"]
        if isinstance(data, dict):
            data = dict(data)
            data.pop("_target_", None)
        return cls.model_validate(data)


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

AnyCallable = Annotated[Callable[..., Any], BeforeValidator(resolve_callable)]


@runtime_checkable
class Reader(Protocol):
    """Reads raw satellite data and returns it in native CRS as an xarray.Dataset."""

    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        """Read data for the given task.

        Implementations should:
        1. Use ``task.patches`` to spatially subset where possible.
        2. Return dask-backed (lazy) datasets by default for memory efficiency.
        3. Only load data that intersects the task's AOI.
        """
        ...


@runtime_checkable
class Reprojector(Protocol):
    """Reprojects/resamples an xarray.Dataset to target grid cell definitions."""

    def __call__(self, ds: xr.Dataset, task: ExtractionTask) -> dict[str, xr.Dataset]:
        """Reproject *ds* for every patch in *task*.

        Args:
            ds: Source dataset in native CRS.
            task: Extraction task containing the patches to reproject.

        Returns:
            Mapping from ``patch.id`` to the reprojected ``xr.Dataset`` aligned to
            that patch's geobox.
        """
        ...


@runtime_checkable
class Processor(Protocol):
    """Pure ``xarray.Dataset -> xarray.Dataset`` transform."""

    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Transform *ds* and return a new dataset."""
        ...


@runtime_checkable
class Writer(Protocol):
    """Serialises an xarray.Dataset to disk."""

    def __call__(
        self,
        ds: xr.Dataset,
        task: ExtractionTask,
        patch: ExtractionPatch,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* for a single extracted patch.

        Returns:
            GeoDataFrame of written artifacts with ``ArtifactSchema``.
        """
        ...


class ExtractConfig(BaseModel):
    """Declarative configuration for an extraction pipeline."""

    model_config = {"extra": "forbid", "frozen": True, "arbitrary_types_allowed": True}

    read: AnyCallable
    preprocess: Sequence[AnyCallable] = Field(default_factory=list)
    reproject: AnyCallable | None = None
    postprocess: Sequence[AnyCallable] = Field(default_factory=list)
    write: AnyCallable | None = None


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
            job: Parent extraction job supplying grid, patch, output, and stage
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
    """A class representing a task for extracting data.

    Attributes:
        assets: GeoDataFrame of assets to extract.
        patches: Spatial grid patches this task covers.
        aoi: Optional area-of-interest geometry used to clip the extraction region.
        task_context: Observability metadata generated during task preparation.
        job: Parent ``ExtractionJob`` that owns this task's extraction configuration.
    """

    assets: GeoDataFrame[AssetSchema]
    patches: Sequence[ExtractionPatch]
    job: ExtractionJob
    aoi: BaseGeometry | None = None
    task_context: Mapping[str, Any] = attrs.field(factory=dict)

    @property
    def extract(self) -> ExtractConfig:
        """Declarative configuration of extraction stages (delegated to ``job``)."""
        return self.job.extract

    @property
    def output_uri(self) -> str:
        """Destination URI for extracted artifacts (delegated to ``job``)."""
        return self.job.output_uri

    @property
    def grid_config(self) -> GridConfig:
        """Tiling specification shared by all tasks in this run (delegated to ``job``)."""
        return self.job.grid_config

    @property
    def patch_config(self) -> PatchConfig:
        """ML physical dimensions specification (delegated to ``job``)."""
        return self.job.patch_config

    @property
    def derivative(self) -> str | None:
        """Derivative pipeline name, or ``None`` for raw extraction (delegated to ``job``)."""
        return self.job.derivative

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

        if self.patches:
            all_cells_str = (
                f"{self.patches[0].__class__.__name__}('"
                + ", ".join([str(p) for p in self.patches])
                + "')"
            )
        else:
            all_cells_str = "[]"

        extract_len = (
            1
            + len(self.extract.preprocess)
            + len(self.extract.postprocess)
            + (1 if self.extract.reproject else 0)
            + (1 if self.extract.write else 0)
        )

        return (
            f"{self.__class__.__name__}("
            f"n_assets={n_assets}, "
            f"extract_len={extract_len}, "
            f"patches={all_cells_str}, "
            f"output_uri='{self.output_uri}'"
            f")"
        )
