"""Core interface definitions, plugin types, and data models for AEREO.

Defines the AereoProfile configuration schemas, PluginParam parameters, and interface classes
like SearchProvider, Reader, Writer, and Reprojector.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Literal,
    Mapping,
    Protocol,
    Self,
    Sequence,
    TYPE_CHECKING,
    TypeAlias,
    cast,
)

if TYPE_CHECKING:
    from aereo.backends import TaskRunner


import attrs
from aereo.grid import GridCell
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field, TypeAdapter
from shapely.geometry.base import BaseGeometry

GridFilterMode = Literal["intersection", "within", "coverage"]

DEFAULT_CELLS_PER_TASK: int = 50
WGS84_CRS: str = "epsg:4326"

# Default raster write parameters used by extract plugins.
DEFAULT_RASTER_DRIVER: str = "GTiff"
DEFAULT_RASTER_COMPRESS: str = "deflate"
DEFAULT_RASTER_ZLEVEL: int = 1
DEFAULT_RASTER_PREDICTOR: int | None = None

_YAML_INSTALL_MSG = (
    "YAML support requires PyYAML. Install it with: pip install 'aereo[yaml]'"
)

_XARRAY_INSTALL_MSG = (
    "xarray support requires xarray. Install it with: pip install 'aereo[xarray]'"
)

_RIOXARRAY_INSTALL_MSG = "rioxarray support requires rioxarray. Install it with: pip install 'aereo[rioxarray]'"


def _import_xarray() -> Any:
    """Import xarray with a clear error message if missing."""
    try:
        import xarray as xr
    except ImportError as exc:
        raise ImportError(_XARRAY_INSTALL_MSG) from exc
    return xr


def _import_rioxarray() -> Any:
    """Import rioxarray with a clear error message if missing."""
    try:
        import rioxarray  # noqa: F401
    except ImportError as exc:
        raise ImportError(_RIOXARRAY_INSTALL_MSG) from exc
    return rioxarray


# ---------------------------------------------------------------------------
# AereoDataset — canonical in-memory intermediate representation
# ---------------------------------------------------------------------------
#
# ``AereoDataset`` is an ``xarray.Dataset`` that carries the following
# conventions so that every pipeline stage (Reader, Processor, Reprojector,
# Writer) can rely on a consistent contract:
#
# 1. CRS metadata is attached via ``rioxarray``::
#
#        ds.rio.crs  # -> rasterio.crs.CRS (or None if unset)
#
# 2. Spatial dimensions are named ``y`` and ``x``.
# 3. Band dimension is named ``band`` (at least size 1).
# 4. Optional temporal dimension is named ``time``.
# 5. Data variables are typically named after the physical quantity
#    (e.g. ``"ndvi"``, ``"B04"``, ``"C01"``).
#
# Whether the underlying data is dask-backed (lazy) or numpy-backed
# (eager) is an implementation detail of each stage.
# ---------------------------------------------------------------------------

#: Canonical in-memory intermediate representation.
#:
#: ``AereoDataset`` is an ``xarray.Dataset`` that carries the following
#: conventions so that every pipeline stage (Reader, Processor, Reprojector,
#: Writer) can rely on a consistent contract:
#:
#: 1. CRS metadata is attached via ``rioxarray``::
#:
#:        ds.rio.crs  # -> rasterio.crs.CRS (or None if unset)
#:
#: 2. Spatial dimensions are named ``y`` and ``x``.
#: 3. Band dimension is named ``band`` (at least size 1).
#: 4. Optional temporal dimension is named ``time``.
#: 5. Data variables are typically named after the physical quantity
#:    (e.g. ``"ndvi"``, ``"B04"``, ``"C01"``).
#:
#: Whether the underlying data is dask-backed (lazy) or numpy-backed
#: (eager) is an implementation detail of each stage.
try:
    import xarray as _xr

    AereoDataset: TypeAlias = _xr.Dataset
except ImportError:
    # Graceful fallback when xarray is not installed — the alias becomes
    # ``Any`` so that type-checking and runtime imports still work.
    AereoDataset = Any  # type: ignore[misc,assignment]


def validate_aereo_dataset(
    ds: Any,
    *,
    require_crs: bool = True,
    require_dims: Sequence[str] | None = ("band", "y", "x"),
) -> None:
    """Validate that *ds* conforms to the AereoDataset conventions.

    Args:
        ds: The dataset to validate.
        require_crs: If True, ensure ``ds.rio.crs`` is set.
        require_dims: If given, ensure all listed dimensions exist.

    Raises:
        ValueError: If any convention is violated.
        ImportError: If ``rioxarray`` is not installed and *require_crs* is True.
    """
    import xarray as xr

    if not isinstance(ds, xr.Dataset):
        raise ValueError(f"Expected xarray.Dataset, got {type(ds).__name__}")

    if require_crs:
        _import_rioxarray()
        # Access the rio accessor to trigger its import side-effects
        if ds.rio.crs is None:
            raise ValueError(
                "AereoDataset must have a CRS set via rioxarray (ds.rio.crs)"
            )

    if require_dims:
        missing = [d for d in require_dims if d not in ds.dims]
        if missing:
            raise ValueError(f"AereoDataset missing required dimensions: {missing}")


def _skip_empty(geom: BaseGeometry | None) -> bool:
    """Return True if *geom* is None or empty."""
    return geom is None or geom.is_empty


def _load_json_file(path: str | Path) -> dict[str, Any]:
    """Load and parse a JSON file."""
    path = Path(path)
    return json.loads(path.read_text())


def _union_all(geom_series) -> BaseGeometry:
    """Return the union of a geometry series, handling API differences."""
    if hasattr(geom_series, "union_all"):
        return geom_series.union_all()
    return geom_series.unary_union


def _import_yaml() -> Any:
    """Import yaml with a clear error message if PyYAML is missing."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(_YAML_INSTALL_MSG) from exc
    return yaml


