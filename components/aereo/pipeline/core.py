"""Hydra-native declarative pipeline architecture for AEREO.

Defines the core declarative job model representing a complete search &
extraction pipeline configuration.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import Any, Literal, cast

import hydra
from omegaconf import OmegaConf
from aereo.executors.core import Executor, LocalExecutor
from aereo.interfaces import (
    ExtractionTask,
    Reader,
    Reprojector,
    Processor,
    SearchProvider,
    TaskBuilder,
    Writer,
)
from aereo.interfaces.utils import (
    _prepare_config_for_instantiate,
    normalize_geometry_input,
    update_callable,
)
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import BaseModel, Field, field_validator
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

logger = get_logger()


def _callable_name(obj: Any) -> str:
    """Return a readable name for a callable, unwrapping ``functools.partial``."""
    if isinstance(obj, partial):
        return _callable_name(obj.func)
    name = getattr(obj, "__name__", None)
    if name:
        return name
    return type(obj).__name__


def _default_task_builder() -> TaskBuilder:
    """Return the default task builder used when none is configured."""
    from aereo.builtins.task_builder import build_grouped_tasks

    return build_grouped_tasks


def _valid_job_keys(cls: type[ExtractionJob]) -> set[str]:
    """Return all field names and aliases accepted by ``ExtractionJob``.

    This lets Hydra configs define helper variables (e.g. ``target_bands``,
    ``aoi_path``) that are used for interpolation but are not part of the job
    schema.
    """
    keys = set(cls.model_fields.keys())
    for field_info in cls.model_fields.values():
        if field_info.alias:
            keys.add(field_info.alias)
    return keys


def _strip_unknown_job_keys(cfg: Any, cls: type[ExtractionJob]) -> Any:
    """Remove top-level keys that are not ``ExtractionJob`` fields or aliases.

    Args:
        cfg: Configuration container (dict, list, or scalar).
        cls: The ``ExtractionJob`` class whose schema defines valid keys.

    Returns:
        The same shape with unknown top-level keys removed.
    """
    if isinstance(cfg, dict):
        valid = _valid_job_keys(cls)
        return {k: v for k, v in cfg.items() if k in valid}
    return cfg


def load_plugin(config_dir: str | Path, group: str, name: str) -> Any:
    """Load a single runtime plugin from a Hydra config package.

    This helper removes the boilerplate of manually calling ``OmegaConf.load``
    and ``hydra.utils.instantiate(..., _convert_="all", _partial_=True)`` for
    runtime plugin groups such as ``search`` and ``task_builder``.

    Args:
        config_dir: Directory containing the Hydra config package.
        group: Config group directory name (e.g. ``search`` or ``task_builder``).
        name: Config file name (without ``.yaml``).

    Returns:
        The instantiated plugin (usually a ``functools.partial`` wrapping a
        function).

    Example::

        from aereo.pipeline import ExtractionJob, load_plugin

        job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
        search_provider = load_plugin("examples/config", "search", "sentinel2_pc")
        task_builder = load_plugin("examples/config", "task_builder", "grouped")
    """
    path = Path(config_dir).resolve() / group / f"{name}.yaml"
    cfg = OmegaConf.load(path)
    return hydra.utils.instantiate(cfg, _convert_="all", _partial_=True)


class ExtractionJob(BaseModel):
    """Declarative configuration tree for a complete extraction job.

    Bundles grid size, output URI, pipeline step callables, and optional
    runtime plugins (search provider and task builder) into a single validated
    Hydra-compatible model. When ``search_provider`` and/or ``task_builder``
    are configured, ``job.search()`` and ``job.build_tasks()`` can be called
    without passing a provider or builder explicitly.

    Pipeline execution order is fixed::

        read -> preprocess -> reproject -> postprocess -> write

    ``preprocess`` and ``postprocess`` accept either a single processor or a
    list of processors; each processor is applied in order. All pipeline steps
    are callables, typically ``functools.partial`` values loaded from Hydra,
    so any step-specific keyword arguments are bound directly to the callable.
    ``preprocess``, ``reproject``, and ``postprocess`` are optional. When
    ``reproject`` is provided, ``reproject_mode`` must be set to either
    ``"raw"`` (reproject the whole dataset once) or ``"grid"`` (reproject
    each grid cell separately).
    """

    model_config = {
        "extra": "forbid",
        "frozen": True,
        "arbitrary_types_allowed": True,
        "populate_by_name": True,
    }

    name: str = Field(
        default="default",
        description="Human-readable job name used to identify outputs.",
    )
    grid_dist: int = Field(
        description="Grid cell size in metres for the MajorTOM artifact index."
    )
    output_uri: str = Field(
        description="Destination URI for extracted artifacts (local path or object store)."
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "When False, reuse cached per-task artifact catalogs if they exist. "
            "When True, always execute tasks and overwrite existing caches."
        ),
    )
    target_aoi: BaseGeometry | dict[str, Any] | str | Path | None = Field(
        default=None,
        description=(
            "AOI geometry used to clip prepared extraction tasks and to build "
            "the MajorTOM artifact index. "
            "Accepts a Shapely object, GeoJSON dict, or path to a GeoJSON file. "
            "When omitted, the search provider's ``intersects`` geometry is used."
        ),
    )

    # Optional grid/reprojection parameters
    resolution: float | None = Field(
        default=None,
        description="Target pixel resolution in metres for reprojection and artifact indexing.",
    )
    margin: float | None = Field(
        default=None,
        description="Buffer in metres added around the AOI when building the grid.",
    )
    crop_buffer: float = Field(
        default=0.1,
        description=(
            "Buffer in degrees added around each grid cell before cropping the "
            "source dataset in grid-mode reprojection. Larger buffers keep more "
            "source pixels for edge cells but increase memory use."
        ),
    )
    grid_cells_margin: float = Field(
        default=0.0,
        description=(
            "Percentage margin added to each grid cell's GeoBox during grid-mode "
            "reprojection (e.g. 10.0 for 10%%). This expands the output patch "
            "beyond the nominal cell size to avoid gaps between adjacent cells. "
            "Distinct from ``margin``, which is a metre buffer around the full AOI."
        ),
    )
    alignment_resolution: float | None = Field(
        default=None,
        description=(
            "Optional resolution in metres used to align the grid cell GeoBox. "
            "When set, the GeoBox centre and half-width are snapped to this grid "
            "instead of ``resolution``. This is useful for nested extractions "
            "(e.g. VIIRS at 400 m and GOES at 2000 m) where the finer resolution "
            "should be an exact refinement of a coarser grid. Defaults to ``resolution``."
        ),
    )

    # Pipeline steps
    read: Reader = Field(
        description="Callable that reads source data and returns an xr.Dataset."
    )

    preprocess: Processor | list[Processor] | None = Field(
        default=None,
        description="Optional processor or list of processors applied after read.",
    )

    reproject: Reprojector | None = Field(
        default=None,
        description="Optional reprojection callable.",
    )
    reproject_mode: Literal["raw", "grid"] | None = Field(
        default=None,
        description="Reprojection mode: 'raw' for one mosaic, 'grid' for one file per cell.",
    )

    postprocess: Processor | list[Processor] | None = Field(
        default=None,
        description="Optional processor or list of processors applied after reprojection.",
    )

    write: Writer = Field(
        description="Callable that writes an xr.Dataset to a single path and returns it."
    )

    # Optional runtime plugins. The config keys ``search`` and ``task_builder``
    # are accepted for readability; internally they are stored as
    # ``search_provider`` and ``task_builder``.
    search_provider: SearchProvider | None = Field(
        default=None,
        alias="search",
        description="Optional search provider used by ``job.search()`` when no provider is passed.",
    )
    task_builder: TaskBuilder | None = Field(
        default_factory=_default_task_builder,
        description="Optional task builder used by ``job.build_tasks()`` when no builder is passed. Defaults to ``build_grouped_tasks``.",
    )

    @field_validator("preprocess", "postprocess", mode="before")
    @classmethod
    def _normalize_processors(
        cls,
        value: Processor | list[Processor] | None,
    ) -> list[Processor] | None:
        """Normalize a single processor to a list for uniform execution."""
        if value is None:
            return None
        if isinstance(value, list):
            return value
        return [value]

    @field_validator("target_aoi", mode="before")
    @classmethod
    def _validate_target_aoi(cls, value: Any) -> BaseGeometry | None:
        """Normalize the ``target_aoi`` input before Pydantic validation.

        Args:
            value: Shapely geometry, GeoJSON dict, path, or ``None``.

        Returns:
            A normalized geometry or ``None``.
        """
        return normalize_geometry_input(value)

    @field_validator("reproject_mode")
    @classmethod
    def _validate_reproject_mode(
        cls,
        value: Literal["raw", "grid"] | None,
        info: Any,
    ) -> Literal["raw", "grid"] | None:
        """Ensure reproject_mode is consistent with reproject presence."""
        data = info.data
        reproject = data.get("reproject")
        if reproject is not None and value is None:
            raise ValueError("reproject_mode must be set when reproject is provided")
        if reproject is None and value is not None:
            raise ValueError(
                "reproject_mode must be None when reproject is not provided"
            )
        return value

    @classmethod
    def _from_instantiated(cls, instantiated: Any, source: str) -> ExtractionJob:
        """Validate an object produced by Hydra instantiation as an ExtractionJob.

        Args:
            instantiated: Object produced by ``hydra.utils.instantiate``.
            source: Human-readable description of the config source for errors.

        Returns:
            A validated ``ExtractionJob`` instance.

        Raises:
            ValueError: If *instantiated* is neither an ``ExtractionJob`` nor a dict.
        """
        if isinstance(instantiated, cls):
            return instantiated

        if isinstance(instantiated, dict):
            return cls.model_validate(instantiated)

        raise ValueError(
            f"Failed to instantiate ExtractionJob from {source}: "
            f"expected ExtractionJob or dict, got {type(instantiated).__name__}"
        )

    @property
    def effective_target_aoi(self) -> BaseGeometry | None:
        """Return the geometry used to clip prepared tasks.

        Returns the explicitly provided ``target_aoi`` if any, otherwise
        ``None``.
        """
        return cast("BaseGeometry | None", self.target_aoi)

    def search(
        self,
        provider: SearchProvider | None = None,
        aoi: BaseGeometry | dict[str, Any] | str | Path | None = None,
        **search_kwargs: Any,
    ) -> GeoDataFrame[AssetSchema]:
        """Execute a search.

        Uses *provider* when given; otherwise falls back to the job's configured
        ``search_provider``. Runtime search parameters win over the job's fixed
        ``target_aoi``. The resolved AOI is passed to the provider as
        ``intersects``.

        Args:
            provider: Optional search provider to execute. Defaults to the
                provider configured on the job.
            aoi: Optional AOI geometry overriding ``job.target_aoi``.
            **search_kwargs: Additional arguments used to update the provider
                before execution (e.g. ``start_datetime``, ``end_datetime``).

        Returns:
            A validated GeoDataFrame of matched assets.

        Raises:
            ValueError: If no provider is given and none is configured on the job.
        """
        provider = provider or self.search_provider
        if provider is None:
            raise ValueError(
                "No search provider configured. Pass one or set it in the job config."
            )

        logger.info(
            "search_called",
            provider=_callable_name(provider),
        )

        resolved_aoi = (
            normalize_geometry_input(aoi)
            if aoi is not None
            else self.effective_target_aoi
        )
        if resolved_aoi is not None:
            search_kwargs["intersects"] = resolved_aoi

        bound_provider = update_callable(provider, **search_kwargs)

        return bound_provider()

    def build_tasks(
        self,
        assets: GeoDataFrame[AssetSchema],
        task_builder: TaskBuilder | None = None,
        **builder_kwargs: Any,
    ) -> Sequence[ExtractionTask]:
        """Build extraction tasks from search results.

        Args:
            assets: GeoDataFrame of assets returned by a search provider.
            task_builder: Optional task builder used to group assets into tasks.
                Defaults to the builder configured on the job.
            **builder_kwargs: Additional arguments used to update the task
                builder before execution (e.g. ``cells_per_task``).

        Returns:
            A sequence of prepared ``ExtractionTask`` objects.

        Raises:
            ValueError: If no builder is given and none is configured on the job.
        """
        task_builder = task_builder or self.task_builder
        if task_builder is None:
            raise ValueError(
                "No task builder configured. Pass one or set it in the job config."
            )

        if assets.empty:
            return []

        logger.info(
            "build_tasks_start",
            builder=_callable_name(task_builder),
            assets=len(assets),
        )

        if builder_kwargs:
            task_builder = update_callable(task_builder, **builder_kwargs)

        assert task_builder is not None
        return task_builder(assets, self)

    def execute(
        self,
        tasks: Sequence[ExtractionTask],
        executor: Executor | None = None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Run prepared tasks and return the combined artifacts.

        Args:
            tasks: Extraction tasks to execute.
            executor: Optional executor. Defaults to ``LocalExecutor()``.

        Returns:
            A validated ``GeoDataFrame[ArtifactSchema]``.
        """
        if not tasks:
            return cast(
                GeoDataFrame[ArtifactSchema], ArtifactSchema.empty_geodataframe()
            )

        selected_executor = executor or LocalExecutor()
        logger.info(
            "execute_start",
            task_count=len(tasks),
            executor=selected_executor.__class__.__name__,
        )
        return selected_executor(tasks)

    def write_catalog(
        self,
        artifacts: GeoDataFrame[ArtifactSchema],
        uri: str | Path | None = None,
    ) -> str:
        """Write the artifact catalog to parquet.

        Args:
            artifacts: GeoDataFrame of extracted artifacts.
            uri: Destination URI. Defaults to
                ``{output_uri}/artifacts.parquet``.

        Returns:
            The URI where the catalog was written.
        """
        if uri is None:
            uri = f"{self.output_uri.rstrip('/')}/artifacts.parquet"

        str_uri = str(uri)
        if not str_uri.startswith("s3://"):
            path = Path(str_uri.removeprefix("file://"))
            path.parent.mkdir(parents=True, exist_ok=True)

        artifacts.to_parquet(str_uri)  # pyright: ignore[reportArgumentType]
        return str_uri

    @classmethod
    def load_from_config(
        cls,
        config_dir: str | Path,
        config_name: str = "main_config",
        overrides: list[str] | None = None,
    ) -> ExtractionJob:
        """Load and validate an ``ExtractionJob`` from a Hydra config package.

        This is the recommended way to consume a Hydra config package: it
        initializes the config directory, composes the configuration,
        recursively instantiates all plugins, and validates the result.

        Args:
            config_dir: Directory containing the Hydra config package.
            config_name: Name of the root config file (without ``.yaml``).
            overrides: Optional Hydra command-line style overrides, e.g.
                ``["grid_dist=grid_50km"]``.

        Returns:
            A validated ``ExtractionJob`` instance.

        Example::

            from aereo.pipeline import ExtractionJob

            job = ExtractionJob.load_from_config(
                "examples/config_package",
                overrides=["grid_dist=grid_50km"],
            )
        """
        from hydra import compose, initialize_config_dir
        from omegaconf import OmegaConf

        config_dir = Path(config_dir).resolve()
        with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
            cfg = compose(config_name=config_name, overrides=overrides or [])
            plain_cfg = OmegaConf.to_container(cfg, resolve=True)
            plain_cfg = _strip_unknown_job_keys(plain_cfg, cls)
            prepared_cfg = _prepare_config_for_instantiate(plain_cfg)
            instantiated = hydra.utils.instantiate(prepared_cfg, _convert_="all")

        return cls._from_instantiated(
            instantiated, f"config at {config_dir}/{config_name}"
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> ExtractionJob:
        """Load an ExtractionJob from a single YAML file using Hydra.

        Loads the configuration via OmegaConf, recursively instantiates all
        target classes using hydra.utils.instantiate, and returns an
        ExtractionJob instance.

        The expected YAML layout places ``grid_dist``, ``output_uri``,
        ``read`` and ``write`` as top-level keys, enabling Hydra config package
        composition::

            defaults:
              - grid_dist: default
              - read: sentinel2
              - write: geotiff
              - _self_

            output_uri: /tmp/extraction

        Args:
            path: Path to the YAML config file.

        Returns:
            A validated ``ExtractionJob`` instance.

        Raises:
            ValueError: If Hydra instantiation does not produce an
                ``ExtractionJob`` or a dict.
        """
        from omegaconf import OmegaConf

        path = Path(path)
        cfg = OmegaConf.load(path)

        plain_cfg = OmegaConf.to_container(cfg, resolve=True)
        plain_cfg = _strip_unknown_job_keys(plain_cfg, cls)
        prepared_cfg = _prepare_config_for_instantiate(plain_cfg)
        instantiated = hydra.utils.instantiate(prepared_cfg, _convert_="all")
        return cls._from_instantiated(instantiated, f"configuration at {path}")
