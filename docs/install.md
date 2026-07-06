# Install

AEREO is a Python 3.12+ framework. The core package is small; sensor-specific
search and I/O plugins are installed separately.

## Requirements

- Python **3.12** or newer
- `pip` or `uv`
- Credentials for any catalog that requires them (see below)

## Quick install

=== "Sentinel-2 (Planetary Computer)"

    ```bash
    pip install aereo aereo-search-planetary-computer
    ```

    You will need a [Planetary Computer subscription key](https://planetarycomputer.microsoft.com/docs/concepts/sas/)
    for signed assets. Set it as an environment variable or in your notebook.

=== "MODIS / VIIRS / Sentinel-3 (NASA Earthdata)"

    ```bash
    pip install aereo aereo-search-earthaccess
    ```

    Register for a free [NASA Earthdata Login](https://urs.earthdata.nasa.gov/)
    and store your credentials with `earthaccess.login()` or environment
    variables.

=== "GOES ABI (public S3)"

    ```bash
    pip install aereo aereo-search-aws-goes aereo-read-satpy aereo-reproject-satpy
    ```

    GOES data on AWS is public, so no authentication is required.

=== "GeoTessera"

    ```bash
    pip install aereo aereo-search-tessera aereo-read-tessera
    ```

    Check your Tessera catalog documentation for authentication.

## Verify the installation

```python
from aereo.pipeline import ExtractionJob
from aereo.builtins import search_stac, build_grouped_tasks
from aereo.executors import LocalExecutor

print("AEREO imported successfully")
```

You can also list installed plugins:

```bash
aereo action=plugins
```

## Development install

If you are contributing to AEREO or running the example notebooks from the
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
your first Sentinel-2 GeoTIFF.
