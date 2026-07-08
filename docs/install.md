# Install

AerEO is a Python 3.12+ orchestration framework. The core package includes
built-in search (STAC, NASA Earthaccess, etc.), read, reproject, and write
functions. Sensor-specific plugins are installed separately, so you only ship
what you need.

## Requirements

- Python **3.12** or newer
- `pip` or `uv`
- Credentials for any catalog that requires them (see below)

## Quick install

=== "STAC (Sentinel-2, Landsat, etc.)"

    ```bash
    uv add aereo
    # or
    pip install aereo
    ```

=== "NASA Earthaccess (MODIS, VIIRS, Sentinel-3, etc.)"

    ```bash
    uv add aereo aereo-read-satpy
    # or
    pip install aereo aereo-read-satpy
    ```

    Configure [earthaccess](https://github.com/nsidc/earthaccess) credentials
    (`.netrc`, environment variables, or `earthaccess.login()`) before searching.

=== "GOES ABI (public S3)"

    ```bash
    uv add aereo aereo-search-aws-goes aereo-read-satpy
    # or
    pip install aereo aereo-search-aws-goes aereo-read-satpy
    ```

    GOES data on AWS is public, so no authentication is required.

=== "GeoTessera"

    ```bash
    uv add aereo aereo-search-tessera aereo-read-tessera
    # or
    pip install aereo aereo-search-tessera aereo-read-tessera
    ```

    GeoTessera data is public, so no authentication is required.

Install the core framework with `uv add aereo` (or `pip install aereo`), then
add plugins for search, read, reproject, or write stages. By combining plugins
you can access hundreds of constellations without changing your pipeline.

## Optional extras

AerEO's core install covers STAC search, ODC-based reprojection, GeoTIFF writing,
and local execution. A few built-in capabilities need extra dependencies:

| Extra | Enables | Install |
|---|---|---|
| `serverless` | `LambdaExecutor` and S3 staging (via `boto3`) | `uv add aereo[serverless]` |
| `swath` | `reproject_swath` / `reproject_pyresample` for 2-D lat/lon swath data | `uv add aereo[swath]` |
| `viz` | Cartopy-backed plots in `aereo.viz` | `uv add aereo[viz]` |
| `all` | Everything above in one command | `uv add aereo[all]` |

## Verify the installation

```python
from aereo.pipeline import ExtractionJob
from aereo.builtins import search_stac, build_grouped_tasks
from aereo.executors import LocalExecutor

print("AerEO imported successfully")
```

You can also list installed plugins from Python:

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()
print(registry.list_supported_collections())
print(list(registry.list_all_params()))
```

## Development install

If you are contributing to AerEO or running the example notebooks from the
repo:

```bash
git clone https://github.com/frandorr/aereo.git
cd aereo
uv sync --extra docs
```

Then build the docs locally:

```bash
uv run mkdocs serve
```

## Next step

Head to [Your First Pipeline](getting-started/first-pipeline.md) to extract
your first Sentinel-2 GeoTIFF, or read the
[Configuration](configuration/config-package.md) section to understand the YAML
files before you run anything.
