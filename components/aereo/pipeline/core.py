"""Hydra-native declarative pipeline architecture for AEREO.

Defines the core declarative job model representing a complete search &
extraction pipeline configuration.
"""

from __future__ import annotations

from pathlib import Path

from aereo.interfaces.core import (
    SearchProvider,
    GlobalConfig,
    ExtractConfig,
)
from pydantic import BaseModel, Field


class ExtractionJob(BaseModel):
    """Declarative configuration tree for a complete extraction job.

    Bundles search configuration, global job settings, and extraction pipeline stages
    together into a single validated Hydra-compatible model.
    """

    model_config = {"extra": "forbid", "frozen": True}

    global_config: GlobalConfig = Field(alias="global")
    search: SearchProvider
    extract: ExtractConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> ExtractionJob:
        """Load an ExtractionJob from a YAML file using Hydra.

        Loads the configuration via OmegaConf, recursively instantiates all
        target classes using hydra.utils.instantiate, and returns an
        ExtractionJob instance.
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
