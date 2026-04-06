# aer Plugin System

`aer` uses **pluggy**, the battle-tested plugin system from pytest, to enable third-party extensions. This allows developers to register new search backends, extract backends, and data transformations using simple `@hookimpl` decorators.

## How it Works

The plugin system provides **hookspecs** (specifications) that define the interface, and **hookimpls** (implementations) provided by external packages:

```python
# In aer - the hookspec
class AerSpec:
    @hookspec
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search for satellite data."""

# In your plugin - the hookimpl
class MySearchPlugin:
    @hookimpl
    def search(self, query: SearchQuery) -> GeoDataFrame:
        # Your implementation
        return results
```

## Writing a Plugin

### Search Plugins

Create a class that implements the `search` hook:

```python
from pandera.typing.geopandas import GeoDataFrame
from aer.plugin import hookimpl
from aer.search import SearchQuery

class EarthAccessSearchPlugin:
    """Search plugin using NASA Earthdata."""

    @hookimpl
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search NASA Earthdata for satellite imagery.

        Parameters
        ----------
        query : SearchQuery
            Search parameters including collections, time range,
            and spatial extent.

        Returns
        -------
        GeoDataFrame
            Search results with columns: collection, id, datetime,
            geometry, plus any provider-specific metadata.
        """
        # Example implementation
        import earthaccess

        results = earthaccess.search_data(
            short_name=query.collections[0],
            temporal=(query.datetime),
            bounding_box=query.intersects.bounds,
        )

        # Convert to GeoDataFrame with SearchResultSchema
        return GeoDataFrame(results)
```

### Extract Plugins

Create a class that implements the `extract` hook:

```python
from aer.plugin import hookimpl
from aer.extract import ExtractionTask

class EarthAccessExtractPlugin:
    """Extract plugin for NASA Earthdata."""

    @hookimpl
    def extract(self, task: ExtractionTask) -> ExtractionTask:
        """Download and process satellite data.

        Parameters
        ----------
        task : ExtractionTask
            Task containing source URL, output path, and processing
            parameters. The target grid cell is in
            'overlapping_spatial_extent'.

        Returns
        -------
        ExtractionTask
            Task with updated status (SUCCESS or FAILED) and
            output_files populated.
        """
        try:
            # Download the data
            download_file(task.source_url, task.output_path)

            # Reproject to target grid if needed
            if task.target_grid:
                reproject(task.output_path, task.target_grid)

            task.status = "SUCCESS"
            task.output_files = [task.output_path]
        except Exception as e:
            task.status = "FAILED"
            task.error = str(e)

        return task
```

### Prepare Tasks Plugins

Create a class that implements the `prepare_tasks` hook:

```python
from aer.plugin import hookimpl
from aer.extract import ExtractionTask
from aer.search import SearchQuery

class MyPreparePlugin:
    """Prepare extraction tasks from search results."""

    @hookimpl
    def prepare_tasks(self, query: SearchQuery) -> list[ExtractionTask]:
        """Convert search results to extraction tasks.

        Parameters
        ----------
        query : SearchQuery
            The search query, typically with results attached.

        Returns
        -------
        list[ExtractionTask]
            List of extraction tasks ready for processing.
        """
        return [
            ExtractionTask(
                source_url=item.s3_url,
                output_path=f"/data/{item.id}.nc",
                parameters={"channels": query.channels},
            )
            for item in query.results
        ]
```

## Using Plugins

### Loading Plugins

Plugins are automatically discovered via Python entry points:

```python
import pluggy
from aer.plugin import AerSpec, PROJECT_NAME

# Create plugin manager
pm = pluggy.PluginManager(PROJECT_NAME)
pm.add_hookspecs(AerSpec)

# Load all plugins from entry points
pm.load_setuptools_entrypoints("aer.plugins")

# Now all @hookimpl plugins are registered
```

### Calling Hooks

Once plugins are loaded, call hooks by name:

```python
from aer.search import SearchQuery

# Create a query
query = SearchQuery(
    collections=["HLSL30"],
    datetime="2024-01-01/2024-02-01",
    intersects=my_geometry,
)

# Call the search hook - all registered plugins will be invoked
results = pm.hook.search(query=query)

# results is a list of return values from all plugins
# (combine them or pick the first based on your needs)
combined_results = pd.concat(results)
```

