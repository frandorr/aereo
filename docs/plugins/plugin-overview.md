# AEREO Plugin System

`aereo` uses a modular, object-oriented plugin architecture built around
standard Python `entry_points`. This lets developers register new search
providers, readers, processors, reprojectors, and writers without third-party
hook libraries like `pluggy`.

Plugins feel like PyTorch modules: you subclass a base interface, implement
`__call__`, and register the class under the `aereo.plugins` entry-point group.

---

## How it works

The plugin system relies on strongly-typed interfaces defined in
`aereo.interfaces`. Plugins subclass these base classes, and `AereoRegistry`
discovers them at runtime from `entry_points`.

### The pipeline (`ExtractionJob`)

The data orchestration lifecycle has three core stages:

1. **Search**: `SearchProvider` plugins query satellite data collections and
   return standardized `AssetSchema` GeoDataFrames.
2. **Prepare**: `ExtractionJob.build_tasks()` turns search results into
   `ExtractionTask` objects, using the `GridConfig`, `PatchConfig`, and
   `ExtractConfig` from the job.
3. **Execute**: An `Executor` runs each task through the stage pipeline
   configured in `ExtractConfig`:
   `Reader → Processor → Reprojector → Processor → Writer`.

### Built-in stages

The `aereo.builtins` package ships with ready-to-use plugins:

| Stage | Built-in plugins |
|-------|------------------|
| Search | `SearchSTAC`, `SearchEarthaccess` |
| Reader | `ReadODCSTAC` |
| Processor | `SelectBands`, `QAMask`, `NDVI`, `Normalize`, `Composite` |
| Reprojector | `ReprojectODC` |
| Writer | `WriteGeoTIFF` |

External plugins (installed separately) provide additional readers,
reprojectors, and search providers, such as `ReadSatpy`, `ReprojectSatpy`,
`SearchAwsGoes`, and `SearchTessera`.

---

## The API surface

`aereo.interfaces` provides the core contracts that plugins implement.

### `SearchProvider`

Responsible for querying remote APIs and building the initial asset footprint.

```python
from pandera.typing.geopandas import GeoDataFrame
from aereo.interfaces import SearchProvider
from aereo.schemas import AssetSchema

class MySearchProvider(SearchProvider):
    def __call__(self) -> GeoDataFrame[AssetSchema]:
        # Query the catalog, build a GeoDataFrame, validate it.
        ...
```

### `Reader`

Opens a source asset and returns an `xr.DataArray` (or similar) for downstream
stages.

```python
from aereo.interfaces import Reader, ExtractionTask
import xarray as xr

class MyReader(Reader):
    def __call__(self, task: ExtractionTask) -> xr.DataArray:
        # Open hrefs from task.assets, return a DataArray.
        ...
```

### `Processor`

Transforms a data array. Processors run before and/or after the reprojector.

```python
from aereo.interfaces import Processor
import xarray as xr

class MyProcessor(Processor):
    def __call__(self, data: xr.DataArray, task: ExtractionTask) -> xr.DataArray:
        # Transform data.
        ...
```

### `Reprojector`

Reprojects data to the task's target grid.

```python
from aereo.interfaces import Reprojector, ExtractionTask
import xarray as xr
from odc.geo.geobox import GeoBox

class MyReprojector(Reprojector):
    def __call__(self, data: xr.DataArray, geobox: GeoBox, task: ExtractionTask) -> xr.DataArray:
        # Reproject data to geobox.
        ...
```

### `Writer`

Writes final artifacts to disk or object store.

```python
from aereo.interfaces import Writer, ExtractionTask
from pandera.typing.geopandas import GeoDataFrame
from aereo.schemas import ArtifactSchema

class MyWriter(Writer):
    def __call__(self, data, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        # Write files and return artifact rows.
        ...
```

---

## Plugin parameter metadata

Plugins can declare typed parameter schemas using `PluginParam`. This enables
runtime introspection, CLI help generation, and validation before execution.

### `PluginParam`

A frozen Pydantic model that describes a single configuration parameter:

```python
from aereo.interfaces import PluginParam

param = PluginParam(
    name="reader",
    type="choice",
    description="Rasterio reader driver to use",
    choices=["abi_l1b", "netcdf", "geotiff"],
    required=True,
)
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Parameter key |
| `type` | `Literal["str", "int", "float", "bool", "choice", "path", "list[str]"]` | Expected value type |
| `description` | `str` | Human-readable help text |
| `default` | `Any \| None` | Default value when omitted |
| `choices` | `Sequence[str] \| None` | Allowed values for `"choice"` type |
| `required` | `bool` | Whether the parameter must be provided |

### Declaring params on a plugin

Set `required_params` and `optional_params` as class attributes on your plugin
subclass:

```python
from aereo.interfaces import SearchProvider, PluginParam

class MySearchProvider(SearchProvider):
    required_params = [
        PluginParam(name="api_key", type="str", description="API authentication key", required=True),
    ]

    optional_params = [
        PluginParam(name="max_cloud_cover", type="float", description="Max cloud cover %", default=20.0),
    ]
```

### Introspecting params at runtime

The `AereoRegistry` provides methods to query parameter metadata:

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()

# Get params for a specific plugin
params = registry.get_plugin_params("search_stac")

# Get a JSON-serializable catalog of all plugins and their params
catalog = registry.list_all_params()
```

> [!NOTE]
> Parameter metadata is optional. Existing plugins that do not declare
> `required_params` / `optional_params` continue to work unchanged.

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
my_searcher = "my_package.module:MySearchProvider"
my_reader = "my_package.module:MyReader"
my_writer = "my_package.module:MyWriter"
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
