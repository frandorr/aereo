"""AEREO CLI — command-line interface for the AEREO satellite data framework."""

from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence, cast

import attrs

import geopandas as gpd
import hydra
import pandas as pd
from omegaconf import DictConfig
from rich.console import Console
from rich.table import Table
from shapely.geometry.base import BaseGeometry

from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend
from aereo.interfaces import ExtractConfig, normalize_geometry_input
from aereo.pipeline import ExtractionJob
from aereo.interfaces.utils import _extract_geometry_from_geojson
from aereo.schemas import AssetSchema
from aereo.registry import AereoRegistry

console = Console()

_MAX_TABLE_ROWS = 50
_HREF_PREVIEW_CHARS = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_geometry(geojson_path: Path) -> dict[str, Any] | None:
    """Load a GeoJSON file and return the geometry dict.

    Args:
        geojson_path: Path to the GeoJSON file.

    Returns:
        The geometry dictionary, or None if the path is missing.

    Raises:
        ValueError: If the GeoJSON has no extractable geometry.
    """
    data = json.loads(geojson_path.read_text())
    geometry = _extract_geometry_from_geojson(data)
    if geometry is None:
        raise ValueError("Could not extract geometry from GeoJSON.")
    return geometry


def _load_geometry_safe(path: Path | None) -> BaseGeometry | None:
    """Load geometry from GeoJSON if path is provided and exists.

    Args:
        path: Path to GeoJSON file, or None.

    Returns:
        Shapely geometry, or None if path is None or missing.
    """
    geom_dict = _load_geometry(path) if path and path.exists() else None
    return normalize_geometry_input(geom_dict) if geom_dict is not None else None


def _build_search_provider(cfg: DictConfig) -> Any:
    """Instantiate and configure a search provider from CLI config.

    Args:
        cfg: Hydra DictConfig containing ``search``, ``geojson``, ``start``, and
            ``end`` keys.

    Returns:
        Configured search provider instance.
    """
    search_provider = hydra.utils.instantiate(cfg.search)

    update_dict: dict[str, Any] = {}
    intersects = _load_geometry_safe(Path(cfg.geojson) if cfg.geojson else None)
    if intersects:
        update_dict["intersects"] = intersects
    start_dt = _parse_iso_datetime(cfg.start)
    if start_dt:
        update_dict["start_datetime"] = start_dt
    end_dt = _parse_iso_datetime(cfg.end)
    if end_dt:
        update_dict["end_datetime"] = end_dt

    if update_dict:
        search_provider = search_provider.model_copy(update=update_dict)

    return search_provider


def _resolve_target_aoi(
    cfg: DictConfig,
    fallback: BaseGeometry | None = None,
) -> BaseGeometry | None:
    """Resolve the target AOI used to clip prepared extraction tasks.

    Resolution order:
        1. ``cfg.target_aoi`` (GeoJSON dict, file path, or Shapely object).
        2. ``cfg.geojson`` path.
        3. ``fallback`` geometry (commonly ``search_provider.intersects``).

    Args:
        cfg: Hydra DictConfig.
        fallback: Optional fallback geometry.

    Returns:
        A Shapely BaseGeometry, or None if no AOI is available.
    """
    target = cfg.get("target_aoi")
    if target is not None:
        from omegaconf import DictConfig as OmegaConfDictConfig, OmegaConf

        if isinstance(target, OmegaConfDictConfig):
            target = OmegaConf.to_container(target, resolve=True)
        return normalize_geometry_input(
            cast("BaseGeometry | dict[str, Any] | str | Path | None", target)
        )

    if cfg.geojson:
        return _load_geometry_safe(Path(cfg.geojson))

    return fallback


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string.

    Args:
        value: ISO 8601 datetime string, or None.

    Returns:
        Parsed datetime, or None if input was None.
    """
    return datetime.fromisoformat(value) if value else None


def _search_results_to_json(df: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Convert search results GeoDataFrame to JSON-serializable records.

    Args:
        df: GeoDataFrame containing search results.

    Returns:
        List of JSON-serializable record dictionaries.
    """
    # Convert to plain DataFrame to avoid GeoDataFrame geometry warnings
    plain_df = pd.DataFrame(df.copy())
    plain_df["geometry"] = plain_df["geometry"].apply(
        lambda g: g.__geo_interface__ if g is not None else None
    )
    records = plain_df.to_dict(orient="records")
    # Convert datetime to ISO strings
    for rec in records:
        for key in ("start_time", "end_time"):
            val = rec.get(key)
            if val is not None and isinstance(val, datetime):
                rec[key] = val.isoformat()
    return records


