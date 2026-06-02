"""AEREO CLI — command-line interface for the AEREO satellite data framework."""

# ruff: noqa: E402
from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable

import geopandas as gpd
import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend
from aereo.interfaces import AereoProfile, GridConfig
from aereo.schemas import AssetSchema

app = typer.Typer(
    name="aereo",
    help="AEREO — Modular satellite data discovery, extraction, and processing",
    no_args_is_help=True,
)
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


def _load_grid_config(path: Path | None) -> GridConfig:
    """Load a GridConfig from YAML, or return defaults.

    Args:
        path: Path to grid config YAML, or None.

    Returns:
        Loaded GridConfig, or a default instance if path is None or missing.
    """
    return GridConfig.from_yaml(path) if path and path.exists() else GridConfig()


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


def _load_profiles(paths: list[Path]) -> list[AereoProfile]:
    """Load AereoProfile instances from YAML file paths.

    Args:
        paths: List of paths to profile YAML files.

    Returns:
        List of loaded AereoProfile instances.

    Raises:
        typer.Exit: If a profile file is not found.
    """
    profiles: list[AereoProfile] = []
    for p in paths:
        if not p.exists():
            console.print(f"[red]Profile not found:[/red] {p}")
            raise typer.Exit(code=1)
        profiles.extend(AereoProfile.from_yaml(p))
    return profiles


def _validate_yaml(path: Path, loader: Callable[[Path], Any], label: str) -> None:
    """Validate a YAML file using the given schema loader.

    Args:
        path: Path to the YAML file.
        loader: Callable that loads and validates the file.
        label: Human-readable label for error messages.

    Raises:
        typer.Exit: If the file is not found or validation fails.
    """
    if not path.exists():
        console.print(f"[red]{label} not found:[/red] {path}")
        raise typer.Exit(code=1)
    try:
        loader(path)
        console.print(f"[green]✓ {label} valid:[/green] {path}")
    except Exception as exc:
        console.print(f"[red]✗ {label} invalid:[/red] {path}\n{exc}")
        raise typer.Exit(code=1)


def _add_plugin_rows(table: Table, label: str, plugins: dict[str, type]) -> None:
    """Add plugin summary rows to a Rich table.

    Args:
        table: Rich Table to append rows to.
        label: Human-readable plugin type label.
        plugins: Mapping of plugin name to plugin class.
    """
    for name, cls in plugins.items():
        cols = ", ".join(cls.supported_collections[:3])
        if len(cls.supported_collections) > 3:
            cols += " ..."
        req = str(len(getattr(cls, "required_params", [])))
        opt = str(len(getattr(cls, "optional_params", [])))
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

    Raises:
        typer.Exit: With code 1 if *fn* raises an exception.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        console.print(f"[red]{label} failed:[/red] {exc}")
        raise typer.Exit(code=1)