class PluginParam(BaseModel):
    """Schema for a single plugin parameter.

    Used by both search and extract plugins to declare what parameters
    they accept. Enables auto-generated docs, CLI validation, and UI forms.
    """

    model_config = {"extra": "forbid", "frozen": True}

    name: str
    type: Literal["str", "int", "float", "bool", "choice", "path", "list[str]", "dict"]
    description: str
    default: Any | None = None
    choices: Sequence[str] | None = None
    required: bool = False


def merge_params(
    batch_params: Mapping[str, Any] | None,
    profile_params: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge profile-level params over batch-level params.

    Profile wins on key collision.

    Args:
        batch_params: Base parameters, typically from a batch config.
        profile_params: Override parameters, typically from a profile.
            These take precedence on key collision.

    Returns:
        A new dict containing the merged parameters.
    """
    merged = dict(batch_params or {})
    merged.update(profile_params)
    return merged


class GridConfig(BaseModel):
    """Tiling specification for a single extraction run.

    All profiles in the same ``prepare_for_extraction`` call share one
    ``GridConfig``. This guarantees that every profile extracts the same
    geographic bounding box for a given cell ID.
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
    target_grid_margin: float = Field(
        default=0.0,
        description="Percentage margin added to each cell's nominal size (e.g. 6.8 for 6.8 %).",
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
        return cls.model_validate(data)


class AereoPlugin(ABC):
    """Base class for AEREO plugins"""

    # 1. Define the type hint, but remove the `= None` default.
    supported_collections: Sequence[str]

    # --- NEW: params metadata ---
    required_params: Sequence[PluginParam] = ()
    optional_params: Sequence[PluginParam] = ()

    def __init_subclass__(cls, plugin_abstract: bool = False, **kwargs):
        """Validate plugin subclasses on definition.

        Enforces that subclasses define ``supported_collections`` as a
        non-empty sequence of strings and that ``required_params`` and
        ``optional_params`` contain only PluginParam instances.

        Args:
            plugin_abstract: If True, skip validation (for intermediate ABCs).
            **kwargs: Passed to ``ABC.__init_subclass__``.
        """
        super().__init_subclass__(**kwargs)

        if plugin_abstract:
            return

        # 2. Force the attribute to exist on the subclass
        if not hasattr(cls, "supported_collections"):
            raise TypeError(
                f"Plugin class '{cls.__name__}' must define the 'supported_collections' attribute."
            )

        # 3. Catch the most common developer mistake: using a string instead of a sequence
        # e.g., supported_collections = "GOES-16" instead of ["GOES-16"]
        if isinstance(cls.supported_collections, str):
            raise TypeError(
                f"'{cls.__name__}.supported_collections' must be a Sequence of strings "
                f"(like a list, tuple, or set), but got a single string."
            )

        # 4. Ensure it is a valid sequence type
        if not isinstance(cls.supported_collections, (list, tuple, set)):
            raise TypeError(
                f"'{cls.__name__}.supported_collections' must be a Sequence "
                f"(list, tuple, or set), got {type(cls.supported_collections).__name__}."
            )

        # 5. Validate params metadata
        for p in cls.required_params:
            if not isinstance(p, PluginParam):
                raise TypeError(
                    f"{cls.__name__}.required_params must contain PluginParam instances, "
                    f"got {type(p).__name__}"
                )
        for p in cls.optional_params:
            if not isinstance(p, PluginParam):
                raise TypeError(
                    f"{cls.__name__}.optional_params must contain PluginParam instances, "
                    f"got {type(p).__name__}"
                )

        # 6. Empty sequences are allowed (used by plugins that only support plugin_hints)


# ---------------------------------------------------------------------------
# New pipeline base classes (Phase 1)
# ---------------------------------------------------------------------------


class Reader(AereoPlugin, plugin_abstract=True):
    """Reads raw satellite data and returns it in native CRS as an AereoDataset."""

    @abstractmethod
    def read(
        self,
        task: ExtractionTask,
        params: Mapping[str, Any],
    ) -> AereoDataset:
        """Read data for the given task.

        Implementations should:
        1. Use ``task.grid_cells`` to spatially subset where possible.
        2. Return dask-backed (lazy) datasets by default for memory efficiency.
        3. Only load data that intersects the task's AOI.
        """
        ...


class Reprojector(AereoPlugin, plugin_abstract=True):
    """Reprojects/resamples an AereoDataset to a target GeoBox."""

    @abstractmethod
    def reproject(
        self,
        ds: AereoDataset,
        geobox: Any,
        params: Mapping[str, Any],
    ) -> AereoDataset:
        """Reproject *ds* to the target *geobox*.

        Args:
            ds: Source dataset in native CRS.
            geobox: Target grid definition (typically ``odc_geo.geobox.GeoBox``).
            params: Reprojection parameters (e.g. resampling method).

        Returns:
            Reprojected dataset aligned to *geobox*.
        """
        ...


class Processor(AereoPlugin, plugin_abstract=True):
    """Pure ``AereoDataset -> AereoDataset`` transform.

    Runs either **pre-reproject** (once on native-CRS data) or
    **post-reproject** (per cell on co-registered data).
    """

    stage: Literal["pre_reproject", "post_reproject"] = "post_reproject"

    @abstractmethod
    def process(
        self,
        ds: AereoDataset,
        params: Mapping[str, Any],
    ) -> AereoDataset:
        """Transform *ds* and return a new dataset."""
        ...


class Writer(AereoPlugin, plugin_abstract=True):
    """Serialises an AereoDataset to disk."""

    @abstractmethod
    def write(
        self,
        ds: AereoDataset,
        task: ExtractionTask,
        cell: GridCell,
        params: Mapping[str, Any],
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* for a single grid cell.

        Returns:
            GeoDataFrame of written artifacts with ``ArtifactSchema``.
        """
        ...


class PipelineCallback:
    """Lifecycle hooks for pipeline execution.

    Similar to PyTorch Lightning callbacks, these allow external code to
    observe and react to pipeline stages without modifying the TaskRunner.
    """

    def on_task_start(self, task: ExtractionTask) -> None:
        """Called before any processing begins."""
        pass

    def on_download_complete(self, task: ExtractionTask) -> None:
        """Called after assets have been fetched to local storage.

        In AEREO's stage-based pipeline the download step is typically
        handled inside :meth:`Reader.read`, so this hook fires
        immediately after the reader returns.
        """
        pass

    def on_read_complete(
        self,
        task: ExtractionTask,
        ds: AereoDataset,
    ) -> None:
        """Called after the Reader finishes."""
        pass

    def on_reproject_complete(
        self,
        task: ExtractionTask,
        cell: GridCell,
        ds: AereoDataset,
    ) -> None:
        """Called after a single grid cell has been reprojected."""
        pass

    def on_cell_write_complete(
        self,
        task: ExtractionTask,
        cell: GridCell,
        artifacts: GeoDataFrame[ArtifactSchema],
    ) -> None:
        """Called after each cell is written."""
        pass

    def on_task_complete(
        self,
        task: ExtractionTask,
        artifacts_gdf: GeoDataFrame[ArtifactSchema],
    ) -> None:
        """Called after all cells are processed."""
        pass

    def on_task_failed(self, task: ExtractionTask, error: Exception) -> None:
        """Called when a task fails at any stage."""
        pass


class SearchProvider(AereoPlugin, plugin_abstract=True):
    @staticmethod
    def empty_result() -> GeoDataFrame[AssetSchema]:
        """Return an empty GeoDataFrame with AssetSchema columns.

        Returns:
            An empty validated GeoDataFrame with the correct schema columns,
            including a geometry column.
        """
        import geopandas as gpd

        columns = list(AssetSchema.to_schema().columns.keys())
        if "geometry" not in columns:
            columns.append("geometry")
        gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry")
        return cast(GeoDataFrame[AssetSchema], AssetSchema.validate(gdf))

    @abstractmethod
    def search(
        self,
        profiles: Sequence[AereoProfile],
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        search_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[AssetSchema]:
        """Search for collections data matching the query.

        Args:
            profiles: Sequence of AereoProfile objects defining what to search for.
                Collections and other domain-specific config are read from each
                profile (via ``collections``, ``search_params``, etc.).
            intersects: Optional shapely BaseGeometry to filter results by spatial intersection.
            start_datetime: Optional start datetime to filter results by temporal range.
            end_datetime: Optional end datetime to filter results by temporal range.
            search_params: Additional meta-level parameters for the search (credentials,
                timeouts, etc.). Domain-specific config lives on each AereoProfile.

        Returns:
            A GeoDataFrame of search results, where each row represents a dataset
            or asset that matches the search criteria, and includes metadata such
            as collection, geometry, time range, and any other relevant attributes.
        """
        ...


class _ProfileLoaderMixin:
    """Mixin providing YAML/JSON loading and name validation for profile classes.

    Both :class:`AereoProfile` and :class:`PipelineProfile` share the same
    serialization format (a top-level ``profiles`` list), so this mixin
    eliminates the duplication.
    """

    name: str

    @classmethod
    def from_yaml(cls, path: str | Path) -> list[Self]:
        """Load profiles from a YAML file.

        The file must contain a top-level ``profiles`` key mapping to a list
        of profile dictionaries.
        """
        yaml = _import_yaml()
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls._from_raw(data)

    @classmethod
    def from_yaml_string(cls, text: str) -> list[Self]:
        """Load profiles from a YAML string."""
        yaml = _import_yaml()
        data = yaml.safe_load(text)
        return cls._from_raw(data)

    @classmethod
    def from_json(cls, path: str | Path) -> list[Self]:
        """Load profiles from a JSON file."""
        data = _load_json_file(path)
        return cls._from_raw(data)

    @classmethod
    def from_config_dir(
        cls,
        directory: str | Path,
        *,
        allow_duplicate_names: bool = False,
    ) -> list[Self]:
        """Load all ``*.yaml`` / ``*.yml`` / ``*.json`` files in *directory*."""
        directory = Path(directory)
        profiles: list[Self] = []
        for ext in ("*.yaml", "*.yml", "*.json"):
            for fp in directory.glob(ext):
                profiles.extend(
                    cls.from_yaml(fp) if fp.suffix != ".json" else cls.from_json(fp)
                )
        cls._validate_names(profiles, allow_duplicate_names=allow_duplicate_names)
        return profiles

    @classmethod
    def _from_raw(cls, data: dict[str, Any]) -> list[Self]:
        """Validate and construct profile instances from a raw dict.

        Args:
            data: Raw dictionary containing a ``profiles`` key mapping to a
                list of profile dictionaries.

        Returns:
            A list of validated profile instances.

        Raises:
            ValueError: If data is not a dict or lacks a ``profiles`` key.
        """
        if not isinstance(data, dict) or "profiles" not in data:
            raise ValueError("Config must be a dict with a 'profiles' key.")
        raw_profiles = data["profiles"]
        adapter = TypeAdapter(list[cls])
        profiles = adapter.validate_python(raw_profiles)
        cls._validate_names(profiles)
        return profiles

    @classmethod
    def _validate_names(
        cls,
        profiles: list[Self],
        allow_duplicate_names: bool = False,
    ) -> None:
        """Check that profile names are unique.

        Args:
            profiles: List of profiles to validate.
            allow_duplicate_names: If True, skip the uniqueness check.

        Raises:
            ValueError: If duplicate names are found.
        """
        if allow_duplicate_names:
            return
        seen = set()
        for p in profiles:
            if p.name in seen:
                raise ValueError(f"Duplicate profile name: {p.name!r}")
            seen.add(p.name)


PluginStage: TypeAlias = dict[str, dict[str, Any]]


def unpack_stage(stage: PluginStage) -> tuple[str, dict[str, Any]]:
    """Unpack a PluginStage dictionary into a (plugin_name, params) tuple.

    Raises:
        ValueError: If the stage dict does not contain exactly one key.
    """
    if len(stage) != 1:
        raise ValueError(
            f"PluginStage must have exactly one key (plugin_name), got {len(stage)} keys: {list(stage.keys())}"
        )
    name, params = next(iter(stage.items()))
    return name, params


class AereoProfile(_ProfileLoaderMixin, BaseModel):
    """Ground-truth configuration for a single search + extraction unit.

    Can be constructed in code or loaded from JSON/YAML.

    A profile bundles together:
    - What to search for (``collections`` mapping collection names to variables)
    - How to extract it (``resolution``, ``padding``, ``conform_to``)
    - Which plugins to use for each pipeline stage (``search``, ``read``, ``write``, ``reproject``)
    - Additional processing steps (``pre_processors``, ``post_processors``)

    One profile = one coherent pipeline configuration.
    """

    model_config = {"extra": "forbid", "frozen": True}

    name: str
    resolution: float
    collections: Mapping[str, Sequence[str]] = Field(default_factory=dict)
    padding: int | None = 0
    conform_to: tuple[int, int] | None = None
    derivative: str | None = None

    # Stage-specific configurations (replaces old plugin_hints and *_params)
    search: PluginStage | None = None
    read: PluginStage | None = None
    reproject: PluginStage | None = None
    write: PluginStage | None = None

    # Processor configuration
    pre_processors: Sequence[str | PluginStage] = Field(default_factory=list)
    post_processors: Sequence[str | PluginStage] = Field(default_factory=list)


@attrs.frozen
class ExtractionTask:
    """
    A class representing a task for extracting data.

    Attributes:
        assets: GeoDataFrame of assets to extract. It can group multiple collections
            (for example Imagery + Geolocation). Schema is defined in `aereo.schemas.AssetSchema`.
        profile: The AereoProfile containing target variables and resolution.
        uri: Destination URI for extracted artifacts.
        grid_cells: Spatial grid cells this task covers.
        grid_config: Tiling specification shared by all tasks in this run.
        aoi: Optional area-of-interest geometry used to clip the extraction region.
        task_context: Observability metadata generated during task preparation
            (e.g. ``chunk_id``, ``total_chunks``, ``start_time``).
    """

    assets: GeoDataFrame[AssetSchema]
    profile: AereoProfile
    uri: str
    grid_cells: Sequence[GridCell]
    grid_config: GridConfig
    aoi: BaseGeometry | None = None
    task_context: Mapping[str, Any] = attrs.field(factory=dict)

    def __attrs_post_init__(self) -> None:
        """Validate task invariants after construction.

        Raises:
            ValueError: If assets is empty or if a profile collection is
                missing from the assets DataFrame.
        """
        if self.assets is None or len(self.assets) == 0:
            raise ValueError("assets cannot be empty")

        if self.profile.collections:
            if "collection" in self.assets.columns:
                asset_collections = set(self.assets["collection"])
                for col in self.profile.collections:
                    if col not in asset_collections:
                        raise ValueError(
                            f"Collection '{col}' in collections not found in assets collection column."
                        )

    def __repr__(self) -> str:
        n_assets = len(self.assets) if self.assets is not None else 0

        if self.grid_cells:
            all_cells_str = (
                f"{self.grid_cells[0].__class__.__name__}('"
                + ", ".join([str(c) for c in self.grid_cells])
                + "')"
            )
        else:
            all_cells_str = "[]"

        return (
            f"{self.__class__.__name__}("
            f"n_assets={n_assets}, "
            f"profile='{self.profile.name}', "
            f"resolution={self.profile.resolution}, "
            f"grid_cells={all_cells_str}, "
            f"uri='{self.uri}'"
            f")"
        )


class TaskStaging(Protocol):
    """Protocol for staging serialized tasks to remote storage and loading results.

    Concrete implementations handle upload/download for a specific object-store
    backend (e.g. S3, GCS, Azure Blob).
    """

    bucket: str

    def stage(self, src_dir: Path, job_id: str, task_idx: int) -> str:
        """Upload a serialized task directory and return its URI.

        Args:
            src_dir: Directory containing ``task_assets.parquet`` and
                ``task_meta.json`` produced by :class:`aereo.serialization.TaskSerializer`.
            job_id: Logical job identifier for grouping staged tasks.
            task_idx: Index of the task within the job.

        Returns:
            A URI (e.g. ``s3://bucket/aereo-tasks/{job_id}/{task_idx}/``) that the
            remote worker can use to retrieve the task.
        """
        ...

    def load_artifacts(self, manifest_uri: str) -> GeoDataFrame[ArtifactSchema]:
        """Load artifact results from a manifest URI.

        Args:
            manifest_uri: URI pointing to a manifest produced by the remote worker
                (e.g. ``s3://bucket/results/{job_id}/{task_idx}/manifest.json``).

        Returns:
            A validated ``GeoDataFrame[ArtifactSchema]`` with the extracted artifacts.
        """
        ...

    def upload_artifacts(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        output_prefix: str,
    ) -> dict[str, str]:
        """Upload artifacts and a manifest.

        Args:
            artifacts: GeoDataFrame of extracted artifacts.
            output_prefix: URI prefix where the results should be written.

        Returns:
            A dictionary containing the ``manifest_uri`` of the uploaded manifest.
        """
        ...

    def result_prefix(self, job_id: str, task_idx: int) -> str:
        """Return the URI prefix where the remote worker should write results.

        Args:
            job_id: Logical job identifier.
            task_idx: Index of the task within the job.

        Returns:
            A URI prefix (e.g. ``s3://bucket/results/{job_id}/{task_idx}/``).
        """
        ...


class ExecutionBackend(Protocol):
    """Protocol for pluggable task execution backends.

    Backends decide **where** and **how** a batch of :class:`ExtractionTask`
    objects are executed.  Local backends use the supplied *runner* directly;
    remote backends may serialize tasks and dispatch to external workers.
    """

    def run_tasks(
        self,
        tasks: Sequence[ExtractionTask],
        runner: TaskRunner | None = None,
    ) -> Iterable[GeoDataFrame[ArtifactSchema]]:
        """Execute *tasks* and yield or return their results.

        Because the return type is :class:`Iterable`, implementations are free
        to process tasks asynchronously and yield results as they arrive,
        enabling streaming consumption by the caller.

        Args:
            tasks: The extraction tasks to run.
            runner: A client-side :class:`TaskRunner` that knows how to execute
                a single task using the correct local plugin.
        """
        ...
