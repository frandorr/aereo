"""Hydra-native declarative pipeline architecture for AEREO.

Defines the core declarative job model representing a complete search &
extraction pipeline configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import hydra
from aereo.interfaces import (
    ExtractConfig,
    GridConfig,
    PatchConfig,
)
from aereo.interfaces.utils import normalize_geometry_input
from pydantic import BaseModel, Field, field_validator
from shapely.geometry.base import BaseGeometry


class ExtractionJob(BaseModel):
    """Declarative configuration tree for a complete extraction job.

    Bundles grid/patch settings, an output URI, and extraction pipeline stages
    together into a single validated Hydra-compatible model. Search providers
    and task builders are supplied at runtime to the orchestration methods
    rather than stored on the job.
    """

    model_config = {"extra": "forbid", "frozen": True, "arbitrary_types_allowed": True}

    name: str = Field(
        default="default",
        description="Human-readable job name used to identify outputs.",
    )
    derivative: str | None = Field(
        default=None,
        description=(
            "Name of the derivative pipeline. When set, output files are placed "
            "under a ``derivatives/<name>/`` subdirectory of ``output_uri``, "
            "following the EOIDS convention for processed/derived products."
        ),
    )
    grid_config: GridConfig
    patch_config: PatchConfig
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
    extract: ExtractConfig
    target_aoi: BaseGeometry | dict[str, Any] | str | Path | None = Field(
        default=None,
        description=(
            "AOI geometry used to clip prepared extraction tasks. "
            "Accepts a Shapely object, GeoJSON dict, or path to a GeoJSON file. "
            "When omitted, the search provider's ``intersects`` geometry is used."
        ),
    )

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
                ``["patch_config=high_res"]``.

        Returns:
            A validated ``ExtractionJob`` instance.

        Example::

            from aereo.pipeline import ExtractionJob

            job = ExtractionJob.load_from_config(
                "examples/config_package",
                overrides=["patch_config=high_res"],
            )
        """
        from hydra import compose, initialize_config_dir

        config_dir = Path(config_dir).resolve()
        with initialize_config_dir(version_base=None, config_dir=str(config_dir)):
            cfg = compose(config_name=config_name, overrides=overrides or [])
            instantiated = hydra.utils.instantiate(cfg, _convert_="all")

        return cls._from_instantiated(
            instantiated, f"config at {config_dir}/{config_name}"
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> ExtractionJob:
        """Load an ExtractionJob from a single YAML file using Hydra.

        Loads the configuration via OmegaConf, recursively instantiates all
        target classes using hydra.utils.instantiate, and returns an
        ExtractionJob instance.

        The expected YAML layout places ``grid_config``, ``patch_config``,
        ``output_uri`` and ``extract`` as top-level keys, enabling Hydra config
        package composition::

            defaults:
              - grid_config: default
              - patch_config: base
              - extract: sentinel2
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

        instantiated = hydra.utils.instantiate(cfg, _convert_="all")
        return cls._from_instantiated(instantiated, f"configuration at {path}")
