"""Declarative extraction pipeline model.

ExtractionPipeline describes the per-task pipeline (read → process → reproject → write)
in a serializable, stage-native way. It replaces the extraction-time half of AereoProfile.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Self, Sequence

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.types import ImportString


def _import_yaml() -> Any:
    try:
        import yaml

        return yaml
    except ImportError as exc:
        raise ImportError("YAML support requires PyYAML") from exc


class StageConfig(BaseModel):
    """Configuration for a single pipeline stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ProcessStageConfig(StageConfig):
    """Configuration for a processor with explicit pipeline stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Literal["pre_reproject", "post_reproject"] = "post_reproject"


class ExtractionPipeline(BaseModel):
    """Declarative per-task extraction pipeline.

    Describes what happens inside each worker: read assets, optionally process
    them, reproject to the target grid, optionally process per-cell, then write.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    resolution: float
    padding: int | None = 0
    conform_to: tuple[int, int] | None = None
    collections: Mapping[str, Sequence[str]] = Field(default_factory=dict)
    downloader: ImportString[Callable[[str, Path], None]] | None = None

    read: StageConfig = Field(default_factory=StageConfig)
    process: list[ProcessStageConfig] = Field(default_factory=list)
    reproject: StageConfig = Field(default_factory=StageConfig)
    write: StageConfig = Field(default_factory=StageConfig)

    def __getstate__(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        try:
            return self.model_dump(mode="json")
        except Exception:
            state: dict[str, Any] = {}
            for name in self.__class__.model_fields:
                try:
                    val = getattr(self, name)
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
    def from_yaml(cls, path: str | Path) -> Self:
        """Load pipeline from a YAML file."""
        yaml = _import_yaml()
        path = Path(path)
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data.get("pipeline", data))

    @classmethod
    def from_yaml_string(cls, text: str) -> Self:
        """Load pipeline from a YAML string."""
        yaml = _import_yaml()
        data = yaml.safe_load(text)
        return cls.model_validate(data.get("pipeline", data))


class PipelineBuilder:
    """Fluent builder for ExtractionPipeline.

    Example::

        pipeline = (
            PipelineBuilder(name="flood", resolution=10.0)
            .read_with("SentinelReader", reader="msi")
            .process_with("NDWIProcessor", threshold=0.3, stage="post_reproject")
            .reproject_with(resampling="bilinear")
            .write_with("GeoTiffWriter", driver="COG")
            .build()
        )
    """

    def __init__(
        self,
        name: str,
        resolution: float,
        padding: int | None = 0,
        conform_to: tuple[int, int] | None = None,
        collections: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self._name = name
        self._resolution = resolution
        self._padding = padding
        self._conform_to = conform_to
        self._collections = dict(collections) if collections else {}
        self._downloader: Callable[[str, Path], None] | None = None
        self._read: StageConfig | None = None
        self._process: list[ProcessStageConfig] = []
        self._reproject: StageConfig | None = None
        self._write: StageConfig | None = None

    def read_with(self, plugin: str | None = None, **params: Any) -> "PipelineBuilder":
        self._read = StageConfig(plugin=plugin, params=params)
        return self

    def process_with(
        self,
        plugin: str | None = None,
        stage: Literal["pre_reproject", "post_reproject"] = "post_reproject",
        **params: Any,
    ) -> "PipelineBuilder":
        self._process.append(
            ProcessStageConfig(plugin=plugin, stage=stage, params=params)
        )
        return self

    def reproject_with(
        self, plugin: str | None = None, **params: Any
    ) -> "PipelineBuilder":
        self._reproject = StageConfig(plugin=plugin, params=params)
        return self

    def write_with(self, plugin: str | None = None, **params: Any) -> "PipelineBuilder":
        self._write = StageConfig(plugin=plugin, params=params)
        return self

    def build(self) -> ExtractionPipeline:
        return ExtractionPipeline(
            name=self._name,
            resolution=self._resolution,
            padding=self._padding,
            conform_to=self._conform_to,
            collections=self._collections,
            downloader=self._downloader,
            read=self._read or StageConfig(),
            process=self._process,
            reproject=self._reproject or StageConfig(),
            write=self._write or StageConfig(),
        )


def profile_to_pipeline(profile: Any) -> ExtractionPipeline:
    """Convert a legacy AereoProfile to an ExtractionPipeline.

    This is a backward-compatibility bridge used during migration.
    """
    from aereo.interfaces.core import AereoProfile

    if not isinstance(profile, AereoProfile):
        raise TypeError(f"Expected AereoProfile, got {type(profile).__name__}")

    # Map plugin_hints to stage plugins
    read_plugin = profile.plugin_hints.get("read") or profile.plugin_hints.get(
        "extract"
    )
    reproject_plugin = profile.plugin_hints.get("reproject")
    write_plugin = profile.plugin_hints.get("write") or profile.plugin_hints.get(
        "extract"
    )

    # Map processor hints to ProcessStageConfig list
    process_stages: list[ProcessStageConfig] = []
    proc_hint = profile.plugin_hints.get("processors")
    if proc_hint:
        # Old format: comma-separated string, all sharing process_params
        for name in str(proc_hint).split(","):
            name = name.strip()
            if name:
                process_stages.append(
                    ProcessStageConfig(
                        plugin=name,
                        stage="post_reproject",
                        params=dict(profile.process_params),
                    )
                )

    # Merge extract_params into each stage's params for backward compat
    read_params = _merge_stage_params(profile.extract_params, profile.read_params)
    write_params = _merge_stage_params(profile.extract_params, profile.write_params)
    reproject_params = _merge_stage_params(profile.extract_params, {})

    # If we created processor stages from hints, re-merge extract_params
    if process_stages:
        process_stages = [
            ProcessStageConfig(
                plugin=p.plugin,
                stage=p.stage,
                params=_merge_stage_params(profile.extract_params, p.params),
            )
            for p in process_stages
        ]
    else:
        # No processor hints but maybe process_params exist — create a placeholder?
        # In the old model process_params were just passed to any processor. If none
        # are configured we drop them (no stage to attach to).
        pass

    return ExtractionPipeline(
        name=profile.name,
        resolution=profile.resolution,
        padding=profile.padding,
        conform_to=profile.conform_to,
        collections=dict(profile.collections),
        downloader=profile.downloader,
        read=StageConfig(plugin=read_plugin, params=read_params),
        process=process_stages,
        reproject=StageConfig(plugin=reproject_plugin, params=reproject_params),
        write=StageConfig(plugin=write_plugin, params=write_params),
    )


def _merge_stage_params(
    extract_params: Mapping[str, Any], stage_params: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge extract_params (legacy catch-all) into stage-specific params."""
    merged: dict[str, Any] = dict(extract_params)
    merged.update(stage_params)
    return merged