def _search_results_from_json(records: list[dict[str, Any]]) -> gpd.GeoDataFrame:
    """Reconstruct a GeoDataFrame from JSON records.

    Args:
        records: List of JSON record dictionaries.

    Returns:
        A validated GeoDataFrame.
    """
    df = gpd.GeoDataFrame.from_records(records)
    if "geometry" in df.columns:
        from shapely.geometry import shape

        def _to_geom(g: Any) -> Any:
            """Convert a GeoJSON dict to a Shapely geometry."""
            if isinstance(g, dict):
                return shape(g)
            return g

        df["geometry"] = gpd.GeoSeries(df["geometry"].apply(_to_geom))
        df = gpd.GeoDataFrame(df, geometry="geometry")
        df = cast(gpd.GeoDataFrame, df.set_crs(epsg=4326))
    for key in ("start_time", "end_time"):
        if key in df.columns:
            df[key] = pd.to_datetime(df[key])
    return gpd.GeoDataFrame(AssetSchema.validate(df))


def _print_search_table(df: gpd.GeoDataFrame) -> None:
    """Pretty-print search results as a Rich table.

    Displays the first 50 rows with a trailing indicator when more exist.

    Args:
        df: GeoDataFrame containing search results.
    """
    table = Table(title=f"Search Results ({len(df)} scenes)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Collection", style="magenta")
    table.add_column("Start Time", style="green")
    table.add_column("End Time", style="green")
    table.add_column("Href", style="blue", overflow="fold")

    for row in df.head(_MAX_TABLE_ROWS).itertuples(index=False):
        table.add_row(
            str(getattr(row, "id", "")),
            str(getattr(row, "collection", "")),
            str(getattr(row, "start_time", "")),
            str(getattr(row, "end_time", "")),
            str(getattr(row, "href", ""))[:_HREF_PREVIEW_CHARS] + "...",
        )
    if len(df) > _MAX_TABLE_ROWS:
        table.add_row(
            "...",
            f"... and {len(df) - _MAX_TABLE_ROWS} more rows",
            "",
            "",
            "",
        )
    console.print(table)


def _pipeline_to_extract(
    pipeline: Sequence[Any] | None,
) -> ExtractConfig | None:
    """Convert a list of instantiated plugins into an ``ExtractConfig``.

    The CLI ``pipeline`` key is a flat list ordered as
    ``[reader, preprocess..., reprojector, postprocess..., writer]``.
    This helper partitions the list into the structured ``ExtractConfig``
    expected by ``ExtractionJob``.
    """
    if not pipeline:
        return None

    from aereo.interfaces import (
        BatchWriter,
        Processor,
        Reader,
        Reprojector,
        Writer,
    )

    read: Reader | None = None
    reproject: Reprojector | None = None
    write: Writer | BatchWriter | None = None
    preprocess: list[Processor] = []
    postprocess: list[Processor] = []

    for plugin in pipeline:
        if isinstance(plugin, Reader):
            read = plugin
        elif isinstance(plugin, Reprojector):
            reproject = plugin
        elif isinstance(plugin, (Writer, BatchWriter)):
            write = plugin
        elif isinstance(plugin, Processor):
            (postprocess if reproject is not None else preprocess).append(plugin)

    if read is None:
        raise ValueError("pipeline must include a Reader plugin as its first element.")

    return ExtractConfig(
        read=read,
        preprocess=preprocess,
        reproject=reproject,
        postprocess=postprocess,
        write=write,
    )


