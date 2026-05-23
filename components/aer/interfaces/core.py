from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, Self, Sequence, cast

import attrs
import pandas as pd
from aer.grid import GridCell
from aer.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field, ImportString, TypeAdapter
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


def merge_params(
    batch_params: Mapping[str, Any] | None,
    profile_params: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge profile-level params over batch-level params.

    Profile wins on key collision.
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
    grid_filter_mode: Literal["intersection", "within", "coverage"] = Field(
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
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "YAML support requires PyYAML. Install it with: pip install 'aer[yaml]'"
            ) from exc
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls._from_raw(data)

    @classmethod
    def from_yaml_string(cls, text: str) -> "GridConfig":
        """Load a GridConfig from a YAML string."""
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "YAML support requires PyYAML. Install it with: pip install 'aer[yaml]'"
            ) from exc
        data = yaml.safe_load(text)
        return cls._from_raw(data)

    @classmethod
    def from_json(cls, path: str | Path) -> "GridConfig":
        """Load a GridConfig from a JSON file."""
        path = Path(path)
        data = json.loads(path.read_text())
        return cls._from_raw(data)

    @classmethod
    def _from_raw(cls, data: dict[str, Any]) -> "GridConfig":
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


class AerPlugin(ABC):
    """Base class for AER plugins"""

    # 1. Define the type hint, but remove the `= None` default.
    supported_collections: Sequence[str]

    def __init_subclass__(cls, plugin_abstract: bool = False, **kwargs):
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

        # 5. Empty sequences are allowed (used by plugins that only support plugin_hints)


class SearchProvider(AerPlugin, plugin_abstract=True):
    @abstractmethod
    def search(
        self,
        profiles: Sequence[AerProfile],
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        search_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[AssetSchema]:
        """Search for collections data matching the query.

        Args:
            profiles: Sequence of AerProfile objects defining what to search for.
                Collections and other domain-specific config are read from each
                profile (via ``collections``, ``search_params``, etc.).
            intersects: Optional shapely BaseGeometry to filter results by spatial intersection.
            start_datetime: Optional start datetime to filter results by temporal range.
            end_datetime: Optional end datetime to filter results by temporal range.
            search_params: Additional meta-level parameters for the search (credentials,
                timeouts, etc.). Domain-specific config lives on each AerProfile.

        Returns:
            A GeoDataFrame of search results, where each row represents a dataset
            or asset that matches the search criteria, and includes metadata such
            as collection, geometry, time range, and any other relevant attributes.
        """
        ...


class AerProfile(BaseModel):
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

    @classmethod
    def from_yaml(cls, path: str | Path) -> list[Self]:
        """Load profiles from a YAML file.

        The file must contain a top-level ``profiles`` key mapping to a list
        of profile dictionaries.
        """
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "YAML support requires PyYAML. Install it with: pip install 'aer[yaml]'"
            ) from exc
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls._from_raw(data)

    @classmethod
    def from_yaml_string(cls, text: str) -> list[Self]:
        """Load profiles from a YAML string."""
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "YAML support requires PyYAML. Install it with: pip install 'aer[yaml]'"
            ) from exc
        data = yaml.safe_load(text)
        return cls._from_raw(data)

    @classmethod
    def from_json(cls, path: str | Path) -> list[Self]:
        """Load profiles from a JSON file."""
        path = Path(path)
        data = json.loads(path.read_text())
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
        if allow_duplicate_names:
            return
        seen = set()
        for p in profiles:
            if p.name in seen:
                raise ValueError(f"Duplicate profile name: {p.name!r}")
            seen.add(p.name)


# Backward-compat alias — will be removed in a later task.
ExtractionProfile = AerProfile


@attrs.frozen
class ExtractionTask:
    """
    A class representing a task for extracting data.

    Attributes:
        assets: GeoDataFrame of assets to extract. It can group multiple collections
            (for example Imagery + Geolocation). Schema is defined in `aer.schemas.AssetSchema`.
        profile: The AerProfile containing target variables and resolution.
        uri: Destination URI for extracted artifacts.
        grid_cells: Spatial grid cells this task covers.
        grid_config: Tiling specification shared by all tasks in this run.
        aoi: Optional area-of-interest geometry used to clip the extraction region.
        task_context: Observability metadata generated during task preparation
            (e.g. ``chunk_id``, ``total_chunks``, ``start_time``).
    """

    assets: GeoDataFrame[AssetSchema]
    profile: AerProfile
    uri: str
    grid_cells: Sequence[GridCell]
    grid_config: GridConfig
    aoi: BaseGeometry | None = None
    task_context: Mapping[str, Any] = attrs.field(factory=dict)

    def __attrs_post_init__(self) -> None:
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


def _extract_wrapper(
    extractor: "Extractor",
    task: "ExtractionTask",
    extract_params: Mapping[str, Any] | None,
) -> "GeoDataFrame[ArtifactSchema]":
    """Module-level wrapper so ProcessPoolExecutor can pickle the call."""
    return extractor.extract(task, extract_params)


