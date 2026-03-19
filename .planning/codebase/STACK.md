# Tech Stack

## Languages & Runtime

- **Python 3.13+** — Primary language (3.13, 3.14 supported)
- **Type System**: Pydantic, attrs, returns (monadic error handling)

## Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pandas` | >=3.0.1 | DataFrame operations |
| `geopandas` | >=1.1.2 | Geospatial DataFrames |
| `pyarrow` | >=23.0.1 | Arrow format support |
| `shapely` | >=2.1.2 | Geometry operations |
| `pydantic` | >=2.12.5 | Type validation |
| `attrs` | >=25.4 | Immutable data classes |
| `returns` | >=0.26 | Monadic error handling (`Result`, `Maybe`) |
| `structlog` | >=25.5 | Structured logging |
| `pandera` | >=0.24 | DataFrame validation |
| `pyresample` | >=1.35 | Spatial resampling |
| `pyproj` | >=3.7.1 | CRS transformations |
| `utm` | >=0.8.1 | UTM coordinate conversion |

## Earth Observation Dependencies

| Package | Purpose |
|---------|---------|
| `satpy` | Satellite data processing |
| `pyhdf` | HDF file format support |
| `python-geotiepoints` | Geolocation interpolation |

## Cloud/Storage

| Package | Purpose |
|---------|---------|
| `s3fs` | S3 filesystem access |

## Visualization

| Package | Purpose |
|---------|---------|
| `matplotlib` | Plotting |
| `geopandas` | Geospatial visualization |

## Optional Search Plugins

- `aer-search-aws-goes` — AWS GOES data (optional)
- `aer-search-earthaccess` — NASA Earthdata (optional)

## Build & Development Tools

- **Build**: `hatchling`, `hatch-polylith-bricks`
- **Package Manager**: `uv`
- **Testing**: `pytest` (>=9.0.2)
- **Linting**: `ruff` (with `--fix`), `ruff-format`
- **Type Checking**: `mypy` (strict mode)
- **Pre-commit**: `.pre-commit-config.yaml` (ruff, mypy, pyproject-fmt)

## Configuration Files

- `pyproject.toml` — Root workspace config, mypy, pytest, polylith settings
- `workspace.toml` — Polylith namespace config
- `projects/*/pyproject.toml` — Per-project dependency definitions

## Entry Points

```
aer.plugins.search = {earthaccess, ...}  # Search methods
```
