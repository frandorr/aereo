"""Core interface definitions, plugin types, and data models for AEREO.

Defines the GridConfig configuration schemas, Base plugin classes, and task structures
like SearchProvider, Reader, Writer, and Reprojector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Literal,
    Mapping,
    Protocol,
    Sequence,
    cast,
)

from .utils import (
    _import_yaml,
    _load_json_file,
    normalize_geometry_input,
)

if TYPE_CHECKING:
    from aereo.backends import TaskRunner


import attrs
import xarray as xr
from aereo.grid import ExtractionPatch
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field, field_validator
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


class AereoPlugin(BaseModel, ABC):
    """Base class for all AEREO plugins, fully configurable via Pydantic/Hydra."""

    model_config = {"extra": "allow", "frozen": True, "arbitrary_types_allowed": True}


class Reader(AereoPlugin, ABC):
    """Reads raw satellite data and returns it in native CRS as an xarray.Dataset."""

    @abstractmethod
    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        """Read data for the given task.

        Implementations should:
        1. Use ``task.patches`` to spatially subset where possible.
        2. Return dask-backed (lazy) datasets by default for memory efficiency.
        3. Only load data that intersects the task's AOI.
        """
        ...


class Reprojector(AereoPlugin, ABC):
    """Reprojects/resamples an xarray.Dataset to target grid cell definitions."""

    @abstractmethod
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


class Processor(AereoPlugin, ABC):
    """Pure ``xarray.Dataset -> xarray.Dataset`` transform."""

    @abstractmethod
    def __call__(self, ds: xr.Dataset) -> xr.Dataset:
        """Transform *ds* and return a new dataset."""
        ...


class Writer(AereoPlugin, ABC):
    """Serialises an xarray.Dataset to disk."""

    @abstractmethod
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


class BatchWriter(AereoPlugin, ABC):
    """Serialises a dict of lazy patch datasets to disk.

    Unlike the per-patch ``Writer`` which receives one dataset at a time
    (controlled by ``TaskRunner``), a ``BatchWriter`` receives the full
    ``{patch_id: xr.Dataset}`` map from the Reprojector.  This enables:

    * **Batch Dask compute** — merge or schedule multiple patches' graphs together.
    * **Parallel writes** — write patches concurrently using threads/processes.
    * **Memory management** — explicitly drop each patch after write.

    Configure via ``ExtractConfig.write``::

        ExtractConfig(
            read=reader,
            reproject=reprojector,
            write=BatchWriteGeoTIFF(max_workers=4),
        )

    ``TaskRunner`` detects ``isinstance(writer, BatchWriter)`` and hands
    off the full reprojected map instead of iterating per-patch.
    """

    @abstractmethod
    def __call__(
        self,
        patches: Mapping[str, xr.Dataset],
        task: ExtractionTask,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *patches* and return artifact metadata for all written outputs.

        Args:
            patches: Mapping from ``patch.id`` to the (typically lazy) dataset
                aligned to that patch's geobox.
            task: Extraction task containing the patches and configuration.

        Returns:
            GeoDataFrame of written artifacts with ``ArtifactSchema``.
        """
        ...


class ExtractConfig(BaseModel):
    """Declarative configuration for an extraction pipeline."""

    model_config = {"extra": "forbid", "frozen": True}

    read: Reader
    preprocess: Sequence[Processor] = Field(default_factory=list)
    reproject: Reprojector | None = None
    postprocess: Sequence[Processor] = Field(default_factory=list)
    write: Writer | BatchWriter | None = None


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
        ds: xr.Dataset,
    ) -> None:
        """Called after the Reader finishes."""
        pass

    def on_reproject_complete(
        self,
        task: ExtractionTask,
        patch: ExtractionPatch,
        ds: xr.Dataset,
    ) -> None:
        """Called after a single patch has been reprojected."""
        pass

    def on_patch_write_complete(
        self,
        task: ExtractionTask,
        patch: ExtractionPatch,
        artifacts: GeoDataFrame[ArtifactSchema],
    ) -> None:
        """Called after each patch is written."""
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
    """Interface for search providers.

    Common attributes for describing the query:

    collections:
        - Mapping:
            Keys are collection IDs.
            Values are sequences of asset keys to extract.
        - Sequence:
            List of collection IDs, each corresponding to the default
            set of assets for that collection.

    intersects:
        Geometric AOI for the query, as a Shapely geometry object.

    start_datetime:
        Optional start of the temporal window (inclusive), in UTC.

    end_datetime:
        Optional end of the temporal window (inclusive), in UTC.

    search_params:
        Additional keyword arguments to pass to the underlying search
        function (e.g. ``pystac_client.search``, ``earthaccess.search_data``).
    """

    collections: Mapping[str, Sequence[str]] | Sequence[str] | None = None
    intersects: BaseGeometry | dict[str, Any] | str | Path | None = Field(
        default=None,
        description="AOI geometry as a Shapely object, GeoJSON dict, or path to a GeoJSON file.",
    )
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    search_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intersects", mode="before")
    @classmethod
    def _validate_intersects(
        cls, value: BaseGeometry | dict[str, Any] | str | Path | None
    ) -> BaseGeometry | None:
        """Normalize intersects input into a Shapely geometry."""
        return normalize_geometry_input(value)

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
        extract: Declarative configuration of extraction stages.
        output_uri: Destination URI for extracted artifacts (local path or object store).
        patches: Spatial grid patches this task covers.
        grid_config: Tiling specification shared by all tasks in this run.
        patch_config: ML physical dimensions specification.
        aoi: Optional area-of-interest geometry used to clip the extraction region.
        task_context: Observability metadata generated during task preparation.
    """

    assets: GeoDataFrame[AssetSchema]
    extract: ExtractConfig
    output_uri: str
    patches: Sequence[ExtractionPatch]
    grid_config: GridConfig
    patch_config: PatchConfig
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
