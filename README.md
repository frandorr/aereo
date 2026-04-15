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

`aer` uses standard Python `entry_points` for plugin discovery. The plugin system provides a complete pipeline for satellite data processing.

### How It Works

1. **Plugins** are discovered via Python entry points mapped to interfaces (`SearchProvider`, `Extractor`)
2. **Collection-based dispatch** automatically routes tasks to the correct plugins via `AerRegistry`
3. **Simple Pipeline API** for users via `AerClient`: `search` → `prepare` → `extract`

### Discovery & Registry

Plugins are automatically loaded and instantiated by the `AerClient` and `AerRegistry`:

```python
from aer.client import AerClient
from aer.registry import AerRegistry

# View available plugins
registry = AerRegistry()
collections = registry.list_supported_collections()  # ["goes-16", "HLSL30", ...]

# The client orchestrates tasks across plugins automatically
client = AerClient(registry=registry)
search_ctx = client.search(collections=["goes-16"])
```

### Creating a New Plugin

`aer` relies on object-oriented inheritance for new plugins. To create a new search backend, you must:

**1. Inherit from a core interface** and implement methods. E.g. `SearchProvider` or `Extractor`:

```python
from aer.interfaces import SearchProvider
from datetime import datetime
from typing import Sequence, Optional, Mapping, Any

class MySearchPlugin(SearchProvider):
    # MANDATORY: declares which collections this plugin handles
    supported_collections = ["goes-16", "goes-18"]

    def search(
        self,
        collections: Sequence[str],
        intersects: Optional[Any] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None,
        search_params: Optional[Mapping[str, Any]] = None,
    ):
        # Your search implementation returning standard GeoDataFrame schemas
        return df
```

**2. Register via entry points** in your `pyproject.toml`:

```toml
[project.entry-points."aer.search_providers"]
my_plugin = "my_package.plugin:MySearchPlugin"
```

Find the full walkthrough for writing new plugins in our [Plugin Developer Guide](./docs/build-your-own-plugin.md).

---

## 🛠 Usage Example

The complete pipeline is seamlessly managed by `AerClient`: `search` → `prepare` → `extract`

```python
from aer.client import AerClient, FailureMode
from datetime import datetime

client = AerClient()

# Execute the entire workflow in one command!
results_df = client.run_pipeline(
    collections=["goes-16", "HLSL30"],
    start_datetime=datetime(2024, 8, 1),
    end_datetime=datetime(2024, 8, 2),
    intersects=my_geometry,
    failure_mode=FailureMode.BEST_EFFORT # Continue even if one plugin fails
)

print(f"Extracted {len(results_df)} assets successfully!")
```

**Available Pipeline methods:**

| Method | Description |
|----------|-------------|
| `AerClient.search(...)` | Search for data by collection identifiers, returning `SearchResultContext` |
| `SearchResultContext.prepare(...)` | Group search results into extraction tasks (`PreparedExtractionContext`) |
| `PreparedExtractionContext.extract(...)` | Execute download and extraction for grouped tasks |
| `AerClient.run_pipeline(...)` | Syntactic sugar wrapping all three steps consecutively |

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