## Registering Your Plugin

Add an entry point to your `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
my_plugin = "my_package.module:MyPluginClass"
```

Multiple hooks can be implemented by the same class:

```toml
[project.entry-points."aer.plugins"]
earthaccess = "aer_earthaccess.plugin:EarthAccessPlugin"
```

Where `EarthAccessPlugin` implements multiple hooks:

```python
class EarthAccessPlugin:
    @hookimpl
    def search(self, query): ...

    @hookimpl
    def extract(self, task): ...
```

## Spectral Definitions (Instruments, Satellites, Products)

The spectral registry allows third-party packages to define custom satellite, sensor, and product taxonomies via YAML configuration or programmatic registration.

### 1. YAML Configuration (Recommended)

Define instruments, satellites, and products in YAML:

```yaml
instruments:
  - name: "OLI"
    url: "https://landsat.gsfc.nasa.gov/"

satellites:
  - name: "LANDSAT_8"

products:
  - name: "LC08_L1TP"
    instrument: "OLI"
    supported_satellites: ["LANDSAT_8"]
    channels:
      - c_id: "B1"
        resolution: 30
        band:
          name: "Coastal/Aerosol"
          type: "Visible"
          central_wavelength: 0.443
          bandwidth: 0.016
```

Point to your config:
```bash
export AER_SPECTRAL_CONFIG_PATH=/path/to/custom_sensor.yaml
```

### 2. Python API (Programmatic)

Register elements programmatically:

```python
from aer.spectral import Instrument, Satellite, Product, Channel, Band, BandType

# Register instruments and satellites
OLI = Instrument.register("OLI", "https://landsat.gsfc.nasa.gov/...")
LANDSAT_8 = Satellite.register("LANDSAT_8")

# Define channels
L8_BAND_1 = Channel(
    c_id="B1",
    instrument=OLI,
    band=Band(
        name="Coastal/Aerosol",
        band_type=BandType.VISIBLE,
        central_wavelength=0.443,
        bandwidth=0.016,
    ),
    resolution=30,
)

# Products auto-register on creation
LC08_PRODUCT = Product(
    name="LC08_L1TP",
    instrument=OLI,
    supported_satellites=frozenset([LANDSAT_8]),
    channels=(L8_BAND_1,),
)

# Now discoverable globally
assert Product.get("LC08_L1TP") is LC08_PRODUCT
```

## The API Surface

### Plugin System

| Operation | API |
|-----------|-----|
| Implement hook | `@hookimpl` decorator |
| Define spec | `@hookspec` decorator + `AerSpec` class |
| Load plugins | `pm.load_setuptools_entrypoints("aer.plugins")` |
| Call hooks | `pm.hook.search(query=...)` |
| Project name | `PROJECT_NAME = "aer"` |

### Spectral Registry

| Class | Registration | Query | Iterator |
|-------|------------|-------|----------|
| `Instrument` | `Instrument.register("NAME", url="...")` | `Instrument.get("NAME")` | `Instrument.all()` |
| `Satellite` | `Satellite.register("NAME", url="...")` | `Satellite.get("NAME")` | `Satellite.all()` |
| `BandType` | `BandType.register("Name")` | `BandType.get("Name")` | `BandType.all()` |
| `Product` | `Product(name="P", ...)` | `Product.get("P")` | `Product.all()` |

*Note: Registrations are **idempotent**. Calling `.register()` with the same name returns the existing instance.*

## Entry Points & Discovery

Plugins are discovered automatically via **Python Entry Points**. Declare them in `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
my_plugin = "my_package.module:PluginClass"
```

### Loading Behavior

- **Lazy loading**: `load_setuptools_entrypoints()` is called when you create a PluginManager
- **Multiple plugins**: Any number of plugins can implement the same hook
- **No conflicts**: Plugins don't conflict - they're all called in sequence (respecting tryfirst/trylast)

> [!IMPORTANT]
> **Workspace Discovery Root**: In a Polylith development environment, `importlib.metadata` reads discovery metadata from the package currently installed in the environment (the root `pyproject.toml` when using `uv sync` at the workspace root).
>
> If you add a new plugin to a `projects/` sub-package but **do not** add it to the root `pyproject.toml`, it will be missing during development. Always mirror your plugin entry points in the root configuration during active development.
