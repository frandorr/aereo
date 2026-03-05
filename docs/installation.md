# aer Core and Plugin Installation

The `aer` project uses a Polylith architecture, allowing for a lightweight core package and optional plugin extensions.

## Installing aer-core

`aer-core` provides the foundational domain models for spectral data, temporal ranges, spatial grids, and the plugin registry.

To install the core package:

```bash
# From the repository root
pip install projects/aer_core
```

This will install the `aer` package with the base components:
- `aer.spectral`: Instruments, Satellites, and Products
- `aer.temporal`: TimeRange logic
- `aer.spatial`: Grid and cell management
- `aer.search`: SearchQuery, SearchResultSchema
- `aer.plugin`: Unified plugin registry and `@plugin` decorator
- `aer.settings`: Environment configuration
- `aer.bootstrap`: Centralized initialization

## Initializing the Plugin System

Plugins are loaded lazily on first access. You can also eagerly load all plugins:

```python
from aer.bootstrap import bootstrap

# This loads all entry-point plugins (search, download, etc.)
bootstrap()
```

## Installing a Plugin

Plugins provide concrete implementations (e.g., search fetchers, download backends).

Using `aer-search-earthaccess` as an example:

```bash
pip install projects/aer_search_earthaccess
```

Once installed, the plugin automatically registers itself. You can verify this in a Python REPL:

```python
from aer.plugin import plugin_registry

# The plugin from the separate package is now available in the registry
earthaccess = plugin_registry.get("earthaccess")
print(earthaccess)
# <Plugin 'earthaccess' (search): SearchQuery -> GeoDataFrame>
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
"components/aer/plugin" = "aer/plugin"           # Plugin registry
"components/aer/my_plugin" = "aer/my_plugin"     # Your implementation
"components/aer/spectral" = "aer/spectral"       # Data models
"components/aer/temporal" = "aer/temporal"        # Time models
# ... other dependencies
```

### 3. Register your Plugin
In your component's `core.py`, decorate your function with `@plugin`:

```python
from aer.plugin import plugin
from aer.search import SearchQuery
import geopandas as gpd

@plugin(name="my_plugin_name", category="search")
def my_custom_search(query: SearchQuery) -> gpd.GeoDataFrame:
    # Your implementation here
    ...
```

Then declare the entry point in `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
my_plugin_name = "aer.my_plugin.core:my_custom_search"
```

### 4. Build and Distribute
You can now build a wheel for your plugin:

```bash
cd projects/aer_my_plugin
uv build
```
