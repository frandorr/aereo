"""AEREO CLI — command-line interface for the AEREO satellite data framework."""

# ruff: noqa: E402
from __future__ import annotations

import json
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import hydra
import pandas as pd
from omegaconf import DictConfig
from rich.console import Console
from rich.table import Table

from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend
from aereo.schemas import AssetSchema
from aereo.registry import AereoRegistry

console = Console()


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
    if data.get("type") == "FeatureCollection":
        if not data.get("features"):
            raise ValueError("GeoJSON FeatureCollection has no features.")
        return data["features"][0]["geometry"]
    elif data.get("type") == "Feature":
        return data["geometry"]
    elif "type" in data and data["type"] in (
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    ):
        return data
    raise ValueError("Could not extract geometry from GeoJSON.")


def _load_geometry_safe(path: Path | None) -> dict[str, Any] | None:
    """Load geometry from GeoJSON if path is provided and exists.

    Args:
        path: Path to GeoJSON file, or None.

    Returns:
        Geometry dictionary, or None if path is None or missing.
    """
    return _load_geometry(path) if path and path.exists() else None


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
        df = df.set_crs(epsg=4326)
        if df is None:
            raise ValueError("Failed to construct GeoDataFrame from records.")
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

    for row in df.head(50).itertuples(index=False):
        table.add_row(
            str(getattr(row, "id", "")),
            str(getattr(row, "collection", "")),
            str(getattr(row, "start_time", "")),
            str(getattr(row, "end_time", "")),
            str(getattr(row, "href", ""))[:60] + "...",
        )
    if len(df) > 50:
        table.add_row("...", f"... and {len(df) - 50} more rows", "", "", "")
    console.print(table)


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
        reg_key = label.lower()
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


def plugins_cmd() -> None:
    """List installed AEREO plugins."""
    registry = AereoRegistry()

    table = Table(title="Installed AEREO Plugins")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Collections", style="green")
    table.add_column("Required", style="yellow")
    table.add_column("Optional", style="blue")

    _add_plugin_rows(table, "Searcher", registry._searchers, registry)

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
# Main Entry Point with Hydra
# ---------------------------------------------------------------------------


@hydra.main(version_base=None, config_path="conf", config_name="config")
def main(cfg: DictConfig) -> None:
    """Main execution entry point loaded by Hydra."""
    # Setup logging
    _configure_verbose_logging(cfg.verbose)

    action = cfg.get("action", "run")

    if action == "search":
        if not cfg.get("search"):
            console.print(
                "[red]No search provider configuration provided (search key is missing).[/red]"
            )
            sys.exit(1)

        search_provider = hydra.utils.instantiate(cfg.search)

        update_dict = {}
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

        client = AereoClient()
        results = _run_with_exit(
            "Search",
            client.search,
            search_provider=search_provider,
        )
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

    elif action == "prepare":
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

        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        client = AereoClient()
        tasks = _run_with_exit(
            "Prepare",
            client.prepare_tasks,
            search_results=df,
            grid_config=grid_config,
            pipeline=pipeline,
            uri=str(output_dir),
            cells_per_task=cfg.cells_per_task,
        )

        task_file = Path(cfg.output) if cfg.output else (output_dir / "tasks.pkl")
        task_file.write_bytes(pickle.dumps(tasks))
        console.print(
            f"[green]✓ Prepared {len(tasks)} tasks (chunk size: {cfg.cells_per_task}).[/green]"
        )
        console.print(f"[green]Wrote tasks to[/green] {task_file}")

    elif action == "extract":
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

    elif action == "run":
        if not cfg.get("search"):
            console.print(
                "[red]No search provider configuration provided (search key is missing).[/red]"
            )
            sys.exit(1)

        search_provider = hydra.utils.instantiate(cfg.search)

        update_dict = {}
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

        pipeline = hydra.utils.instantiate(cfg.pipeline)
        grid_config = hydra.utils.instantiate(cfg.grid_config)

        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        client = AereoClient()

        # Search
        console.print("[bold blue]🔍 Searching...[/bold blue]")
        results = _run_with_exit(
            "Search",
            client.search,
            search_provider=search_provider,
        )
        _check_results(results)
        console.print(f"[green]✓ Found {len(results)} scenes.[/green]")

        # Prepare
        console.print("[bold blue]📦 Preparing...[/bold blue]")
        tasks = _run_with_exit(
            "Prepare",
            client.prepare_tasks,
            search_results=results,
            pipeline=pipeline,
            grid_config=grid_config,
            uri=str(output_dir),
            cells_per_task=cfg.cells_per_task,
        )
        console.print(
            f"[green]✓ Prepared {len(tasks)} tasks (chunk size: {cfg.cells_per_task}).[/green]"
        )

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

    elif action == "validate":
        # Simply attempting to load and validate model signatures
        # Since Hydra does instantiation, validation happens during loading.
        try:
            if cfg.get("search"):
                hydra.utils.instantiate(cfg.search)
            if cfg.get("pipeline"):
                hydra.utils.instantiate(cfg.pipeline)
            if cfg.get("grid_config"):
                hydra.utils.instantiate(cfg.grid_config)
            console.print("[green]✓ Configuration is valid.[/green]")
        except Exception as exc:
            console.print(f"[red]✗ Configuration is invalid:[/red] {exc}")
            sys.exit(1)

    elif action == "plugins":
        plugins_cmd()

    elif action == "plugin_params":
        if not cfg.get("plugin_name"):
            console.print(
                "[red]plugin_name is required for plugin_params action.[/red]"
            )
            sys.exit(1)
        plugin_params_cmd(cfg.plugin_name)

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
