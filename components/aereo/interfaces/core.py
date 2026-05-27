from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Iterable,
    Literal,
    Mapping,
    Protocol,
    Self,
    Sequence,
    TYPE_CHECKING,
    cast,
)

if TYPE_CHECKING:
    from aereo.backends import TaskRunner


import attrs
from aereo.grid import GridCell
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field, ImportString, TypeAdapter
from shapely.geometry.base import BaseGeometry

GridFilterMode = Literal["intersection", "within", "coverage"]

DEFAULT_CELLS_PER_TASK: int = 50
WGS84_CRS: str = "epsg:4326"

_YAML_INSTALL_MSG = (
    "YAML support requires PyYAML. Install it with: pip install 'aer[yaml]'"
)


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
    type: Literal["str", "int", "float", "bool", "choice", "path", "list[str]"]
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


class Downloader(Protocol):
    """Callable that downloads a URL to a local path."""

    def __call__(self, url: str, local_path: Path) -> None:
        """Download *url* to *local_path*."""
        ...


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


class SearchProvider(AereoPlugin, plugin_abstract=True):
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


class AereoProfile(BaseModel):
    """Ground-truth configuration for a single search + extraction unit.

    Can be constructed in code or loaded from JSON/YAML. The *downloader*
    field accepts either a live callable or a dotted import path string.

    A profile bundles together:
    - What to search for (``collections`` mapping collection names to variables)
    - How to extract it (``resolution``, ``padding``, ``conform_to``)
    - Which plugins to use (``plugin_hints``)
    - How to download assets (``downloader``)

    Plugin-specific settings (e.g. ``reader``, ``calibration``, ``resampling``)
    belong in ``extract_params`` or ``search_params`` rather than top-level
    fields.

    One profile = one coherent pipeline configuration.
    """

    model_config = {"extra": "forbid", "frozen": True}

    name: str
    resolution: float
    collections: Mapping[str, Sequence[str]] = Field(default_factory=dict)
    padding: int | None = 0
    conform_to: tuple[int, int] | None = None
    plugin_hints: Mapping[str, str] = Field(default_factory=dict)
    downloader: ImportString[Callable[[str, Path], None]] | None = None
    search_params: Mapping[str, Any] = Field(default_factory=dict)
    extract_params: Mapping[str, Any] = Field(default_factory=dict)

    def __getstate__(self) -> dict[str, Any]:
        """Serialize to a dict, converting live callables to dotted paths.

        Non-importable callables (lambdas, nested functions, bound methods)
        are replaced with ``None`` so that pickling never crashes.
        """
        try:
            state = self.model_dump(mode="json")
        except Exception:
            # Fallback: dump field-by-field, stringifying anything non-JSON
            state = {}
            for name in self.__class__.model_fields:
                try:
                    val = getattr(self, name)
                    # ImportString callables serialize to their dotted path
                    state[name] = json.loads(json.dumps(val, default=str))
                except Exception:
                    state[name] = None

        downloader_path = state.get("downloader")
        if downloader_path is not None:
            try:
                ta = TypeAdapter(ImportString[Callable[[str, Path], None]] | None)
                ta.validate_python(downloader_path)
            except Exception:
                state["downloader"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Reconstruct from a validated dict."""
        obj = self.__class__.model_validate(state)
        object.__setattr__(self, "__dict__", obj.__dict__)

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

    # --- helpers ---

    @classmethod
    def _from_raw(cls, data: dict[str, Any]) -> list[Self]:
        """Validate and construct AereoProfile instances from a raw dict.

        Args:
            data: Raw dictionary containing a ``profiles`` key mapping to a
                list of profile dictionaries.

        Returns:
            A list of validated AereoProfile instances.

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


# Backward-compat alias — will be removed in a later task.
ExtractionProfile = AereoProfile


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


class Extractor(AereoPlugin, plugin_abstract=True):
    """Base class for AEREO extraction plugins.

    Subclasses must implement ``extract()``. Grid parameters are no longer
    declared as plugin properties; they are supplied at preparation time via
    ``GridConfig``.
    """

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        grid_config: GridConfig,
        target_aoi: BaseGeometry | None = None,
        uri: str | None = None,
        profiles: Sequence[AereoProfile] | None = None,
        cells_per_task: int = DEFAULT_CELLS_PER_TASK,
        extractor_hint: str | None = None,
        init_params: Mapping[str, Any] | None = None,
    ) -> Sequence[ExtractionTask]:
        """Prepare extraction tasks by grouping assets and chunking grid cells.

        Groups search results by profile and start time, generates grid cells,
        optionally filters them by AOI coverage, then chunks into tasks.

        Args:
            search_results: GeoDataFrame of assets from the search phase.
            grid_config: Tiling specification shared by all tasks.
            target_aoi: Optional geometry to clip the extraction region.
            uri: Destination URI prefix for extracted artifacts.
            profiles: Profiles defining what to extract. Must contain at least one.
            cells_per_task: Maximum number of grid cells per task chunk.
            extractor_hint: Optional hint string forwarded to task context.
            init_params: Optional parameters added to each task's context.

        Returns:
            A sequence of ExtractionTask objects ready for execution.

        Raises:
            ValueError: If uri is None, no profiles are provided, or
                grid_dist is not set in grid_config.
        """
        if uri is None:
            raise ValueError(
                "Default prepare_for_extraction requires uri to be defined."
            )

        if not profiles:
            raise ValueError(
                "Default prepare_for_extraction requires at least one profile to be defined."
            )

        grid_dist = grid_config.target_grid_dist
        if grid_dist is None:
            raise ValueError(
                "GridConfig.target_grid_dist must be an explicit integer (e.g. 50_000)."
            )
        grid_overlap = grid_config.target_grid_overlap
        target_grid_margin = grid_config.target_grid_margin
        grid_filter_mode = grid_config.grid_filter_mode
        min_coverage = grid_config.min_coverage

        import geopandas as gpd
        from aereo.grid import GridDefinition

        grid_def = GridDefinition(d=grid_dist, overlap=grid_overlap)

        tasks = []

        # 1. Iterate over each profile
        for profile in profiles:
            resolution = int(profile.resolution)
            padding = profile.padding or 0

            # Filter assets by profile collections if specified
            if profile.collections:
                profile_assets = search_results[
                    search_results["collection"].isin(list(profile.collections.keys()))
                ].copy()
            else:
                profile_assets = search_results.copy()

            if profile_assets.empty:
                continue

            # First pass: collect all cells across time groups for this profile
            profile_cell_groups: list[tuple[Any, GeoDataFrame, list[GridCell]]] = []

            # 2. Group by exact start_time
            for start_time, time_group in profile_assets.groupby("start_time"):
                # 3. Determine base geometry union of the group
                group_geom = _union_all(time_group.geometry)

                if _skip_empty(group_geom):
                    continue

                # 4. Intersect with target_aoi if provided
                if target_aoi is not None:
                    aoi_geom = target_aoi.intersection(group_geom)
                else:
                    aoi_geom = group_geom

                if _skip_empty(aoi_geom):
                    continue

                # 5. Generate grid cells specifically for the intersected geometry
                all_cells = list(grid_def.generate_grid_cells(aoi_geom))
                if not all_cells:
                    continue

                # 5b. Optional grid cell filtering by asset coverage
                _grid_filter_mode = str(grid_filter_mode).lower()
                if _grid_filter_mode != "intersection":
                    filtered_cells = []
                    for cell in all_cells:
                        cell_geom = cell.geom
                        if _grid_filter_mode == "within":
                            if aoi_geom.contains(cell_geom):
                                filtered_cells.append(cell)
                        elif _grid_filter_mode == "coverage":
                            intersection = cell_geom.intersection(aoi_geom)
                            coverage = (
                                intersection.area / cell_geom.area
                                if cell_geom.area > 0
                                else 0.0
                            )
                            if coverage >= min_coverage:
                                filtered_cells.append(cell)
                        else:
                            raise ValueError(
                                f"Unknown grid_filter_mode: {_grid_filter_mode}. "
                                f"Use 'intersection', 'within', or 'coverage'."
                            )
                    all_cells = filtered_cells
                    if not all_cells:
                        continue

                profile_cell_groups.append(
                    (start_time, cast(GeoDataFrame, time_group), all_cells)
                )

            if not profile_cell_groups:
                continue

            # Compute common shape if conforming is enabled for this profile
            conform_to_shape: tuple[int, int] | None = None
            if profile.conform_to is not None:
                conform_to_shape = profile.conform_to

            # Pre-warm and cache area_def results for all cells to avoid
            # redundant computation in the second pass.
            area_def_cache: dict[GridCell, Any] = {}
            for _, _, cells in profile_cell_groups:
                for cell in cells:
                    area_def_cache[cell] = cell.area_def(
                        resolution,
                        padding,
                        margin=target_grid_margin,
                        conform_to=conform_to_shape,
                    )

            # Second pass: chunk cells and create tasks
            for start_time, time_group, all_cells in profile_cell_groups:
                # 6. Chunk cells and create tasks
                cell_chunks = [
                    all_cells[i : i + cells_per_task]
                    for i in range(0, len(all_cells), cells_per_task)
                ]

                for chunk_idx, cells in enumerate(cell_chunks):
                    # Filter assets to only those that spatially intersect these grid cells' footprints,
                    # accounting for resolution, padding, and margin.
                    cell_geoms = []
                    for cell in cells:
                        geobox = area_def_cache[cell]
                        cell_geoms.append(geobox.extent.to_crs(WGS84_CRS).geom)

                    cells_union = _union_all(gpd.GeoSeries(cell_geoms))

                    intersecting_mask = (
                        time_group.intersects(cells_union) | time_group.geometry.isna()
                    )
                    chunk_assets = cast(
                        GeoDataFrame[AssetSchema],
                        time_group[intersecting_mask].copy(),
                    )

                    task_context: dict[str, Any] = {
                        "chunk_id": chunk_idx,
                        "total_chunks": len(cell_chunks),
                        "start_time": str(start_time),
                        "extractor_hint": extractor_hint,
                        "init_params": dict(init_params) if init_params else {},
                    }

                    task = ExtractionTask(
                        assets=chunk_assets,
                        profile=profile,
                        uri=uri,
                        grid_cells=cells,
                        grid_config=grid_config,
                        aoi=target_aoi,
                        task_context=task_context,
                    )
                    tasks.append(task)

        return tasks

    @abstractmethod
    def extract(
        self,
        extraction_task: ExtractionTask,
        extract_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Extract data for a batch of assets (equivalent to one item of the prepare_for_extraction output).
        Args:
            extraction_task: An ExtractionTask containing a batch of assets to extract.
                This is one of the items returned by the `prepare_for_extraction` method.
                    extraction_task.task_context holds batch-specific data generated during preparation
            extract_params: Meta-level or tool-level parameters for the extraction
                (e.g. ``max_retries``, ``credentials``, ``downloader`` callables).
                Domain-specific configuration such as ``padding`` should be
                defined on ``extraction_task.profile`` (via its explicit
                fields or ``extract_params``) rather than here.

                .. note::
                    When a downloader is needed, extractors should resolve it in this order:
                    1. ``extraction_task.profile.downloader`` (per-profile, highest priority)
                    2. ``extract_params.get("downloader")`` (batch-level fallback)
                    3. Built-in default download logic.

        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
            time range, and any other relevant attributes.
        """
        ...


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
            A URI (e.g. ``s3://bucket/aer-tasks/{job_id}/{task_idx}/``) that the
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
