"""Hydra-native declarative pipeline architecture for AEREO.

Defines the core declarative job model representing a complete search &
extraction pipeline configuration.
"""

from __future__ import annotations

from pathlib import Path

from aereo.interfaces import (
    ExtractConfig,
    GridConfig,
    PatchConfig,
    SearchProvider,
)
from pydantic import BaseModel, Field


class ExtractionJob(BaseModel):
    """Declarative configuration tree for a complete extraction job.

    Bundles search configuration, grid/patch settings, an output URI, and
    extraction pipeline stages together into a single validated
    Hydra-compatible model.
    """

    model_config = {"extra": "forbid", "frozen": True}

    grid_config: GridConfig
    patch_config: PatchConfig
    output_uri: str = Field(
        description="Destination URI for extracted artifacts (local path or object store)."
    )
    search: SearchProvider
    extract: ExtractConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> ExtractionJob:
        """Load an ExtractionJob from a YAML file using Hydra.

        Loads the configuration via OmegaConf, recursively instantiates all
        target classes using hydra.utils.instantiate, and returns an
        ExtractionJob instance.

        The expected YAML layout places ``grid_config``, ``patch_config`` and
        ``output_uri`` as top-level keys alongside ``search`` and ``extract``,
        enabling Hydra config package composition::

            defaults:
              - grid_config: default
              - patch_config: base
              - extract: sentinel2
              - _self_

            output_uri: /tmp/extraction
        """
        from omegaconf import OmegaConf
        import hydra

        path = Path(path)
        cfg = OmegaConf.load(path)

        instantiated = hydra.utils.instantiate(cfg, _convert_="all")
        if isinstance(instantiated, cls):
            return instantiated

        if isinstance(instantiated, dict):
            return cls.model_validate(instantiated)

        raise ValueError(
            f"Failed to instantiate ExtractionJob from configuration at {path}: "
            f"expected ExtractionJob or dict, got {type(instantiated).__name__}"
        )