def _configure_verbose_logging(verbose: bool) -> None:
    """Configure structlog for verbose output if requested.

    Args:
        verbose: Whether to enable verbose (DEBUG) logging.
    """
    if verbose:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))


def _add_plugin_rows(
    table: Table, label: str, plugins: dict[str, type], registry: AereoRegistry
) -> None:
    """Add plugin summary rows to a Rich table.

    Args:
        table: Rich Table to append rows to.
        label: Human-readable plugin type label.
        plugins: Mapping of plugin name to plugin class.
        registry: AereoRegistry instance to query metadata.
    """
    for name, cls in plugins.items():
        reg_key = label.replace(" ", "_").lower()
        collections = registry._registries[reg_key].get_collections(name)
        cols = ", ".join(collections[:3])
        if len(collections) > 3:
            cols += " ..."
        try:
            params = registry.get_plugin_params(name)
            req = str(len(params.get("required", [])))
            opt = str(len(params.get("optional", [])))
        except Exception:
            req = "0"
            opt = "0"
        table.add_row(label, name, cols, req, opt)


def _run_with_exit(
    label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Execute *fn*, printing a styled error and exiting on exception.

    Args:
        label: Human-readable name of the operation for error messages.
        fn: Callable to execute.
        *args: Positional arguments for *fn*.
        **kwargs: Keyword arguments for *fn*.

    Returns:
        The return value of *fn*.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        console.print(f"[red]{label} failed:[/red] {exc}")
        sys.exit(1)


def _check_results(results: gpd.GeoDataFrame | None) -> None:
    """Exit if search results are empty or None.

    Args:
        results: GeoDataFrame from a search operation.
    """
    if results is None or len(results) == 0:
        console.print("[yellow]No results found.[/yellow]")
        sys.exit(2)


def plugins_cmd(cfg: DictConfig | None = None) -> None:
    """List installed AEREO plugins.

    Args:
        cfg: Unused; accepted so ``plugins_cmd`` matches the action runner
            signature.
    """
    registry = AereoRegistry()

    table = Table(title="Installed AEREO Plugins")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Collections", style="green")
    table.add_column("Required", style="yellow")
    table.add_column("Optional", style="blue")

    _add_plugin_rows(table, "Searcher", registry._searchers, registry)
    _add_plugin_rows(
        table,
        "Task Builder",
        registry._registries["task_builder"].plugins,
        registry,
    )

    for label in ("reader", "reprojector", "processor", "writer", "batch_writer"):
        _add_plugin_rows(
            table,
            label.replace("_", " ").title(),
            registry._registries[label].plugins,
            registry,
        )

    console.print(table)


def plugin_params_cmd(name: str) -> None:
    """Show parameters for a specific AEREO plugin.

    Args:
        name: Name of the plugin to inspect.
    """
    registry = AereoRegistry()
    try:
        params = registry.get_plugin_params(name)
    except KeyError:
        console.print(f"[red]Plugin '{name}' not found.[/red]")
        sys.exit(1)

    table = Table(title=f"Parameters for {name}")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Data Type", style="green")
    table.add_column("Description", style="yellow")
    table.add_column("Required", style="blue")
    table.add_column("Default", style="dim")

    for section, required_flag in (("required", "Yes"), ("optional", "No")):
        for param in params.get(section, []):
            table.add_row(
                section.capitalize(),
                param["name"],
                param["type"],
                param["description"],
                required_flag,
                str(param["default"]) if param.get("default") is not None else "—",
            )

    console.print(table)


# ---------------------------------------------------------------------------
# Action runners
# ---------------------------------------------------------------------------


def _run_search_action(cfg: DictConfig) -> None:
    """Execute the ``search`` CLI action."""
    if not cfg.get("search"):
        console.print(
            "[red]No search provider configuration provided (search key is missing).[/red]"
        )
        sys.exit(1)

    search_provider = _build_search_provider(cfg)
    client = AereoClient()
    results = _run_with_exit("Search", client.search, search_provider=search_provider)
    _check_results(results)

    fmt = cfg.get("format", "table")
    if fmt == "json":
        records = _search_results_to_json(results)
        json_out = json.dumps(records, indent=2, default=str)
        if cfg.output:
            Path(cfg.output).write_text(json_out)
            console.print(
                f"[green]Wrote {len(records)} results to[/green] {cfg.output}"
            )
        else:
            console.print(json_out)
    else:
        _print_search_table(results)
        if cfg.output:
            records = _search_results_to_json(results)
            Path(cfg.output).write_text(json.dumps(records, indent=2, default=str))
            console.print(f"[green]Wrote results to[/green] {cfg.output}")


def _run_prepare_action(cfg: DictConfig) -> None:
    """Execute the ``prepare`` CLI action."""
    if not cfg.get("search_results"):
        console.print(
            "[red]search_results file path is required for prepare action.[/red]"
        )
        sys.exit(1)

    search_results_path = Path(cfg.search_results)
    if not search_results_path.exists():
        console.print(f"[red]Search results not found:[/red] {search_results_path}")
        sys.exit(1)

    records = json.loads(search_results_path.read_text())
    df = _search_results_from_json(records)

    pipeline = hydra.utils.instantiate(cfg.pipeline)
    grid_config = hydra.utils.instantiate(cfg.grid_config)
    patch_config = hydra.utils.instantiate(cfg.patch_config)
    task_builder = hydra.utils.instantiate(cfg.task_builder)
    extract = _pipeline_to_extract(pipeline)
    if extract is None:
        console.print(
            "[red]pipeline must include a Reader plugin as its first element.[/red]"
        )
        sys.exit(1)

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_aoi = _resolve_target_aoi(cfg)

    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=patch_config,
        output_uri=cfg.get("output_uri") or str(output_dir),
        extract=extract,
        target_aoi=target_aoi,
        overwrite=cfg.overwrite,
    )

    tasks = _run_with_exit(
        "Prepare",
        task_builder,
        search_results=df,
        job=job,
    )

    task_file = Path(cfg.output) if cfg.output else (output_dir / "tasks.pkl")
    task_file.write_bytes(pickle.dumps(tasks))
    chunk_size = getattr(task_builder, "cells_per_task", None)
    chunk_msg = f" (chunk size: {chunk_size})" if chunk_size is not None else ""
    console.print(f"[green]✓ Prepared {len(tasks)} tasks{chunk_msg}.[/green]")
    console.print(f"[green]Wrote tasks to[/green] {task_file}")


