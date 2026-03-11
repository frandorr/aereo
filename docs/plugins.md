# aer Plugin System

`aer` uses a **unified plugin registry** with a type-aware **Capability Graph**. This allows third-party developers to register new search backends, download backends, or data transformations using a single `@plugin` decorator — no base classes, no config files.

## How it Works

The plugin system has two layers:

1. **Spectral Registry** — `Instrument`, `Satellite`, `BandType`, and `Product` are immutable frozen dataclasses backed by class-level registries. When you call `.register()`, it instantiates your new element and adds it to the global namespace.

2. **Plugin Registry** — The `PluginRegistry` provides a unified registry for all functional plugins (search, download, transform, etc.). It automatically infers input/output types from function annotations, building a **Capability Graph** of all available data pipelines.

## Writing a Plugin

### The `@plugin` Decorator

Creating a plugin is just decorating a typed function:

```python
from aer.plugin import plugin
import geopandas as gpd

@plugin(name="my_filter", category="transform")
def filter_large_granules(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only granules above 50 MB."""
    return gdf[gdf["size_mb"] > 50]
```

That's it. The registry automatically:
1. Extracts the input type (`GeoDataFrame`) and return type (`GeoDataFrame`) from annotations.
2. Registers the function in the global plugin registry.
3. Adds an edge to the Capability Graph so the plugin can be discovered and chained.

### Using Plugins

```python
from aer.plugin import plugin_registry

# Discover all plugins
for p in plugin_registry.all():
    print(p)  # <Plugin 'earthaccess' (search): SearchQuery -> GeoDataFrame>

# Use a plugin by name
search = plugin_registry.get("earthaccess")
gdf = search(query)

# Visualise possible type transitions
from aer.search import SearchQuery
plugin_registry.show_capabilities(SearchQuery)
# [*] SearchQuery
#  └── (earthaccess) -> GeoDataFrame
#       └── (my_filter) -> GeoDataFrame
```

### Chaining Plugins with Pipeline

```python
from aer.plugin import Pipeline

# Type transitions are validated at construction time
pipe = Pipeline("earthaccess", "my_filter")
result = pipe.run(query)
```

## Spectral Definitions (Instruments, Satellites, Products)

The spectral registry allows third-party packages to define entirely custom satellite, sensor, and product taxonomies. Because these taxonomies are pure metadata, `aer` supports an extensible **YAML Configuration System**.

### 1. YAML Configuration (Recommended)

You can define custom instruments, satellites, bands, and products in a `.yaml` file. The framework will parse and register these objects automatically at runtime.

Create a file `custom_sensor.yaml`:
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

Then point the environment variable to your file or directory of files:
```bash
export AER_SPECTRAL_CONFIG_PATH=/path/to/custom_sensor.yaml
```

The config loader will instantly pre-register all objects globally in `Product.all()`, so components like search plugins can use it immediately without requiring code changes.

### 2. Python API (Programmatic)

If you must define elements programmatically, use `.register()` on the core typestate markers. Always capture the return value of `.register()` for type safety:

Because plugins extend the namespace dynamically, always capture the return value of `.register()` for type safety:

```python
from aer.spectral import Instrument, Satellite, BandType, Band, Channel, Product

# Register new instruments and satellites
OLI = Instrument.register("OLI", "https://landsat.gsfc.nasa.gov/...")
LANDSAT_8 = Satellite.register("LANDSAT_8")

# Define channels using standard aer interfaces
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

### Plugin Registry

| Operation | API |
|---|---|
| Register | `@plugin(name="...", category="...")` |
| Get by name | `plugin_registry.get("name")` |
| List all | `plugin_registry.all()` |
| Show graph | `plugin_registry.show_capabilities(StartType)` |
| Chain | `Pipeline("step1", "step2").run(input)` |

### Spectral Registry

| Class | Registration | Query | Iterator |
|---|---|---|---|
| `Instrument` | `Instrument.register("NAME", url="...")` | `Instrument.get("NAME")` | `Instrument.all()` |
| `Satellite` | `Satellite.register("NAME", url="...")` | `Satellite.get("NAME")` | `Satellite.all()` |
| `BandType` | `BandType.register("Name")` | `BandType.get("Name")` | `BandType.all()` |
| `Product` | `Product(name="P", ...)` | `Product.get("P")` | `Product.all()` |

*Note: Registrations are **idempotent**. Calling `.register()` with the same name returns the existing instance.*

## Entry Points & Discovery

Functional plugins (search, download, etc.) are discovered automatically via **Python Entry Points**. The `PluginRegistry` scans for entry points in the `aer.plugins` group.

### The Bootstrap Mechanism

To eagerly load all installed plugins, call `bootstrap()`:

```python
from aer.bootstrap import bootstrap
bootstrap()
```

Alternatively, `plugin_registry.get()` and `plugin_registry.all()` trigger lazy loading on first access.

### Plugin Discovery (Entry Points)

Plugins are declared in the `[project.entry-points]` section of your `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
earthaccess = "aer.search_earthaccess.core:search_earthaccess"
```

> [!IMPORTANT]
> **Workspace Discovery Root**: In a Polylith development environment, `importlib.metadata` reads discovery metadata from the package currently installed in the environment (the root `pyproject.toml` when using `uv sync` at the workspace root).
>
> If you add a new plugin to a `projects/` sub-package but **do not** add it to the root `pyproject.toml`, it will be missing from the registry during development, leading to `KeyError: "Plugin '...' is not registered."`. Always mirror your plugin entry points in the root configuration during active development.
