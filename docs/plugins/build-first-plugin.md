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

Plugins are plain Python functions decorated with `@validate_call`. The
interesting work happens in the function body, and the signature tells AEREO
which parameters users can pass.

### Search plugin

Create a search provider (e.g., in `acme_plugin/search.py`).

```python
"""ACME search plugin for aereo."""

from datetime import datetime
from typing import Any, Mapping, Sequence

import geopandas as gpd
import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from aereo.interfaces import SearchProvider
from aereo.schemas import AssetSchema


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def acme_search_provider(
    collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
    intersects: BaseGeometry | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    api_key: str,
) -> GeoDataFrame[AssetSchema]:
    """Search plugin for ACME satellite data."""
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

Create a reader that opens source assets and returns an `xr.Dataset`:

```python
"""ACME reader plugin for aereo."""

from typing import Any

import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import Reader


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def acme_reader(
    files: list[str],
    bands: list[str] | None = None,
    **kwargs: Any,
) -> xr.Dataset:
    """Reader plugin for ACME data."""
    # Open filenames, select bands, return a Dataset.
    ...
```

### Writer plugin

Create a writer that persists the final data to a path supplied by the
orchestrator:

```python
"""ACME writer plugin for aereo."""

from pathlib import Path
from typing import Any

import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import Writer


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def acme_writer(
    ds: xr.Dataset,
    path: str | Path,
    **kwargs: Any,
) -> str:
    """Writer plugin for ACME data."""
    # Write GeoTIFF to path and return the written path.
    ...
```

---

## Step 4: Register the entry point

`aereo` discovers third-party plugins automatically using Python entry points.

Add the plugin function paths to `pyproject.toml` under the unified `aereo.plugins`
group:

```toml
[project.entry-points."aereo.plugins"]
# alias = "module.path:function_name"
acme_search = "acme_plugin.search:acme_search_provider"
acme_read = "acme_plugin.read:acme_reader"
acme_write = "acme_plugin.write:acme_writer"
```

---

## Step 5: Document your parameters

Users can introspect parameters at runtime via the `AereoRegistry`:

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
  _target_: acme_plugin.search:acme_search_provider
  api_key: ${oc.env:ACME_API_KEY}

read:
  _target_: acme_plugin.read:acme_reader
  bands: ["B01", "B02"]

write:
  _target_: acme_plugin.write:acme_writer
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
from acme_plugin.search import acme_search_provider
from aereo.schemas import AssetSchema

results = acme_search_provider(
    collections=["acme-l1"],
    intersects=None,
    start_datetime=None,
    end_datetime=None,
    api_key="test",
)
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

| Interface | Purpose | Callable signature |
|-----------|---------|--------------------|
| `SearchProvider` | Query satellite data | `(collections, intersects, start_datetime, end_datetime, **kwargs) -> GeoDataFrame[AssetSchema]` |
| `Reader` | Open source assets | `(files: list[str], **kwargs) -> xr.Dataset` |
| `Processor` | Transform datasets | `(ds: xr.Dataset, **kwargs) -> xr.Dataset` |
| `Reprojector` | Reproject/resample | `(ds: xr.Dataset, **kwargs) -> xr.Dataset` |
| `Writer` | Write artifacts | `(ds: xr.Dataset, path: str \| Path, **kwargs) -> str` |
| `TaskBuilder` | Build extraction tasks | `(search_results, job: ExtractionJob, **kwargs) -> Sequence[ExtractionTask]` |

See the `aereo.interfaces` module for detailed documentation.

---

## Next steps

- Read [How Plugins Work](plugin-overview.md) for a deeper dive into the plugin
  system and discovery mechanics.
- Explore [Advanced Plugin Patterns](plugin-advanced.md) for local development
  tips, custom schemas, and multi-backend strategies.
