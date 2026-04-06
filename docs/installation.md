# aer Core and Plugin Installation

The `aer` project uses a Polylith architecture, allowing for a lightweight core package and optional plugin extensions that use Python's standard pluggy system.

## Installing aer-core

`aer-core` provides the foundational domain models for spectral data, temporal ranges, spatial grids, and the plugin hookspecs.

To install the core package:

```bash
# From the repository root
pip install projects/aer-core
```

This will install the `aer` package with the base components:
- `aer.spectral`: Instruments, Satellites, and Products
- `aer.temporal`: TimeRange logic
- `aer.spatial`: Grid and cell management
- `aer.search`: SearchQuery, SearchResultSchema
- `aer.plugin`: Pluggy hookspecs (`AerSpec`, `hookimpl`, `hookspec`)
- `aer.settings`: Environment configuration

## Using the Plugin System

The plugin system uses **pluggy**, the same plugin system used by pytest. Plugins are loaded via Python entry points.

### Basic Usage

```python
import pluggy
from aer.plugin import AerSpec, PROJECT_NAME

# Create and configure the plugin manager
pm = pluggy.PluginManager(PROJECT_NAME)
pm.add_hookspecs(AerSpec)

# Load all installed plugins from entry points
pm.load_setuptools_entrypoints("aer.plugins")

# Now you can use the plugins
from aer.search import SearchQuery

query = SearchQuery(
    collections=["HLSL30"],
    datetime="2024-01-01/2024-02-01",
    intersects=my_geometry,
)

# Call the search hook - all registered search plugins will be invoked
results = pm.hook.search(query=query)
```

## Installing a Plugin

Plugins provide concrete implementations (e.g., search fetchers, download backends).

Using `aer-search-earthaccess` as an example:

```bash
pip install projects/aer-search-earthaccess
```

Once installed, the plugin automatically registers itself when you call `load_setuptools_entrypoints()`. You can verify this in a Python REPL:

```python
import pluggy
from aer.plugin import AerSpec, PROJECT_NAME

pm = pluggy.PluginManager(PROJECT_NAME)
pm.add_hookspecs(AerSpec)
pm.load_setuptools_entrypoints("aer.plugins")

# Check registered implementations
print(pm.hook.search.get_hookimpls())
# [<HookImpl plugin_name='earthaccess' ...>]
```

## Developer Guide: Creating a New Plugin Project

To create a new plugin using the Polylith structure:

### 1. Create a New Polylith Project
Project definitions live in `projects/` and determine which components (bricks) are bundled into the distribution.

```bash
uv run poly create project --name aer_my_plugin --description "Description of my plugin"
```

### 2. Configure the Project
Edit `projects/aer_my_plugin/pyproject.toml` to include the foundational components and your specific implementation component.

```toml
[tool.polylith.bricks]
"components/aer/search" = "aer/search"          # Search model
"components/aer/plugin" = "aer/plugin"         # Plugin hookspecs
"components/aer/my_plugin" = "aer/my_plugin"   # Your implementation
"components/aer/spectral" = "aer/spectral"       # Data models
"components/aer/temporal" = "aer/temporal"       # Time models
# ... other dependencies
```

### 3. Implement Your Plugin
In your component's `core.py`, implement the hook using `@hookimpl`:

```python
from aer.plugin import hookimpl
from aer.search import SearchQuery
from pandera.typing.geopandas import GeoDataFrame

class MyPlugin:
    @hookimpl
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search using my custom data source."""
        # Your implementation here
        results = my_api.search(...)
        return GeoDataFrame(results)
```

Then declare the entry point in `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
my_plugin_name = "aer.my_plugin.core:MyPlugin"
```

### 4. Build and Distribute
You can now build a wheel for your plugin:

```bash
cd projects/aer_my_plugin
uv build
```

## How Plugin Discovery Works

The plugin system uses Python's standard `importlib.metadata` entry points mechanism:

1. You declare plugins in `pyproject.toml` under `[project.entry-points."aer.plugins"]`
2. When `pm.load_setuptools_entrypoints("aer.plugins")` is called, pluggy scans all installed packages
3. Classes listed in entry points are instantiated and their `@hookimpl` methods are registered
4. When you call `pm.hook.search()`, all registered search implementations are invoked

This is the same mechanism used by pytest, tox, and other major Python tools.