class Extractor(AerPlugin, plugin_abstract=True):
    """Base class for AER extraction plugins.

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
        profiles: Sequence[AerProfile] | None = None,
        cells_per_chunk: int = 50,
        extractor_hint: str | None = None,
    ) -> Sequence[ExtractionTask]:
        """Prepare extraction tasks by grouping assets by profile and start time, then chunking grid cells."""
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

        from aer.grid import GridDefinition

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
                if hasattr(time_group, "union_all"):
                    group_geom = time_group.union_all()
                else:
                    group_geom = time_group.geometry.unary_union

                if group_geom is None or group_geom.is_empty:
                    continue

                # 4. Intersect with target_aoi if provided
                if target_aoi is not None:
                    aoi_geom = target_aoi.intersection(group_geom)
                else:
                    aoi_geom = group_geom

                if aoi_geom is None or aoi_geom.is_empty:
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
                # Pre-warm area_def cache with conformed shape for all cells
                for _, _, cells in profile_cell_groups:
                    for cell in cells:
                        cell.area_def(
                            resolution,
                            padding,
                            margin=target_grid_margin,
                            conform_to=conform_to_shape,
                        )

            # Second pass: chunk cells and create tasks
            for start_time, time_group, all_cells in profile_cell_groups:
                # 6. Chunk cells and create tasks
                cell_chunks = [
                    all_cells[i : i + cells_per_chunk]
                    for i in range(0, len(all_cells), cells_per_chunk)
                ]

                for chunk_idx, cells in enumerate(cell_chunks):
                    # Filter assets to only those that spatially intersect these grid cells' footprints,
                    # accounting for resolution, padding, and margin.
                    import geopandas as gpd

                    cell_geoms = []
                    for cell in cells:
                        geobox = cell.area_def(
                            resolution,
                            padding=padding,
                            margin=target_grid_margin,
                            conform_to=conform_to_shape,
                        )
                        cell_geoms.append(geobox.extent.to_crs("epsg:4326").geom)

                    if hasattr(gpd.GeoSeries(cell_geoms), "union_all"):
                        cells_union = gpd.GeoSeries(cell_geoms).union_all()
                    else:
                        cells_union = gpd.GeoSeries(cell_geoms).unary_union

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

    def extract_batches(
        self,
        extraction_task_batch: Sequence[ExtractionTask],
        extract_params: Mapping[str, Any] | None = None,
        max_batch_workers: int | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """
        Execute extraction over multiple batches, optionally in parallel.

        When ``max_batch_workers`` is set, batches are processed in parallel
        using ``ProcessPoolExecutor`` with a ``forkserver`` context (Unix) or
        ``spawn`` context (Windows).  This avoids thread-safety issues that can
        occur with the default ``fork`` start method when threaded libraries
        such as dask or rasterio have already been imported in the parent
        process.  Failed batches are logged and collected; if *all* batches fail
        a ``RuntimeError`` is raised.

        When ``max_batch_workers`` is ``None`` (default), falls back to
        sequential execution.

        Args:
            extraction_task_batch: A sequence of ExtractionTask, where each one contains a batch
                of assets to extract. This is the output of the `prepare_for_extraction` method.
            extract_params: Meta-level or tool-level parameters for the extraction
                (e.g. ``max_retries``, ``credentials``, ``downloader`` callables).
                Domain-specific configuration should live on each task's ``profile``.
            max_batch_workers: Maximum number of worker processes for parallel execution.
                ``None`` (default) disables parallelism and runs sequentially.
        Returns:
            A GeoDataFrame of extracted artifacts, where each row corresponds to an extracted asset
            and its corresponding grid_cell, and includes metadata such as collection, geometry,
            time range, and any other relevant attributes.
        """
        if max_batch_workers is None:
            # Sequential path (original behaviour)
            results = []
            for batch in extraction_task_batch:
                effective_params = merge_params(
                    extract_params, batch.profile.extract_params
                )
                results.append(self.extract(batch, effective_params))
            concatenated = pd.concat(results, ignore_index=True)
            validated = ArtifactSchema.validate(concatenated)
            return cast(GeoDataFrame[ArtifactSchema], validated)

        # Parallel path
        results: list[GeoDataFrame[ArtifactSchema]] = []
        errors: list[str] = []

        tasks = [
            (self, batch, merge_params(extract_params, batch.profile.extract_params))
            for batch in extraction_task_batch
        ]

        with ProcessPoolExecutor(max_workers=max_batch_workers) as executor:
            futures = {
                executor.submit(_extract_wrapper, *t): i for i, t in enumerate(tasks)
            }

            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "batch_extract_failed",
                        extra={"batch": batch_idx, "error": str(exc)},
                    )
                    errors.append(str(exc))

        if not results:
            raise RuntimeError(
                f"All {len(extraction_task_batch)} batches failed. Errors: {errors}"
            )

        concatenated = pd.concat(results, ignore_index=True)
        validated = ArtifactSchema.validate(concatenated)
        return cast(GeoDataFrame[ArtifactSchema], validated)
