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

`aer` uses **pluggy** for plugin discovery. The plugin system provides a complete pipeline for satellite data processing.

### How It Works

1. **Plugins** are discovered via Python entry points
2. **Product-based dispatch** automatically selects the right plugin based on product
3. **Simple API** for users: `run_search` → `create_tasks` → `run_extract`

### Discovery & Registry

Plugins are automatically loaded when you use the API functions:

```python
from aer.plugin.api import run_search, list_available_products

# Plugins are loaded automatically via entry points
products = list_available_products()  # ["goes-16", "modis", ...]
results = run_search(products=["goes-16"])  # Auto-selects appropriate plugin
```

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

The complete pipeline: **search → create tasks → extract**

```python
from aer.plugin.api import run_search, create_tasks, run_extract
from aer.temporal import TimeRange
from datetime import datetime

# 1. Search for satellite data by product
results = run_search(
    products=["goes-16", "modis"],
    time_range=TimeRange(
        start=datetime(2024, 8, 1),
        end=datetime(2024, 8, 2)
    ),
    intersects=my_geometry
)
print(f"Found {len(results)} granules")

# 2. Create extraction tasks from search results
tasks = create_tasks(
    search_results=results,
    intersects=my_geometry,
    output_path="/tmp/extracted"
)

# 3. Extract data for each task
for task in tasks:
    run_extract(task, plugin_name="my_plugin")

print("Extraction complete!")
```

**Available API functions:**

| Function | Description |
|----------|-------------|
| `run_search(products, ...)` | Search for data by product identifiers |
| `create_tasks(search_results, ...)` | Transform results into extraction tasks |
| `run_extract(task, plugin_name)` | Extract data for a task |
| `list_available_products()` | List products with registered plugins |
| `list_plugins()` | List all registered plugin names |

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
