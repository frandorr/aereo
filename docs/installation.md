# aer Core and Plugin Installation

The `aer` project uses a Polylith architecture, allowing for a lightweight core package and optional plugin extensions.

## Installing aer-core

`aer-core` provides the foundational domain models for spectral data, temporal ranges, spatial grids, and the search registry.

To install the core package:

```bash
# From the repository root
pip install projects/aer_core
```

This will install the `aer` package with the base components:
- `aer.spectral`: Instruments, Satellites, and Products
- `aer.temporal`: TimeRange logic
- `aer.spatial`: Grid and cell management
- `aer.search`: Plugin registry for search capabilities
- `aer.settings`: Environment configuration
- `aer.plugins`: Plugin loading infrastructure
- `aer.bootstrap`: Centralized initialization

## Initializing the Plugin System

While many components (like `SearchMethod`) handle discovery on-demand, you can also perform a centralized bootstrap:

```python
from aer.bootstrap import bootstrap

# This loads all known plugin groups (search, ingest, export, etc.)
bootstrap()
```

## Installing a Plugin

Plugins provide concrete implementations for the registry (e.g., search fetchers, data extractors).

Using `aer-search-earthaccess` as an example:

```bash
pip install projects/aer_search_earthaccess
```

Once installed, the plugin automatically registers itself. You can verify this in a Python REPL:

```python
from aer.search import SearchMethod

# The plugin from the separate package is now available in the registry
earthaccess_search = SearchMethod.get("earthaccess")
print(earthaccess_search)
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
"components/aer/search" = "aer/search"        # Registry
"components/aer/my_plugin" = "aer/my_plugin"  # Your implementation
"components/aer/spectral" = "aer/spectral"    # Data models
"components/aer/temporal" = "aer/temporal"    # Time models
# ... other dependencies
```

### 3. Register your Plugin
In your component's `core.py`, ensure you register your function with the global registry:

```python
from aer.search import SearchMethod

def my_custom_search(...):
    # logic
    pass

# This line ensures that when someone imports your component, it registers itself
MY_SEARCH = SearchMethod.register("my_plugin_name", my_custom_search)
```

### 4. Build and Distribute
You can now build a wheel for your plugin:

```bash
cd projects/aer_my_plugin
uv build
```
