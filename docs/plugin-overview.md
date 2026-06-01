# aereo Plugin System

`aereo` uses a modular, function-based plugin architecture built around [Apache Hamilton](https://github.com/dagworks-inc/hamilton) and standard Python `entry_points`. This allows developers to seamlessly register new pipeline stages for satellite data collections without needing complex third-party hook libraries like `pluggy`.

## How it Works

The plugin system relies on **plain Python functions** grouped by pipeline stage. Each stage has its own `entry_points` group (e.g., `aereo.search`, `aereo.read`). AEREO discovers these modules at runtime and wires their functions into a Hamilton DAG that orchestrates execution.

### The Pipeline (`AereoClient`)

The data orchestration lifecycle consists of three core stages, managed cohesively by the `AereoClient`:

1.  **Search**: `aereo.search` plugins query satellite data collections and return standardized `AssetSchema` GeoDataFrames. The `AereoClient` concurrently dispatches searches across multiple plugins.
2.  **Prepare**: Core grid-generation logic transforms search results into discrete `ExtractionTask` objects (grouping by time, location, and profile).
3.  **Extract**: A Hamilton DAG built from `aereo.download`, `aereo.read`, `aereo.reproject`, `aereo.write`, and `aereo.process` plugins downloads, processes, and formats data into unified `ArtifactSchema` GeoDataFrames.

## The API Surface

Plugins export plain functions with descriptive names and type hints. Hamilton uses the function names and signatures to build the execution graph.

### Search Plugin

Responsible for querying remote APIs and building the initial asset footprint.
Plugins must declare `supported_collections` as a sequence of strings.

```python
from typing import Any, Mapping, Sequence
from datetime import datetime
from shapely.geometry.base import BaseGeometry
from pandera.typing.geopandas import GeoDataFrame

from aereo.schemas import AssetSchema

supported_collections = ("my-satellite-data",)


def search_assets(
    aoi: BaseGeometry | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    collections: Sequence[str],
    search_params: Mapping[str, Any] | None = None,
) -> GeoDataFrame[AssetSchema]:
    ...


def search_results(search_assets: GeoDataFrame[AssetSchema]) -> GeoDataFrame[AssetSchema]:
    return search_assets
```

### Read Plugin

Responsible for loading downloaded assets into an in-memory `xarray.Dataset`.
Plugins must declare `supported_collections` as a sequence of strings.

```python
from pathlib import Path
from typing import Any, Mapping

import xarray as xr
from aereo.interfaces import ExtractionTask

supported_collections = ("my-satellite-data",)


def read_scenes(
    extracted_assets: Mapping[str, Path],
    task: ExtractionTask,
    collection: str | None = None,
) -> xr.Dataset:
    ...
```

### Processor Plugin

Responsible for transforming `xr.Dataset` objects between read and write.
Processors are pure functions: they receive a dataset, modify it, and return it.

```python
import xarray as xr

supported_collections = ("*",)


def compute_custom_index(ds: xr.Dataset, band_a: str = "B04", band_b: str = "B08") -> xr.Dataset:
    """Compute a custom spectral index."""
    index = (ds[band_a] - ds[band_b]) / (ds[band_a] + ds[band_b])
    ds["custom_index"] = index
    return ds
```

## Processor Configuration

Users declare which processors to run — and in what order — via `PipelineProfile`.

### Sequential

```python
from aereo.interfaces import PipelineProfile

profile = PipelineProfile(
    name="s2_calibrated",
    resolution=100,
    collections={"sentinel-2-l2a": ["B04", "B08"]},
    pre_processors=["select_bands"],
    post_processors=["normalize"],
)
```

### With parameters

```python
profile = PipelineProfile(
    name="s2_masked",
    resolution=100,
    collections={"sentinel-2-l2a": ["B04", "B08", "SCL"]},
    pre_processors=[
        {"select_bands": {"bands": ["B04", "B08", "SCL"]}},
        {"mask_clouds": {"qa_band": "SCL", "qa_mask_bits": [3, 8, 9]}},
    ],
)
```

### Parallel branches

```python
profile = PipelineProfile(
    name="s2_ndvi_ndwi",
    resolution=100,
    collections={"sentinel-2-l2a": ["B04", "B08", "B11"]},
    post_processors=[
        {"parallel": ["compute_ndvi", "compute_ndwi"]},
        "normalize",
    ],
)
```

The processor compiler translates this config into Hamilton functions:

```
                    ┌─→ compute_ndvi ─┐
reproject_to_grid ──┤                 ├──→ merge_0 ─→ normalize ─→ write_cogs
                    └─→ compute_ndwi ─┘
```

Independent branches run concurrently. The merge node concatenates their outputs before the next sequential step.

## Using the High-Level API (Recommended)

The `AereoClient` provides a simple, robust interface that handles plugin discovery, collection routing, parallel search, and configurable error handling.

### Usage

```python
from datetime import datetime, timezone
from aereo.client import AereoClient
from aereo.interfaces import PipelineProfile

client = AereoClient()

profiles = [
    PipelineProfile(
        name="goes_c07",
        resolution=2000,
        collections={"ABI-L1b-RadF": ["C07"]},
        plugin_hints={"search": "aws_goes", "read": "satpy"},
        search_params={"satellite": "GOES-19"},
        read_params={"reader": "abi_l1b", "calibration": "reflectance"},
    )
]

# 1. Search
search_results = client.search(
    profiles=profiles,
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
)
print(f"Found {len(search_results)} assets.")

# 2. Prepare tasks
from aereo.interfaces import GridConfig

tasks = client.prepare_for_extraction(
    search_results,
    profiles=profiles,
    uri="output/goes",
    grid_config=GridConfig(target_grid_dist=256_000),
)

from aereo.backends import LocalProcessBackend

# 3. Extract
backend = LocalProcessBackend(max_workers=4)
artifacts_df = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(artifacts_df)} artifacts.")
```

## Advanced: Manual Plugin Management

If you need fine-grained control, use the discovery utilities directly. They parse `entry_points` and provide resolved plugin modules.

```python
from aereo.discovery import discover_plugins, resolve_plugin
from aereo.interfaces import PipelineProfile

# Discover all search plugins
search_plugins = discover_plugins("aereo.search")
print(search_plugins.list_supported_collections())

# Resolve which plugin to use for a profile
profile = PipelineProfile(
    name="goes_c07",
    resolution=2000,
    collections={"ABI-L1b-RadF": ["C07"]},
    plugin_hints={"search": "aws_goes"},
)
mod = resolve_plugin(
    stage="search",
    collection="ABI-L1b-RadF",
    plugin_hints=profile.plugin_hints,
    stage_plugins=search_plugins,
)
print(mod.__name__)  # aereo.search_aws_goes.nodes
```

## Entry Points & Discovery

Plugins are discovered automatically via Python `entry_points`. Declare them in `pyproject.toml` under the **stage-specific** group:

```toml
[project.entry-points."aereo.search"]
my_searcher = "my_package.search"

[project.entry-points."aereo.read"]
my_reader = "my_package.read"

[project.entry-points."aereo.process"]
my_processors = "my_package.processors"
```

> [!IMPORTANT]
> **Workspace Discovery Root**: In a Polylith development environment, `importlib.metadata` reads discovery metadata from the package currently installed in the environment. If you add a new plugin to a `projects/` sub-package but **do not** add it to the root `pyproject.toml`, it will be missing during development. Always mirror your plugin entry points in the root configuration during active development.

> [!NOTE]
> The legacy unified `aereo.plugins` entry-point group is still supported for backward compatibility, but new plugins should use the stage-specific groups.

To learn how to build and expose your own custom plugins natively, see [Build Your First Plugin](build-first-plugin.md).