def _run_extract_action(cfg: DictConfig) -> None:
    """Execute the ``extract`` CLI action."""
    if not cfg.get("tasks"):
        console.print(
            "[red]tasks pickle file path is required for extract action.[/red]"
        )
        sys.exit(1)

    tasks_path = Path(cfg.tasks)
    if not tasks_path.exists():
        console.print(f"[red]Tasks file not found:[/red] {tasks_path}")
        sys.exit(1)

    task_list = pickle.loads(tasks_path.read_bytes())

    if cfg.get("overwrite") is not None:
        task_list = [
            attrs.evolve(
                task,
                job=task.job.model_copy(update={"overwrite": cfg.overwrite}),
            )
            for task in task_list
        ]

    backend = LocalProcessBackend(max_workers=cfg.workers)
    client = AereoClient()
    artifacts = _run_with_exit(
        "Extraction", client.execute_tasks, task_list, backend=backend
    )

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "artifacts.parquet"
    artifacts.to_parquet(parquet_path)

    console.print(f"[green]✓ Extracted {len(artifacts)} artifacts.[/green]")
    console.print(f"[green]Parquet saved to:[/green] {parquet_path}")
    console.print(f"[green]Output directory:[/green] {output_dir}")


def _run_run_action(cfg: DictConfig) -> None:
    """Execute the full ``run`` pipeline action."""
    if not cfg.get("search"):
        console.print(
            "[red]No search provider configuration provided (search key is missing).[/red]"
        )
        sys.exit(1)

    search_provider = _build_search_provider(cfg)

    pipeline = hydra.utils.instantiate(cfg.pipeline)
    grid_config = hydra.utils.instantiate(cfg.grid_config)
    patch_config = hydra.utils.instantiate(cfg.patch_config)
    task_builder = hydra.utils.instantiate(cfg.task_builder)
    extract = _pipeline_to_extract(pipeline)
    if extract is None:
        console.print(
            "[red]pipeline must include a Reader plugin as its first element.[/red]"
        )
        sys.exit(1)

    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_aoi = _resolve_target_aoi(cfg, fallback=search_provider.intersects)

    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=patch_config,
        output_uri=cfg.get("output_uri") or str(output_dir),
        extract=extract,
        target_aoi=target_aoi,
        overwrite=cfg.overwrite,
    )

    client = AereoClient()

    # Search
    console.print("[bold blue]🔍 Searching...[/bold blue]")
    results = _run_with_exit("Search", client.search, search_provider=search_provider)
    _check_results(results)
    console.print(f"[green]✓ Found {len(results)} scenes.[/green]")

    # Prepare
    console.print("[bold blue]📦 Preparing...[/bold blue]")
    tasks = _run_with_exit(
        "Prepare",
        task_builder,
        search_results=results,
        job=job,
    )
    chunk_size = getattr(task_builder, "cells_per_task", None)
    chunk_msg = f" (chunk size: {chunk_size})" if chunk_size is not None else ""
    console.print(f"[green]✓ Prepared {len(tasks)} tasks{chunk_msg}.[/green]")

    # Extract
    console.print("[bold blue]⛏️ Extracting...[/bold blue]")
    backend = LocalProcessBackend(max_workers=cfg.workers)
    artifacts = _run_with_exit(
        "Extraction", client.execute_tasks, tasks, backend=backend
    )

    parquet_path = output_dir / "artifacts.parquet"
    artifacts.to_parquet(parquet_path)

    console.print(f"[green]✓ Extracted {len(artifacts)} artifacts.[/green]")
    console.print(f"[green]Parquet saved to:[/green] {parquet_path}")
    console.print(f"[green]Output:[/green] {output_dir}")


