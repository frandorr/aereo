"""AER CLI — command-line interface for the AER satellite data framework."""

from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

import geopandas as gpd
import typer
from rich.console import Console
from rich.table import Table

from aer.client import AerClient
from aer.execution import LocalProcessBackend
from aer.interfaces import AerProfile, GridConfig
from aer.schemas import AssetSchema

app = typer.Typer(
    name="aer",
    help="AER — Modular satellite data discovery, extraction, and processing",
    no_args_is_help=True,
)
console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_geometry(geojson_path: Path) -> Optional[dict[str, Any]]:
    """Load a GeoJSON file and return the geometry dict."""
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


def _search_results_to_json(df: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Convert search results GeoDataFrame to JSON-serializable records."""
    # Convert to GeoJSON feature collection then to simple records
    df = df.copy()
    df["geometry"] = df.geometry.apply(
        lambda g: g.__geo_interface__ if g is not None else None
    )
    records = df.to_dict(orient="records")
    # Convert datetime to ISO strings
    for rec in records:
        for key in ("start_time", "end_time"):
            if key in rec and rec[key] is not None:
                rec[key] = (
                    rec[key].isoformat() if hasattr(rec[key], "isoformat") else rec[key]
                )
    return records


def _search_results_from_json(records: list[dict[str, Any]]) -> Any:
    """Reconstruct a GeoDataFrame from JSON records."""
    df = gpd.GeoDataFrame.from_records(records)
    if "geometry" in df.columns:
        from shapely.geometry import shape

        def _to_geom(g: Any) -> Any:
            if isinstance(g, dict):
                return shape(g)
            return g

        df["geometry"] = gpd.GeoSeries(df["geometry"].apply(_to_geom))
        df = gpd.GeoDataFrame(df, geometry="geometry")
        df.set_crs(epsg=4326, inplace=True)
    for key in ("start_time", "end_time"):
        if key in df.columns:
            df[key] = gpd.pd.to_datetime(df[key])
    return gpd.GeoDataFrame(AssetSchema.validate(df))


def _print_search_table(df: gpd.GeoDataFrame) -> None:
    """Pretty-print search results as a Rich table."""
    table = Table(title=f"Search Results ({len(df)} scenes)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Collection", style="magenta")
    table.add_column("Start Time", style="green")
    table.add_column("End Time", style="green")
    table.add_column("Href", style="blue", overflow="fold")

    for _, row in df.head(50).iterrows():
        table.add_row(
            str(row.get("id", "")),
            str(row.get("collection", "")),
            str(row.get("start_time", "")),
            str(row.get("end_time", "")),
            str(row.get("href", ""))[:60] + "...",
        )
    if len(df) > 50:
        table.add_row("...", f"... and {len(df) - 50} more rows", "", "", "")
    console.print(table)


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
        Optional[Path], typer.Option("--config", "-c", help="Path to grid config YAML")
    ] = None,
    geojson: Annotated[
        Optional[Path], typer.Option("--geojson", "-g", help="Path to AOI GeoJSON file")
    ] = None,
    start: Annotated[
        Optional[str], typer.Option("--start", "-s", help="Start datetime (ISO 8601)")
    ] = None,
    end: Annotated[
        Optional[str], typer.Option("--end", "-e", help="End datetime (ISO 8601)")
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output JSON file for search results"),
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: table or json")
    ] = "table",
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Search for satellite data across configured profiles."""
    if verbose:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))

    # Load profiles
    profiles: list[AerProfile] = []
    for p in profile:
        if not p.exists():
            console.print(f"[red]Profile not found:[/red] {p}")
            raise typer.Exit(code=1)
        profiles.extend(AerProfile.from_yaml(p))

    # Load geometry
    intersects = _load_geometry(geojson) if geojson and geojson.exists() else None

    # Parse datetimes
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    client = AerClient()
    try:
        results = client.search(
            profiles=profiles,
            intersects=intersects,
            start_datetime=start_dt,
            end_datetime=end_dt,
        )
    except Exception as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        raise typer.Exit(code=1)

    if results is None or len(results) == 0:
        console.print("[yellow]No results found.[/yellow]")
        raise typer.Exit(code=2)

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
        Optional[Path], typer.Option("--config", "-c", help="Path to grid config YAML")
    ] = None,
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-d", help="Output directory for extraction")
    ] = Path("./out"),
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output pickle file for tasks"),
    ] = None,
    cells_per_chunk: Annotated[
        int, typer.Option("--cells-per-chunk", help="Max grid cells per task")
    ] = 50,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """Prepare search results for extraction."""
    if verbose:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))

    if not search_results.exists():
        console.print(f"[red]Search results not found:[/red] {search_results}")
        raise typer.Exit(code=1)

    records = json.loads(search_results.read_text())
    df = _search_results_from_json(records)

    profiles: list[AerProfile] = []
    for p in profile:
        if not p.exists():
            console.print(f"[red]Profile not found:[/red] {p}")
            raise typer.Exit(code=1)
        profiles.extend(AerProfile.from_yaml(p))

    grid_config = (
        GridConfig.from_yaml(config) if config and config.exists() else GridConfig()
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    client = AerClient()
    try:
        tasks = client.prepare_for_extraction(
            search_results=df,  # type: ignore[arg-type]
            grid_config=grid_config,
            profiles=profiles,
            uri=str(output_dir),
            cells_per_chunk=cells_per_chunk,
        )
    except Exception as exc:
        console.print(f"[red]Prepare failed:[/red] {exc}")
        raise typer.Exit(code=1)

    task_file = output or (output_dir / "tasks.pkl")
    task_file.write_bytes(pickle.dumps(tasks))
    console.print(
        f"[green]✓ Prepared {len(tasks)} tasks (chunk size: {cells_per_chunk}).[/green]"
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
    """Run extraction on prepared tasks."""
    if verbose:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))

    if not tasks.exists():
        console.print(f"[red]Tasks file not found:[/red] {tasks}")
        raise typer.Exit(code=1)

    task_list = pickle.loads(tasks.read_bytes())

    backend = LocalProcessBackend(max_workers=workers)
    client = AerClient()
    try:
        artifacts = client.execute_tasks(task_list, backend=backend)
    except Exception as exc:
        console.print(f"[red]Extraction failed:[/red] {exc}")
        raise typer.Exit(code=1)

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
        Optional[Path], typer.Option("--config", "-c", help="Path to grid config YAML")
    ] = None,
    geojson: Annotated[
        Optional[Path], typer.Option("--geojson", "-g", help="Path to AOI GeoJSON file")
    ] = None,
    start: Annotated[
        Optional[str], typer.Option("--start", "-s", help="Start datetime (ISO 8601)")
    ] = None,
    end: Annotated[
        Optional[str], typer.Option("--end", "-e", help="End datetime (ISO 8601)")
    ] = None,
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-d", help="Output directory")
    ] = Path("./out"),
    workers: Annotated[
        int, typer.Option("--workers", "-w", help="Max batch workers")
    ] = 1,
    cells_per_chunk: Annotated[
        int, typer.Option("--cells-per-chunk", help="Max grid cells per task")
    ] = 50,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
) -> None:
    """One-shot: search → prepare → extract."""
    if verbose:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))

    # Load profiles
    profiles: list[AerProfile] = []
    for p in profile:
        if not p.exists():
            console.print(f"[red]Profile not found:[/red] {p}")
            raise typer.Exit(code=1)
        profiles.extend(AerProfile.from_yaml(p))

    grid_config = (
        GridConfig.from_yaml(config) if config and config.exists() else GridConfig()
    )
    intersects = _load_geometry(geojson) if geojson and geojson.exists() else None
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    output_dir.mkdir(parents=True, exist_ok=True)
    client = AerClient()

    # Search
    console.print("[bold blue]🔍 Searching...[/bold blue]")
    try:
        results = client.search(
            profiles=profiles,
            intersects=intersects,
            start_datetime=start_dt,
            end_datetime=end_dt,
        )
    except Exception as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        raise typer.Exit(code=1)

    if results is None or len(results) == 0:
        console.print("[yellow]No results found.[/yellow]")
        raise typer.Exit(code=2)
    console.print(f"[green]✓ Found {len(results)} scenes.[/green]")

    # Prepare
    console.print("[bold blue]📦 Preparing...[/bold blue]")
    try:
        tasks = client.prepare_for_extraction(
            search_results=results,
            grid_config=grid_config,
            profiles=profiles,
            uri=str(output_dir),
            cells_per_chunk=cells_per_chunk,
        )
    except Exception as exc:
        console.print(f"[red]Prepare failed:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(
        f"[green]✓ Prepared {len(tasks)} tasks (chunk size: {cells_per_chunk}).[/green]"
    )

    # Extract
    console.print("[bold blue]⛏️ Extracting...[/bold blue]")
    backend = LocalProcessBackend(max_workers=workers)
    try:
        artifacts = client.execute_tasks(tasks, backend=backend)
    except Exception as exc:
        console.print(f"[red]Extraction failed:[/red] {exc}")
        raise typer.Exit(code=1)

    parquet_path = output_dir / "artifacts.parquet"
    artifacts.to_parquet(parquet_path)

    console.print(f"[green]✓ Extracted {len(artifacts)} artifacts.[/green]")
    console.print(f"[green]Parquet saved to:[/green] {parquet_path}")
    console.print(f"[green]Output:[/green] {output_dir}")


