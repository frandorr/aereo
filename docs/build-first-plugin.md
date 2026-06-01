# Build Your First Plugin

The `aereo` framework is fully extensible using Python's standard `entry_points` mechanism. Third-party developers can create standalone Python packages that integrate seamlessly into the `aereo` ecosystem.

The **best and easiest approach** is to create a separate repository. This lets you develop, test, and release independently, without dealing with the core repository's Polylith architecture constraints.

---

## Step 1: Bootstrap Your Repository

We recommend using the [`aereo-plugin-template`](https://github.com/frandorr/aereo-plugin-template) as the foundation. It is pre-configured with the standard Python tooling (`uv`, `ruff`, `pyright`, `pytest`) used across the `aereo` ecosystem.

1. Go to [https://github.com/frandorr/aereo-plugin-template](https://github.com/frandorr/aereo-plugin-template).
2. Click **Use this template** → **Create a new repository**.
3. Name your repository (e.g., `aereo-plugin-acme`) and clone it locally.

---

## Step 2: Add Dependencies

Your plugin only needs to depend on the core `aereo` package to access its interfaces and schemas.

Update `pyproject.toml`:

```toml
[project]
name = "aereo-plugin-acme"
version = "0.1.0"
dependencies = [
    "aereo",
    "geopandas",  # For returning standard schemas
    "pandera",    # For schema validation (optional but recommended)
]
```

Install the dependencies:

```bash
uv sync
```

---

## Step 3: Write Your Plugin Logic

Plugins are **plain Python functions** that AEREO wires together into a [Hamilton](https://github.com/dagworks-inc/hamilton) DAG at runtime. There are no base classes to inherit from and no decorators to apply — just functions with descriptive names and type hints.

Every plugin module **must** declare `supported_collections` as a module-level variable so the discovery machinery knows which collections it can handle.

### Search Plugin

Create a search plugin (e.g., in `acme_plugin/nodes.py`). Search plugins export functions that return a `GeoDataFrame` of assets.

```python
"""ACME search plugin for aereo."""

from datetime import datetime
from typing import Any, Mapping, Sequence

import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

from aereo.schemas import AssetSchema

# REQUIRED: sequence of collections this plugin supports
supported_collections = ("acme-l1", "acme-l2")


def search_assets(
    aoi: BaseGeometry | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    collections: Sequence[str],
    search_params: Mapping[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]:
    """Search ACME API for satellite data."""
    # Your ACME API search logic here

    # Example: Mocking a search request
    # results = acme_api.search(...)

    # Format the response as a GeoDataFrame that aligns with AssetSchema
    df = pd.DataFrame([
        {
            "id": "acme_item_001",
            "collection": collections[0],
            "datetime": datetime.utcnow(),
            "geometry": aoi if aoi else None,
            "assets": {"data": {"href": "https://acme.org/data.tif"}}
        }
    ])

    # Ensure it matches AssetSchema
    gdf = GeoDataFrame(df, geometry="geometry")
    return AssetSchema.validate(gdf)


def search_results(search_assets: GeoDataFrame[AssetSchema]) -> GeoDataFrame[AssetSchema]:
    """Output boundary for the search stage.

    This function simply forwards the results from ``search_assets`` so
    that the Hamilton driver has a single well-known output node.
    """
    return search_assets
```

### Read Plugin

Create a read plugin (e.g., in `acme_plugin/nodes.py`). Read plugins turn downloaded assets into an `xarray.Dataset`.

```python
"""ACME read plugin for aereo."""

from pathlib import Path
from typing import Any, Mapping

import xarray as xr
from aereo.interfaces import ExtractionTask

supported_collections = ("acme-l1",)


def read_scenes(
    extracted_assets: Mapping[str, Path],
    task: ExtractionTask,
    collection: str | None = None,
) -> xr.Dataset:
    """Load ACME data into an xarray Dataset."""
    # Open files, stack bands, attach CRS metadata via rioxarray, etc.
    ds = xr.Dataset()
    # ... your loading logic ...
    return ds
```

### Processor Plugin

Create a processor plugin (e.g., in `acme_plugin/processors.py`). Processors are pure functions that take an `xr.Dataset` and return a modified `xr.Dataset`.

```python
"""ACME processor plugin for aereo."""

import numpy as np
import xarray as xr

supported_collections = ("*",)  # wildcard — applies to any collection


def apply_acme_calibration(ds: xr.Dataset, gain: float = 1.0) -> xr.Dataset:
    """Apply ACME-specific calibration scaling."""
    for var in ds.data_vars:
        ds[var] = ds[var] * gain
    return ds
```

---

## Step 4: Register the Entry Point

`aereo` discovers third-party plugins automatically using **Python Entry Points**. Each pipeline stage has its own entry-point group:

| Stage | Entry-point group | Typical function |
|-------|-------------------|------------------|
| Search | `aereo.search` | `search_assets` |
| Download | `aereo.download` | `download_assets` |
| Read | `aereo.read` | `read_scenes` |
| Reproject | `aereo.reproject` | `reproject_to_grid` |
| Write | `aereo.write` | `write_cogs` |
| Process | `aereo.process` | `compute_ndvi`, `mask_clouds`, etc. |

Add the plugin module paths to `pyproject.toml` under the relevant stage group:

```toml
[project.entry-points."aereo.search"]
acme = "acme_plugin.search"

[project.entry-points."aereo.read"]
acme = "acme_plugin.read"

[project.entry-points."aereo.process"]
acme = "acme_plugin.processors"
```

> [!IMPORTANT]
> The value must be a **module path** (e.g., `acme_plugin.search`), **not** a `module:ClassName` reference. Hamilton imports the module and inspects its functions.

---

## Step 5: Configure Your Profiles

`PipelineProfile` (also available as the backward-compat alias `AereoProfile`) is a **Pydantic `BaseModel`** that declaratively configures a complete pipeline. You get validation, frozen immutability, and native JSON/YAML deserialization.

### Construct profiles in code

```python
from aereo.interfaces import PipelineProfile

profile = PipelineProfile(
    name="acme_l1",
    resolution=250,
    collections={"acme-l1": ["B01"]},
    plugin_hints={"search": "acme", "read": "acme"},
    search_params={"api_key": "secret"},
)
```

`PipelineProfile` is frozen (`model_config = {"frozen": True}`) and forbids unknown fields (`"extra": "forbid"`), so typos raise a clear `ValidationError` immediately.

### Load profiles from YAML or JSON

```yaml
# profiles.yaml
profiles:
  - name: acme_l1
    resolution: 250
    collections:
      acme-l1: ["B01"]
    plugin_hints:
      search: acme
      read: acme
    search_params:
      api_key: secret
```

```python
from pathlib import Path
from aereo.interfaces import PipelineProfile

# From a YAML file
profiles = PipelineProfile.from_yaml(Path("profiles.yaml"))

# From a YAML string
profiles = PipelineProfile.from_yaml_string(yaml_text)

# From a JSON file
profiles = PipelineProfile.from_json(Path("profiles.json"))

# From a directory containing *.yaml / *.yml / *.json
profiles = PipelineProfile.from_config_dir(Path("configs/"))
```

---

## Step 6: Processor Configuration

One of the most powerful features of the Hamilton pipeline is **configurable processors**. You declare which processors run — and in what order — directly in the profile.

### Sequential processors

```python
profile = PipelineProfile(
    name="acme_l1",
    resolution=250,
    collections={"acme-l1": ["B01", "B02"]},
    pre_processors=["select_bands"],
    post_processors=["normalize"],
)
```

Each processor name maps to a function discovered via the `aereo.process` entry-point group. The pipeline wires them in order:

```
read_scenes → select_bands → reproject_to_grid → normalize → write_cogs
```

### Passing parameters to a processor

Use a dict when a processor needs arguments:

```python
profile = PipelineProfile(
    name="acme_l1",
    resolution=250,
    collections={"acme-l1": ["B01", "B02"]},
    pre_processors=[
        {"select_bands": {"bands": ["B01", "B02"]}},
        {"mask_clouds": {"qa_band": "qa", "qa_mask_bits": [3, 4]}},
    ],
)
```

### Parallel processors

Independent processors can run in parallel by wrapping them in a `parallel` dict:

```python
profile = PipelineProfile(
    name="s2_ndvi_ndwi",
    resolution=100,
    collections={"sentinel-2-l2a": ["B04", "B08", "B11"]},
    plugin_hints={"search": "planetary_computer", "read": "odc_stac"},
    post_processors=[
        {"parallel": ["compute_ndvi", "compute_ndwi"]},
        "normalize",
    ],
)
```

The pipeline builds a DAG where `compute_ndvi` and `compute_ndwi` both receive the same input (the output of `reproject_to_grid`), run concurrently, and their results are merged before passing to `normalize`:

```
                    ┌─→ compute_ndvi ─┐
reproject_to_grid ──┤                 ├──→ merge ─→ normalize ─→ write_cogs
                    └─→ compute_ndwi ─┘
```

> [!TIP]
> Parallel branches are merged by concatenating their output datasets. Make sure each branch produces **different variable names** (e.g., `ndvi` and `ndwi`) so they don't collide.

---

## Step 7: Test Your Plugin

Test your plugin using the high-level `AereoClient` API:

```python
from aereo.client import AereoClient
from aereo.interfaces import PipelineProfile
from datetime import datetime
from pathlib import Path

# The client automatically discovers your entry points!
client = AereoClient()

# Load profiles from config (or build them in code)
profiles = PipelineProfile.from_yaml(Path("profiles.yaml"))

# 1. Search
results = client.search(
    profiles=profiles,
    start_datetime=datetime(2023, 1, 1),
    end_datetime=datetime(2023, 1, 31),
)

# 2. Prepare
from aereo.interfaces import GridConfig

tasks = client.prepare_for_extraction(
    results,
    profiles=profiles,
    uri="output/acme",
    grid_config=GridConfig(target_grid_dist=256000),
)

# 3. Extract
from aereo.backends import LocalProcessBackend

backend = LocalProcessBackend()
artifacts = client.execute_tasks(tasks, backend=backend)
print(artifacts[["id", "uri"]])
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

## Plugin Hint Resolution

When multiple plugins can handle the same collection, AEREO resolves which one to use with the following priority:

1. **`plugin_hints`** — Explicit user choice in the profile always wins.
2. **Collection match** — Auto-discovery finds a plugin whose `supported_collections` includes the target collection.
3. **Wildcard fallback** — If no specific match is found, a plugin declaring `supported_collections = ("*",)` is used.

```python
# Explicit hint — always uses "acme" for search
profile = PipelineProfile(
    name="acme_l1",
    resolution=250,
    collections={"acme-l1": ["B01"]},
    plugin_hints={"search": "acme"},
)
```

If no plugin can be resolved, `AereoDriver` raises a clear `ValueError`.

---

## Interface Reference

| Stage | Entry-point group | Key functions | Output type |
|-------|-------------------|---------------|-------------|
| Search | `aereo.search` | `search_assets` | `GeoDataFrame[AssetSchema]` |
| Download | `aereo.download` | `download_assets` | `Mapping[str, Path]` |
| Read | `aereo.read` | `read_scenes` | `xr.Dataset` |
| Reproject | `aereo.reproject` | `reproject_to_grid` | `xr.Dataset` |
| Write | `aereo.write` | `write_cogs` | `GeoDataFrame[ArtifactSchema]` |
| Process | `aereo.process` | `compute_ndvi`, `mask_clouds`, etc. | `xr.Dataset` |

See the `aereo.interfaces` module for detailed documentation on `PipelineProfile`, `ExtractionTask`, and `GridConfig`.

---

## Next Steps

- Read [How Plugins Work](plugin-overview.md) for a deeper dive into the Hamilton DAG, plugin discovery, and the process compiler.
- Explore [Advanced Plugin Patterns](plugin-advanced.md) for local development tips, custom schemas, and multi-backend strategies.