def _check_results(results: gpd.GeoDataFrame | None) -> None:
    """Exit if search results are empty or None.

    Args:
        results: GeoDataFrame from a search operation.

    Raises:
        typer.Exit: With code 2 if *results* is None or empty.
    """
    if results is None or len(results) == 0:
        console.print("[yellow]No results found.[/yellow]")
        raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def search(
    profile: Annotated[
        list[Path],
        typer.Option("--profile", "-p", help="Path to profile YAML (repeatable)"),
    ],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to grid config YAML")
    ] = None,
    geojson: Annotated[
        Path | None, typer.Option("--geojson", "-g", help="Path to AOI GeoJSON file")
    ] = None,
    start: Annotated[
        str | None, typer.Option("--start", "-s", help="Start datetime (ISO 8601)")
    ] = None,
    end: Annotated[
        str | None, typer.Option("--end", "-e", help="End datetime (ISO 8601)")
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output JSON file for search results"),
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: table or json")
    ] = "table",
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Search for satellite data across configured profiles.

    Args:
        profile: Paths to profile YAML files.
        config: Optional path to grid config YAML.
        geojson: Optional path to AOI GeoJSON file.
        start: Optional start datetime (ISO 8601).
        end: Optional end datetime (ISO 8601).
        output: Optional output JSON file path.
        fmt: Output format ("table" or "json").
        verbose: Enable verbose logging.

    Returns:
        None. Prints results or writes to output file.
    """
    _configure_verbose_logging(verbose)
    profiles = _load_profiles(profile)

    # Load geometry
    intersects = _load_geometry_safe(geojson)

    # Parse datetimes
    start_dt = _parse_iso_datetime(start)
    end_dt = _parse_iso_datetime(end)

    client = AereoClient()
    results = _run_with_exit(
        "Search",
        client.search,
        profiles=profiles,
        intersects=intersects,
        start_datetime=start_dt,
        end_datetime=end_dt,
    )
    _check_results(results)

    if fmt == "json":
        records = _search_results_to_json(results)
        json_out = json.dumps(records, indent=2, default=str)
        if output:
            output.write_text(json_out)
            console.print(f"[green]Wrote {len(records)} results to[/green] {output}")
        else:
            console.print(json_out)
    else:
        _print_search_table(results)
        if output:
            records = _search_results_to_json(results)
            output.write_text(json.dumps(records, indent=2, default=str))
            console.print(f"[green]Wrote results to[/green] {output}")


@app.command()
def prepare(
    search_results: Annotated[Path, typer.Argument(help="Path to search results JSON")],
    profile: Annotated[
        list[Path],
        typer.Option("--profile", "-p", help="Path to profile YAML (repeatable)"),
    ],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to grid config YAML")
    ] = None,
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-d", help="Output directory for extraction")
    ] = Path("./out"),
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output pickle file for tasks"),
    ] = None,
    cells_per_task: Annotated[
        int, typer.Option("--cells-per-task", help="Max grid cells per task")
    ] = 50,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Prepare search results for extraction.

    Args:
        search_results: Path to search results JSON.
        profile: Paths to profile YAML files.
        config: Optional path to grid config YAML.
        output_dir: Output directory for extraction tasks.
        output: Optional pickle file path for tasks.
        cells_per_task: Max grid cells per task.
        verbose: Enable verbose logging.

    Returns:
        None. Writes prepared tasks to a pickle file.
    """
    _configure_verbose_logging(verbose)

    if not search_results.exists():
        console.print(f"[red]Search results not found:[/red] {search_results}")
        raise typer.Exit(code=1)

    records = json.loads(search_results.read_text())
    df = _search_results_from_json(records)

    profiles = _load_profiles(profile)

    grid_config = _load_grid_config(config)

    output_dir.mkdir(parents=True, exist_ok=True)

    client = AereoClient()
    tasks = _run_with_exit(
        "Prepare",
        client.prepare_for_extraction,
        search_results=df,  # type: ignore[arg-type]
        grid_config=grid_config,
        profiles=profiles,
        uri=str(output_dir),
        cells_per_task=cells_per_task,
    )

    task_file = output or (output_dir / "tasks.pkl")
    task_file.write_bytes(pickle.dumps(tasks))
    console.print(
        f"[green]✓ Prepared {len(tasks)} tasks (chunk size: {cells_per_task}).[/green]"
    )
    console.print(f"[green]Wrote tasks to[/green] {task_file}")


