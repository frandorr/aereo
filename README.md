# aer 🪐

**aer** (from the Greek word for *air*) is a modular, high-performance Python framework designed for satellite data discovery, extraction, and processing. Built with the [Polylith architecture](https://davidvujic.github.io/python-polylith-docs/setup/) and powered by `uv`, it provides an extensible foundation for handling multi-sensor Earth observation data (GOES, VIIRS, MODIS, Sentinel-3) with a focus on type-safety and cloud-native workflows.

---

## 🚀 Key Features

*   **Modular Architecture**: Built using Python Polylith. Logic is decoupled into reusable `components`, while `projects` assemble them into deployable artifacts.
*   **Instrument-Agnostic Domain Models**: Strongly typed definitions for `spectral` bands, `spatial` grids, and `temporal` ranges.
*   **Extensible Plugin System**: A registry-based system that allows seamless addition of new search methods, instruments, and products via Python entry points.
*   **Cloud-Native Search**: Native integration with NASA Earthdata via the `search-earthaccess` plugin, returning type-validated `GeoDataFrame` objects with granule footprints.
*   **Performance First**: Leverages `uv` for lightning-fast dependency management and `attrs` for efficient data modeling.

---

## 🏗 Project Structure (Polylith)

The codebase is organized into interchangeable bricks:

*   **`components/aer/`**: Reusable functional blocks (e.g., `spectral`, `spatial`, `temporal`, `search`).
*   **`projects/`**: Deployable artifacts (e.g., `aer-search-earthaccess`). These assemble components and define plugin entry points.
*   **`test/`**: Mirrors the component structure for unit testing, plus `test/integration` for cross-component validation.

---

## 🔌 The Plugin System

`aer` is designed to be extended without modifying the core library. It uses a registry pattern discovered via `entry_points`.

### Discovery & Registry
Plugins register themselves into core registries (like `SearchMethod` or `Instrument`). To initialize all available plugins in your environment, use the bootstrap utility:

```python
from aer.bootstrap import bootstrap
bootstrap()  # Automatically discovers and loads all registered aer plugins
```

### Extending search
You can add new search implementations by registering them with `SearchMethod`. Projects define these in their `pyproject.toml`:

```toml
[project.entry-points."aer.plugins.search"]
earthaccess = "aer.search_earthaccess.core:SEARCH_EARTHACCESS"
```

> [!TIP]
> **Development Note**: When working in a Polylith workspace, plugins are discovered via Python entry points. Registering an entry point in a `project` sub-package makes it available for distribution, but for the plugin to be discoverable **during development** (i.e., when running `uv run`), you must also declare it in the root `pyproject.toml`. False discovery is often caused by missing these root-level entry point declarations.

### Creating a New Plugin

Aer uses **pluggy** for plugin discovery. To create a new plugin, you must:

**1. Declare mandatory attributes** on your plugin class:

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `plugin_type` | `"search"` or `"extract"` | ✅ Yes | Determines which hook to dispatch |
| `supported_products` | `list[str]` | ✅ Yes | Products this plugin handles (e.g., `["goes-16", "modis"]`) |

**2. Implement the appropriate hook(s):**

```python
from aer.plugin import hookimpl, AerSpec, PROJECT_NAME
import pluggy

class MySearchPlugin:
    # MANDATORY: declares this is a search plugin
    plugin_type = "search"

    # MANDATORY: declares which products this plugin handles
    supported_products = ["goes-16", "goes-18"]

    @hookimpl
    def search(self, collections, intersects, time_range, search_params):
        # Your search implementation
        return results
```

Or for an extract plugin:

```python
class MyExtractPlugin:
    plugin_type = "extract"
    supported_products = ["goes-16"]

    @hookimpl
    def extract(self, task):
        # Your extraction implementation
        return task
```

**3. Register via entry points** in your `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
my_plugin = "my_package.plugin:MySearchPlugin"
```

**4. Use product-based dispatch** in your application:

```python
from aer.plugin import PluginSelector, run_search

# Setup plugin manager
pm = pluggy.PluginManager("aer")
pm.add_hookspecs(AerSpec)
pm.load_setuptools_entrypoints("aer.plugins")

# Use selector with type filtering
selector = PluginSelector(pm)
selector.index_plugins()

# Auto-select search plugin for "goes-16"
plugin = selector.select(products=["goes-16"], plugin_type="search")

# Or use the high-level API (defaults to search type)
results = run_search(products=["goes-16"])
```

**Error handling:**

| Error | When raised |
|-------|-------------|
| `NoMatchingPluginError` | No plugins support the requested products |
| `PluginConflictError` | Multiple plugins support the same products (specify `plugin_name` to resolve) |
| `ValueError` | Invalid `plugin_type` (must be "search" or "extract") |

---

## 🛠 Usage Example

Search for VIIRS and MODIS data using the `earthaccess` plugin:

```python
from datetime import datetime
from aer.bootstrap import bootstrap
from aer.search import SearchMethod
from aer.product_viirs_earthaccess import VNP02MOD_EA
from aer.product_modis_earthaccess import MODIS_021KM_EA
from aer.temporal import TimeRange

# 1. Initialize the plugin system
bootstrap()

# 2. Define your search constraints
time_range = TimeRange(
    start=datetime(2024, 8, 1, 0, 0, 0),
    end=datetime(2024, 8, 2, 0, 0, 0),
)

# 3. Use the registered search method
search = SearchMethod.get("earthaccess")
results = search(
    products=[VNP02MOD_EA, MODIS_021KM_EA],
    time_range=time_range
)

print(f"Found {len(results)} granules")
# Search returns a validated GeoDataFrame
print(results[["product_name", "start_time", "geometry"]].head())
```

---

## 📦 Installation & Setup

### Prerequisites
*   [uv](https://github.com/astral-sh/uv) (required for dependency management)

### Setup
Clone the repository and sync the workspace:

```bash
git clone https://github.com/frandorr/aer.git
cd aer
uv sync
```

---

## 🤝 How to Participate

We follow the Polylith development workflow.

### Adding a New Component
Use the Polylith CLI to create a new brick:
```bash
uv run poly create component --name my_feature
```

### Running Tests
Always use `uv` to run tests:
```bash
# Run all tests
uv run pytest

# Run tests for a specific component
uv run pytest test/components/aer/spectral/
```

### Core Conventions
*   **Public API**: Only symbols exported in `__init__.py` via `__all__` should be imported by other components.
*   **Type Hinting**: `aer` uses strict type checking (Pydantic, attrs, returns).
*   **Plugin registration**: Follow the patterns in `aer.plugins` and `aer.bootstrap`.

---

## 📄 License

MIT
