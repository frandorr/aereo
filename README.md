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

---

## 🛠 Usage Example

Search for VIIRS and MODIS data using the `earthaccess` plugin:

```python
from datetime import datetime
from aer.bootstrap import bootstrap
from aer.search import SearchMethod
from aer.spectral import VNP02MOD, MODIS_021KM
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
    products=[VNP02MOD, MODIS_021KM],
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