@app.command()
def validate(
    config: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config YAML to validate"),
    ] = None,
    profile: Annotated[
        Optional[Path],
        typer.Option("--profile", "-p", help="Path to profile YAML to validate"),
    ] = None,
) -> None:
    """Validate a config or profile YAML against AER schemas."""
    if config:
        if not config.exists():
            console.print(f"[red]Config not found:[/red] {config}")
            raise typer.Exit(code=1)
        try:
            GridConfig.from_yaml(config)
            console.print(f"[green]✓ Config valid:[/green] {config}")
        except Exception as exc:
            console.print(f"[red]✗ Config invalid:[/red] {config}\n{exc}")
            raise typer.Exit(code=1)

    if profile:
        if not profile.exists():
            console.print(f"[red]Profile not found:[/red] {profile}")
            raise typer.Exit(code=1)
        try:
            AerProfile.from_yaml(profile)
            console.print(f"[green]✓ Profile valid:[/green] {profile}")
        except Exception as exc:
            console.print(f"[red]✗ Profile invalid:[/red] {profile}\n{exc}")
            raise typer.Exit(code=1)

    if not config and not profile:
        console.print("[yellow]Provide --config or --profile to validate.[/yellow]")
        raise typer.Exit(code=1)


@app.command()
def plugins() -> None:
    """List installed AER plugins."""
    from aer.registry import AerRegistry

    registry = AerRegistry()

    table = Table(title="Installed AER Plugins")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Collections", style="green")

    for name, cls in registry._searchers.items():
        cols = ", ".join(cls.supported_collections[:3])
        if len(cls.supported_collections) > 3:
            cols += " ..."
        table.add_row("Searcher", name, cols)

    for name, cls in registry._extractors.items():
        cols = ", ".join(cls.supported_collections[:3])
        if len(cls.supported_collections) > 3:
            cols += " ..."
        table.add_row("Extractor", name, cols)

    console.print(table)


# Entry point for `python -m aer.cli`
if __name__ == "__main__":
    app()
