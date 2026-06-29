# AEREO Plugin System

`aereo` uses a modular plugin architecture built around plain Python functions
and standard `entry_points`. You do not need to subclass a base class or learn a
plugin framework: implement a function with the right signature, decorate it with
Pydantic's `@validate_call`, and register it under the `aereo.plugins` entry-point
group.

---

## How it works

The plugin system relies on strongly-typed interfaces defined in
`aereo.interfaces`. Plugins are functions that match these `Protocol` signatures,
and `AereoRegistry` discovers them at runtime from `entry_points`.

### The pipeline (`ExtractionJob`)

The data orchestration lifecycle has three core stages:

1. **Search**: a search function queries a satellite data collection and returns
   a standardized `AssetSchema` GeoDataFrame.
2. **Prepare**: `ExtractionJob.build_tasks()` turns search results into
   `ExtractionTask` objects, using the `grid_dist`, `PatchConfig`, and
   `TaskBuilder`.
3. **Execute**: an executor runs each task: `read function → write function`
   once per patch.

### Built-in stages

The `aereo.builtins` package ships with ready-to-use functions:

| Stage | Built-in functions | Input | Output |
|-------|--------------------|-------|--------|
| Search | `search_stac`, `search_earthaccess` | `(collections, intersects, start_datetime, end_datetime, **kwargs)` | `GeoDataFrame[AssetSchema]` |
| Reader | `read_odc_stac` | `ExtractionTask` | `xr.Dataset` |
| Processor | `select_bands`, `qa_mask`, `ndvi`, `normalize`, `composite` | `xr.Dataset` | `xr.Dataset` |
| Reprojector | `reproject_odc` | `(xr.Dataset, ExtractionTask, **kwargs)` | `dict[str, xr.Dataset]` (keyed by patch id) |
| Writer | `write_geotiff` | `(xr.Dataset, ExtractionTask, ExtractionPatch)` | `GeoDataFrame[ArtifactSchema]` |
| Task builder | `build_grouped_tasks` | `(GeoDataFrame[AssetSchema], ExtractionJob, PatchConfig)` | `Sequence[ExtractionTask]` |

External plugins (installed separately) provide additional readers,
reprojectors, and search providers, such as `read_satpy`, `reproject_satpy`,
`search_aws_goes`, and `search_tessera`.

---

## The API surface

`aereo.interfaces` provides the core contracts that plugins implement. Each
contract is a `Protocol`, so plugins can be regular functions.

### `SearchProvider`

Responsible for querying remote APIs and building the initial asset footprint.

```python
from datetime import datetime
from typing import Any, Mapping, Sequence

from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call
from shapely.geometry.base import BaseGeometry

from aereo.interfaces import SearchProvider
from aereo.schemas import AssetSchema


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def my_search_provider(
    collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
    intersects: BaseGeometry | None,
    start_datetime: datetime | None,
    end_datetime: datetime | None,
    api_key: str,
) -> GeoDataFrame[AssetSchema]:
    """Search a catalog and return validated assets."""
    ...
```

### `Reader`

Opens source assets and returns an `xr.Dataset` for downstream stages.

```python
import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import Reader, ExtractionTask


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def my_reader(task: ExtractionTask) -> xr.Dataset:
    """Open hrefs from task.assets and return a Dataset."""
    ...
```

### `Processor`

Transforms a dataset. Processors run before and/or after the reprojector.

```python
import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import Processor


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def my_processor(ds: xr.Dataset) -> xr.Dataset:
    """Transform data."""
    ...
```

### `Reprojector`

Reprojects data to the task's target patches.

```python
import xarray as xr
from pydantic import ConfigDict, validate_call

from aereo.interfaces import Reprojector, ExtractionTask


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def my_reprojector(
    ds: xr.Dataset,
    task: ExtractionTask,
    resampling: str = "nearest",
) -> dict[str, xr.Dataset]:
    """Reproject ds for every patch in task."""
    ...
```

### `Writer`

Writes final artifacts to disk or object store.

```python
from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call
import xarray as xr

from aereo.interfaces import Writer, ExtractionTask, ExtractionPatch
from aereo.schemas import ArtifactSchema


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def my_writer(
    ds: xr.Dataset,
    task: ExtractionTask,
    patch: ExtractionPatch,
) -> GeoDataFrame[ArtifactSchema]:
    """Write data and return artifact rows."""
    ...
```

### `TaskBuilder`

Builds extraction tasks from search results.

```python
from typing import Sequence

from pandera.typing.geopandas import GeoDataFrame
from pydantic import ConfigDict, validate_call

from aereo.interfaces import TaskBuilder, ExtractionJob, ExtractionTask
from aereo.schemas import AssetSchema


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def my_task_builder(
    search_results: GeoDataFrame[AssetSchema],
    job: ExtractionJob,
) -> Sequence[ExtractionTask]:
    """Group assets into extraction tasks."""
    ...
```

---

## Parameter introspection

Because plugins are `@validate_call` functions, their signatures are
introspectable at runtime. `AereoRegistry` derives parameter metadata from the
function signature and Pydantic field information:

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()

# Get params for a specific plugin
params = registry.get_plugin_params("search_stac")

# Get a JSON-serializable catalog of all plugins and their params
catalog = registry.list_all_params()
```

---

## Using the high-level API

`ExtractionJob` provides the orchestration methods that drive the pipeline.

```python
from aereo.pipeline import ExtractionJob
from aereo.executors import LocalExecutor

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

results = job.search(...)
tasks = job.build_tasks(results, ...)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
print(artifacts[["id", "grid_cell", "uri"]].head())
```

---

## Entry points & discovery

Plugins are discovered automatically via Python `entry_points`. Declare them in
`pyproject.toml` under the unified `aereo.plugins` group:

```toml
[project.entry-points."aereo.plugins"]
my_searcher = "my_package.module:my_search_provider"
my_reader = "my_package.module:my_reader"
my_writer = "my_package.module:my_writer"
```

> [!IMPORTANT]
> **Workspace discovery root**: In a Polylith development environment,
> `importlib.metadata` reads discovery metadata from the package currently
> installed in the environment. If you add a new plugin to a `projects/`
> sub-package but **do not** add it to the root `pyproject.toml`, it will be
> missing during development. Always mirror your plugin entry points in the root
> configuration during active development.

To learn how to build and expose your own custom plugins, see
[Build Your First Plugin](build-first-plugin.md).
