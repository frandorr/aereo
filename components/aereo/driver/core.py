"""Hamilton-based driver for AEREO pipeline stages.

Discovers function-based plugins via entry-point groups and builds a
separate Hamilton :class:`hamilton.driver.Driver` for each phase:
search, prepare, and extract.
"""

from __future__ import annotations

from datetime import datetime
from types import ModuleType
from typing import Any, Sequence

from hamilton import driver
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

from aereo.discovery import StagePlugins, discover_plugins, resolve_plugin
from aereo.interfaces import GridConfig, PipelineProfile


class AereoDriver:
    """Discovers plugins and builds Hamilton drivers per phase."""

    def __init__(self) -> None:
        """Discover all stage plugins via entry points."""
        self._search_plugins: StagePlugins = discover_plugins("aereo.search")
        self._download_plugins: StagePlugins = discover_plugins("aereo.download")
        self._read_plugins: StagePlugins = discover_plugins("aereo.read")
        self._reproject_plugins: StagePlugins = discover_plugins("aereo.reproject")
        self._write_plugins: StagePlugins = discover_plugins("aereo.write")
        self._process_plugins: StagePlugins = discover_plugins("aereo.process")

    def _resolve_plugin(self, stage: str, profile: PipelineProfile) -> ModuleType:
        """Resolve which plugin module to use for a stage.

        Resolution priority:

        1. ``profile.plugin_hints[stage]`` — explicit user choice.
        2. Collection match — auto-discovery via ``supported_collections``.
        3. Wildcard fallback — a plugin declaring ``supported_collections = ("*",)``.

        Args:
            stage: The pipeline stage (e.g. ``"search"``, ``"read"``).
            profile: The pipeline profile to resolve for.

        Returns:
            The resolved plugin module.

        Raises:
            ValueError: If no plugin can be resolved.
        """
        stage_plugins: StagePlugins = getattr(self, f"_{stage}_plugins")
        collection = next(iter(profile.collections.keys()), "*")
        return resolve_plugin(stage, collection, profile.plugin_hints, stage_plugins)

    def search(
        self,
        profile: PipelineProfile,
        aoi: BaseGeometry | None,
        start_datetime: str | datetime | None,
        end_datetime: str | datetime | None,
    ) -> GeoDataFrame:
        """Build a Hamilton search driver and execute the search DAG.

        Args:
            profile: Pipeline profile with search configuration.
            aoi: Area of interest geometry.
            start_datetime: Start of temporal range.
            end_datetime: End of temporal range.

        Returns:
            GeoDataFrame of search results.
        """
        mod = self._resolve_plugin("search", profile)
        dr = driver.Builder().with_modules(mod).build()

        inputs: dict[str, Any] = {
            "aoi": aoi,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            **dict(profile.search_params),
        }
        result = dr.execute(["search_results"], inputs=inputs)
        return result["search_results"]

    def prepare(
        self,
        assets: GeoDataFrame,
        profile: PipelineProfile,
        grid_config: GridConfig,
        aoi: BaseGeometry | None,
        uri: str | None = None,
        cells_per_task: int | None = None,
    ) -> Sequence[Any]:
        """Build a Hamilton prepare driver and execute the prepare DAG.

        Args:
            assets: GeoDataFrame of search results.
            profile: Pipeline profile.
            grid_config: Grid configuration.
            aoi: Area of interest geometry.
            uri: Destination URI prefix for extracted artifacts.
            cells_per_task: Maximum grid cells per task chunk.

        Returns:
            Sequence of extraction tasks.

        Raises:
            NotImplementedError: Until core pipeline modules are created (Task 1.6).
        """
        try:
            from aereo.pipeline import prepare as prepare_module  # type: ignore[import-not-found]
        except ImportError as exc:
            raise NotImplementedError(
                "prepare() requires aereo.pipeline.prepare (Task 1.6)."
            ) from exc

        dr = driver.Builder().with_modules(prepare_module).build()
        inputs: dict[str, Any] = {
            "assets": assets,
            "grid_config": grid_config,
            "aoi": aoi,
            "profile": profile,
        }
        if uri is not None:
            inputs["uri"] = uri
        if cells_per_task is not None:
            inputs["cells_per_task"] = cells_per_task
        result = dr.execute(["extraction_tasks"], inputs=inputs)
        return result["extraction_tasks"]

    def extract(self, task: Any) -> GeoDataFrame:
        """Build a Hamilton extract driver and execute the extraction DAG.

        Args:
            task: ExtractionTask to process.

        Returns:
            GeoDataFrame of extracted artifacts.

        Raises:
            NotImplementedError: Until core pipeline and compiler modules are created.
        """
        try:
            from aereo.pipeline import compiler  # type: ignore[import-not-found]
        except ImportError as exc:
            raise NotImplementedError(
                "extract() requires aereo.pipeline.compiler (Task 1.5)."
            ) from exc

        profile = task.profile

        # Handle both AereoProfile and PipelineProfile during migration.
        if hasattr(profile, "pre_processors"):
            pre_processors: Sequence[str | dict[str, Any]] = profile.pre_processors
            post_processors: Sequence[str | dict[str, Any]] = profile.post_processors
            download_params: dict[str, Any] = dict(profile.download_params)
            read_params: dict[str, Any] = dict(profile.read_params)
            reproject_params: dict[str, Any] = dict(profile.reproject_params)
            write_params: dict[str, Any] = dict(profile.write_params)
        else:
            pre_processors = []
            post_processors = []
            download_params = dict(getattr(profile, "extract_params", {}))
            read_params = dict(getattr(profile, "read_params", {}))
            reproject_params = {}
            write_params = dict(getattr(profile, "write_params", {}))

        download_mod = self._resolve_plugin("download", profile)
        read_mod = self._resolve_plugin("read", profile)
        reproject_mod = self._resolve_plugin("reproject", profile)
        write_mod = self._resolve_plugin("write", profile)

        # TODO: processor_funcs will be injected into the Hamilton DAG when
        # ``with_functions`` support is finalized (Task 1.5/1.6).
        # For now the compiler is validated by the import above.
        compiler.compile_processors(  # noqa: F841
            list(pre_processors) + list(post_processors),
            self._gather_process_functions(),
        )

        dr = (
            driver.Builder()
            .with_modules(download_mod, read_mod, reproject_mod, write_mod)
            .build()
        )

        inputs: dict[str, Any] = {
            "task": task,
            **download_params,
            **read_params,
            **reproject_params,
            **write_params,
        }
        result = dr.execute(["artifacts_gdf"], inputs=inputs)
        return result["artifacts_gdf"]

    def _gather_process_functions(self) -> dict[str, Any]:
        """Gather all callable processor functions from discovered process plugins."""
        functions: dict[str, Any] = {}
        for mod in self._process_plugins.name_to_module.values():
            for name in dir(mod):
                if name.startswith("_"):
                    continue
                obj = getattr(mod, name)
                if callable(obj):
                    functions[name] = obj
        return functions