def _run_validate_action(cfg: DictConfig) -> None:
    """Execute the ``validate`` CLI action."""
    try:
        if cfg.get("search"):
            hydra.utils.instantiate(cfg.search)
        if cfg.get("task_builder"):
            hydra.utils.instantiate(cfg.task_builder)
        if cfg.get("pipeline"):
            hydra.utils.instantiate(cfg.pipeline)
        if cfg.get("grid_config"):
            hydra.utils.instantiate(cfg.grid_config)
        if cfg.get("patch_config"):
            hydra.utils.instantiate(cfg.patch_config)
        console.print("[green]✓ Configuration is valid.[/green]")
    except Exception as exc:
        console.print(f"[red]✗ Configuration is invalid:[/red] {exc}")
        sys.exit(1)


def _run_plugin_params_action(cfg: DictConfig) -> None:
    """Execute the ``plugin_params`` CLI action."""
    if not cfg.get("plugin_name"):
        console.print("[red]plugin_name is required for plugin_params action.[/red]")
        sys.exit(1)
    plugin_params_cmd(cfg.plugin_name)


# ---------------------------------------------------------------------------
# Main Entry Point with Hydra
# ---------------------------------------------------------------------------


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    """Main execution entry point loaded by Hydra."""
    _configure_verbose_logging(cfg.verbose)

    action = cfg.get("action", "run")
    runners: dict[str, Callable[[DictConfig], None]] = {
        "search": _run_search_action,
        "prepare": _run_prepare_action,
        "extract": _run_extract_action,
        "run": _run_run_action,
        "validate": _run_validate_action,
        "plugins": plugins_cmd,
        "plugin_params": _run_plugin_params_action,
    }

    runner = runners.get(action)
    if runner is None:
        console.print(f"[red]Unknown action: {action}[/red]")
        sys.exit(1)
    runner(cfg)


if __name__ == "__main__":
    main()