@app.command()
def extract(
    tasks: Annotated[Path, typer.Argument(help="Path to prepared tasks pickle file")],
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-d", help="Output directory")
    ] = Path("./out"),
    workers: Annotated[
        int, typer.Option("--workers", "-w", help="Max batch workers")
    ] = 1,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Run extraction on prepared tasks.

    Args:
        tasks: Path to prepared tasks pickle file.
        output_dir: Output directory for artifacts.
        workers: Max batch workers.
        verbose: Enable verbose logging.

    Returns:
        None. Writes extracted artifacts to parquet.
    """
    _configure_verbose_logging(verbose)

    if not tasks.exists():
        console.print(f"[red]Tasks file not found:[/red] {tasks}")
        raise typer.Exit(code=1)

    task_list = pickle.loads(tasks.read_bytes())

    backend = LocalProcessBackend(max_workers=workers)
    client = AereoClient()
    artifacts = _run_with_exit(
        "Extraction", client.execute_tasks, task_list, backend=backend
    )

    # Write full GeoDataFrame to parquet
    parquet_path = output_dir / "artifacts.parquet"
    artifacts.to_parquet(parquet_path)

    console.print(f"[green]✓ Extracted {len(artifacts)} artifacts.[/green]")
    console.print(f"[green]Parquet saved to:[/green] {parquet_path}")
    console.print(f"[green]Output directory:[/green] {output_dir}")


@app.command()
def run(
    profile: Annotated[
        list[Path],
        typer.Option("--profile", "-p", help="Path to profile YAML (repeatable)"),
    ],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to grid config YAML")
    ] = None,
    geojson: Annotated[
        Path | None, typer.Option("--geojson", "-g", help="Path to AOI GeoJSON file")
    ] = None,
    start: Annotated[
        str | None, typer.Option("--start", "-s", help="Start datetime (ISO 8601)")
    ] = None,
    end: Annotated[
        str | None, typer.Option("--end", "-e", help="End datetime (ISO 8601)")
    ] = None,
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-d", help="Output directory")
    ] = Path("./out"),
    workers: Annotated[
        int, typer.Option("--workers", "-w", help="Max batch workers")
    ] = 1,
    cells_per_task: Annotated[
        int, typer.Option("--cells-per-task", help="Max grid cells per task")
    ] = 50,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """One-shot: search → prepare → extract.

    Args:
        profile: Paths to profile YAML files.
        config: Optional path to grid config YAML.
        geojson: Optional path to AOI GeoJSON file.
        start: Optional start datetime (ISO 8601).
        end: Optional end datetime (ISO 8601).
        output_dir: Output directory for artifacts.
        workers: Max batch workers.
        cells_per_task: Max grid cells per task.
        verbose: Enable verbose logging.

    Returns:
        None. Writes extracted artifacts to parquet.
    """
    _configure_verbose_logging(verbose)
    profiles = _load_profiles(profile)

    grid_config = _load_grid_config(config)
    intersects = _load_geometry_safe(geojson)
    start_dt = _parse_iso_datetime(start)
    end_dt = _parse_iso_datetime(end)

    output_dir.mkdir(parents=True, exist_ok=True)
    client = AereoClient()

    # Search
    console.print("[bold blue]🔍 Searching...[/bold blue]")
    results = _run_with_exit(
        "Search",
        client.search,
        profiles=profiles,
        intersects=intersects,
        start_datetime=start_dt,
        end_datetime=end_dt,
    )
    _check_results(results)
    console.print(f"[green]✓ Found {len(results)} scenes.[/green]")

    # Prepare
    console.print("[bold blue]📦 Preparing...[/bold blue]")
    tasks = _run_with_exit(
        "Prepare",
        client.prepare_for_extraction,
        search_results=results,
        grid_config=grid_config,
        profiles=profiles,
        uri=str(output_dir),
        cells_per_task=cells_per_task,
    )
    console.print(
        f"[green]✓ Prepared {len(tasks)} tasks (chunk size: {cells_per_task}).[/green]"
    )

    # Extract
    console.print("[bold blue]⛏️ Extracting...[/bold blue]")
    backend = LocalProcessBackend(max_workers=workers)
    artifacts = _run_with_exit(
        "Extraction", client.execute_tasks, tasks, backend=backend
    )

    parquet_path = output_dir / "artifacts.parquet"
    artifacts.to_parquet(parquet_path)

    console.print(f"[green]✓ Extracted {len(artifacts)} artifacts.[/green]")
    console.print(f"[green]Parquet saved to:[/green] {parquet_path}")
    console.print(f"[green]Output:[/green] {output_dir}")


@app.command()
def validate(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config YAML to validate"),
    ] = None,
    profile: Annotated[
        Path | None,
        typer.Option("--profile", "-p", help="Path to profile YAML to validate"),
    ] = None,
) -> None:
    """Validate a config or profile YAML against AEREO schemas.

    Args:
        config: Optional path to config YAML to validate.
        profile: Optional path to profile YAML to validate.

    Returns:
        None. Prints validation result.
    """
    if config:
        _validate_yaml(config, GridConfig.from_yaml, "Config")

    if profile:
        _validate_yaml(profile, AereoProfile.from_yaml, "Profile")

    if not config and not profile:
        console.print("[yellow]Provide --config or --profile to validate.[/yellow]")
        raise typer.Exit(code=1)


@app.command()
def plugins() -> None:
    """List installed AEREO plugins.

    Returns:
        None. Prints a table of installed plugins.
    """
    from aereo.registry import AereoRegistry

    registry = AereoRegistry()

    table = Table(title="Installed AEREO Plugins")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Collections", style="green")
    table.add_column("Required", style="yellow")
    table.add_column("Optional", style="blue")

    _add_plugin_rows(table, "Searcher", registry._searchers)

    for label in ("reader", "reprojector", "processor", "writer"):
        _add_plugin_rows(table, label.capitalize(), registry._registries[label].plugins)

    console.print(table)


@app.command()
def plugin_params(name: str) -> None:
    """Show parameters for a specific AEREO plugin.

    Args:
        name: Name of the plugin to inspect.

    Returns:
        None. Prints a table of plugin parameters.
    """
    from aereo.registry import AereoRegistry

    registry = AereoRegistry()
    try:
        params = registry.get_plugin_params(name)
    except KeyError:
        console.print(f"[red]Plugin '{name}' not found.[/red]")
        raise typer.Exit(code=1)

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


# Entry point for `python -m aer.cli`
if __name__ == "__main__":
    app()
