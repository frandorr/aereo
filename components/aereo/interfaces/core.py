"""Core interface definitions, plugin types, and data models for AEREO.

Defines the GridConfig configuration schemas, Base plugin classes, and task structures
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
from pydantic import BaseModel, Field
from shapely.geometry.base import BaseGeometry

GridFilterMode = Literal["intersection", "within", "coverage"]

DEFAULT_CELLS_PER_TASK: int = 50
WGS84_CRS: str = "epsg:4326"

# Default cell parameter for partitioning tasks.

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


def set_dataset_time_bounds(
    ds: AereoDataset, start_time: datetime, end_time: datetime
) -> AereoDataset:
    """Set the start and end time bounds in the dataset's attributes.

    Args:
        ds: The AereoDataset.
        start_time: The start time.
        end_time: The end time.

    Returns:
        The dataset with time bounds set in its attributes.
    """
    ds.attrs["start_time"] = start_time
    ds.attrs["end_time"] = end_time
    return ds


def infer_dataset_time_bounds(ds: AereoDataset) -> AereoDataset:
    """Infer and set the start and end time bounds in the dataset's attributes.

    If a ``time`` coordinate is present, uses its minimum and maximum values.
    Otherwise, leaves the dataset attributes unchanged.

    Args:
        ds: The AereoDataset.

    Returns:
        The dataset with inferred time bounds set in its attributes (if possible).
    """
    import pandas as pd

    if "time" in ds.coords:
        times = ds.coords["time"].values
        if len(times) > 0:
            ds.attrs["start_time"] = pd.Timestamp(times.min()).to_pydatetime()
            ds.attrs["end_time"] = pd.Timestamp(times.max()).to_pydatetime()
    return ds


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
        if isinstance(data, dict):
            data = dict(data)
            data.pop("_target_", None)
        return cls.model_validate(data)


class AereoPlugin(BaseModel, ABC):
    """Base class for all AEREO plugins, fully configurable via Pydantic/Hydra."""

    model_config = {"extra": "allow", "frozen": True, "arbitrary_types_allowed": True}


class Reader(AereoPlugin, ABC):
    """Reads raw satellite data and returns it in native CRS as an AereoDataset."""

    @abstractmethod
    def __call__(self, task: ExtractionTask) -> AereoDataset:
        """Read data for the given task.

        Implementations should:
        1. Use ``task.grid_cells`` to spatially subset where possible.
        2. Return dask-backed (lazy) datasets by default for memory efficiency.
        3. Only load data that intersects the task's AOI.
        """
        ...


class Reprojector(AereoPlugin, ABC):
    """Reprojects/resamples an AereoDataset to a target GeoBox."""

    resolution: float
    padding: int = 0
    conform_to: tuple[int, int] | None = None

    @abstractmethod
    def __call__(self, ds: AereoDataset, geobox: Any) -> AereoDataset:
        """Reproject *ds* to the target *geobox*.

        Args:
            ds: Source dataset in native CRS.
            geobox: Target grid definition (typically ``odc_geo.geobox.GeoBox``).

        Returns:
            Reprojected dataset aligned to *geobox*.
        """
        ...


class Processor(AereoPlugin, ABC):
    """Pure ``AereoDataset -> AereoDataset`` transform."""

    @abstractmethod
    def __call__(self, ds: AereoDataset) -> AereoDataset:
        """Transform *ds* and return a new dataset."""
        ...


class Writer(AereoPlugin, ABC):
    """Serialises an AereoDataset to disk."""

    @abstractmethod
    def __call__(
        self,
        ds: AereoDataset,
        task: ExtractionTask,
        cell: GridCell,
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


class SearchProvider(AereoPlugin, ABC):
    """Interface for search providers."""

    @staticmethod
    def empty_result() -> GeoDataFrame[AssetSchema]:
        """Return an empty GeoDataFrame with AssetSchema columns."""
        import geopandas as gpd

        columns = list(AssetSchema.to_schema().columns.keys())
        if "geometry" not in columns:
            columns.append("geometry")
        gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry")
        return cast(GeoDataFrame[AssetSchema], AssetSchema.validate(gdf))

    @abstractmethod
    def __call__(self) -> GeoDataFrame[AssetSchema]:
        """Execute search based on internal state and return matched assets."""
        ...


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
    collections: list[str] = []
    asset_filters: dict[str, set[str] | None] = {}

    if collections_config is None:
        return collections, asset_filters

    if isinstance(collections_config, Mapping):
        for coll, vars_list in collections_config.items():
            if coll not in collections:
                collections.append(coll)

            if vars_list:
                if "*" in vars_list:
                    asset_filters[coll] = None
                else:
                    asset_filters[coll] = set(str(v) for v in vars_list)
            else:
                asset_filters[coll] = None
    else:
        for coll in collections_config:
            if coll not in collections:
                collections.append(coll)
            asset_filters[coll] = None

    return collections, asset_filters


@attrs.frozen
class ExtractionTask:
    """A class representing a task for extracting data.

    Attributes:
        assets: GeoDataFrame of assets to extract.
        pipeline: Sequence of pipeline stage plugins to execute.
        uri: Destination URI for extracted artifacts.
        grid_cells: Spatial grid cells this task covers.
        grid_config: Tiling specification shared by all tasks in this run.
        aoi: Optional area-of-interest geometry used to clip the extraction region.
        task_context: Observability metadata generated during task preparation.
    """

    assets: GeoDataFrame[AssetSchema]
    pipeline: Sequence[AereoPlugin]
    uri: str
    grid_cells: Sequence[GridCell]
    grid_config: GridConfig
    aoi: BaseGeometry | None = None
    task_context: Mapping[str, Any] = attrs.field(factory=dict)

    def __attrs_post_init__(self) -> None:
        """Validate task invariants after construction.

        Raises:
            ValueError: If assets is empty.
        """
        if self.assets is None or len(self.assets) == 0:
            raise ValueError("assets cannot be empty")

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
            f"pipeline_len={len(self.pipeline)}, "
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
