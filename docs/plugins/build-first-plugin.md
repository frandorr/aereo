# Build Your First Plugin

The `aereo` framework is fully extensible using Python's standard `entry_points`
mechanism. Third-party developers can create standalone Python packages that
integrate seamlessly into the `aereo` ecosystem.

The **best and easiest approach** is to create a separate repository. This lets
you develop, test, and release independently, without dealing with the core
repository's Polylith architecture constraints.

---

## Step 1: Bootstrap your repository

We recommend using the [`aereo-plugin-template`](https://github.com/frandorr/aereo-plugin-template)
as the foundation. It is pre-configured with the standard Python tooling (`uv`,
`ruff`, `pyright`, `pytest`) used across the `aereo` ecosystem.

1. Go to [https://github.com/frandorr/aereo-plugin-template](https://github.com/frandorr/aereo-plugin-template).
2. Click **Use this template** → **Create a new repository**.
3. Name your repository (e.g., `aereo-plugin-acme`) and clone it locally.

---

## Step 2: Add dependencies

Your plugin only needs to depend on the core `aereo` package to access its
interfaces and schemas.

Update `pyproject.toml`:

```toml
[project]
name = "aereo-plugin-acme"
version = "0.1.0"
dependencies = [
    "aereo",
    "geopandas",
    "pandera",
    "xarray",
]
```

Install the dependencies:

```bash
uv sync
```

---

## Step 3: Write your plugin logic

Plugins are standard Python classes that inherit from base interfaces defined in
`aereo.interfaces`. Like PyTorch modules, the interesting work happens in
`__call__`.

### Search plugin

Create a search provider (e.g., in `acme_plugin/search.py`).

```python
"""ACME search plugin for aereo."""

from datetime import datetime
from typing import Any

import geopandas as gpd
import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import box

from aereo.interfaces import SearchProvider
from aereo.schemas import AssetSchema


class AcmeSearchProvider(SearchProvider):
    """Search plugin for ACME satellite data."""

    def __init__(self, api_key: str, intersects: Any = None, **kwargs: Any):
        self.api_key = api_key
        self.intersects = intersects

    def __call__(self) -> GeoDataFrame[AssetSchema]:
        """Search ACME API for satellite data."""
        # Your ACME API search logic here

        df = pd.DataFrame([
            {
                "id": "acme_item_001",
                "collection": "acme-l1",
                "start_time": datetime.utcnow(),
                "end_time": datetime.utcnow(),
                "geometry": box(-1, -1, 1, 1),
                "href": "https://acme.org/data.tif",
            }
        ])

        gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
        return AssetSchema.validate(gdf)
```

### Reader plugin

Create a reader that opens source assets and returns an `xr.DataArray`:

```python
"""ACME reader plugin for aereo."""

import xarray as xr
from aereo.interfaces import Reader, ExtractionTask


class AcmeReader(Reader):
    """Reader plugin for ACME data."""

    def __init__(self, bands: list[str] | None = None):
        self.bands = bands or ["B01"]

    def __call__(self, task: ExtractionTask) -> xr.DataArray:
        """Open ACME assets for this task."""
        # Open hrefs from task.assets, select bands, return a DataArray.
        ...
```

### Writer plugin

Create a writer that persists the final data and returns artifact rows:

```python
"""ACME writer plugin for aereo."""

from pathlib import Path

import geopandas as gpd
import xarray as xr
from pandera.typing.geopandas import GeoDataFrame

from aereo.interfaces import Writer, ExtractionTask
from aereo.schemas import ArtifactSchema


class AcmeWriter(Writer):
    """Writer plugin for ACME data."""

    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)

    def __call__(self, data: xr.DataArray, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Write data and return artifact records."""
        # Write GeoTIFFs, build artifact GeoDataFrame, validate.
        ...
        return ArtifactSchema.empty()
```

---

## Step 4: Register the entry point

`aereo` discovers third-party plugins automatically using Python entry points.

Add the plugin class paths to `pyproject.toml` under the unified `aereo.plugins`
group:

```toml
[project.entry-points."aereo.plugins"]
# alias = "module.path:ClassName"
acme_search = "acme_plugin.search:AcmeSearchProvider"
acme_read = "acme_plugin.read:AcmeReader"
acme_write = "acme_plugin.write:AcmeWriter"
```

---

## Step 5: Document your parameters

If you declared `required_params` and `optional_params`, users can introspect
them at runtime via the `AereoRegistry`:

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()

# Get params for a single plugin
params = registry.get_plugin_params("acme_search")
print(params["required"])
print(params["optional"])

# Export a JSON catalog of every plugin's params
import json
print(json.dumps(registry.list_all_params(), indent=2))
```

This powers CLI help text, config validation, and plugin marketplace listings.

---

## Step 6: Wire the plugin into a pipeline

Use your plugin in a Hydra config:

```yaml
search:
  _target_: acme_plugin.search:AcmeSearchProvider
  api_key: ${oc.env:ACME_API_KEY}

extract:
  read:
    _target_: acme_plugin.read:AcmeReader
    bands: ["B01", "B02"]
  write:
    _target_: acme_plugin.write:AcmeWriter
    output_dir: /tmp/acme_out
```

Or instantiate it in Python:

```python
from aereo.pipeline import ExtractionJob
from aereo.executors import LocalExecutor

job = ExtractionJob.load_from_config("configs/acme", config_name="job")

results = job.search(...)
tasks = job.build_tasks(results, ...)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
```

---

## Step 7: Test your plugin

Test your plugin with a small Hydra config or directly in Python:

```python
from acme_plugin.search import AcmeSearchProvider
from aereo.schemas import AssetSchema

provider = AcmeSearchProvider(api_key="test")
results = provider()
assert isinstance(results, AssetSchema.validate(results).__class__)
```

---

## Step 8: Distribute

Your plugin is just a standard Python package. Publish it to PyPI:

```bash
uv build
uv publish
```

Users install it like any other package:

```bash
pip install aereo-plugin-acme
```

---

## Interface reference

| Interface | Purpose | Key method |
|-----------|---------|------------|
| `SearchProvider` | Query satellite data | `__call__` |
| `Reader` | Open source assets | `__call__` |
| `Processor` | Transform data arrays | `__call__` |
| `Reprojector` | Reproject to target grid | `__call__` |
| `Writer` | Write artifacts | `__call__` |

See the `aereo.interfaces` module for detailed documentation.

---

## Next steps

- Read [How Plugins Work](plugin-overview.md) for a deeper dive into the plugin
  system and discovery mechanics.
- Explore [Advanced Plugin Patterns](plugin-advanced.md) for local development
  tips, custom schemas, and multi-backend strategies.
