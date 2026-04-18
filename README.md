# aer 🪐

**aer** (from the Greek word for *air*) is a modular, high-performance Python framework for satellite data discovery, extraction, and processing. Built with the [Polylith architecture](https://davidvujic.github.io/python-polylith-docs/setup/) and powered by `uv`, it provides an extensible foundation for handling multi-sensor Earth observation data with a focus on type-safety and cloud-native workflows.

---

## 🚀 Key Features

*   **Modular Architecture**: Built using Python Polylith. Logic is decoupled into reusable `components`, while `projects` assemble them into deployable artifacts.
*   **Instrument-Agnostic Domain Models**: Strongly typed definitions for `spectral` bands, `spatial` grids, and `temporal` ranges — independent of any specific satellite mission.
*   **Extensible Plugin System**: A registry-based system that allows seamless addition of new search and extraction capabilities via standard Python entry points.
*   **MajorTOM-Compatible Grid Engine**: First-class support for the ESA MajorTOM grid naming convention, with vectorized grid cell generation and UTM-projected area definitions.
*   **Performance First**: Leverages `uv` for lightning-fast dependency management and `attrs` for efficient data modeling.

---

## 🏗 Project Structure (Polylith)

The codebase is organized into interchangeable bricks:

*   **`components/aer/`**: Reusable functional blocks (e.g., `spectral`, `spatial`, `temporal`, `grid`, `schemas`, `interfaces`, `registry`).
*   **`bases/aer/client/`**: The orchestration client (`AerClient`) that wires registry, search, preparation, and extraction into a unified pipeline.
*   **`projects/`**: Deployable packages (e.g., `aer-core`). These assemble components and bases into installable distributions.
*   **`test/`**: Mirrors the component structure for unit testing, plus `test/integration` for cross-component validation.

---

## 🔌 The Plugin System

`aer` uses standard Python `entry_points` for plugin discovery. The plugin system provides a complete pipeline for satellite data processing.

### How It Works

1. **Plugins** are discovered via Python entry points under the `aer.plugins` group.
2. **Collection-based dispatch** automatically routes tasks to the correct plugin via `AerRegistry`: each plugin declares which data collections it supports.
3. **Typed interfaces** define the contract: plugins inherit from `SearchProvider` (data discovery) or `Extractor` (data retrieval and processing).
4. **Pipeline API** for users via `AerClient`: `search` → `prepare` → `extract`.

### Discovery & Registry

Plugins are automatically loaded and instantiated by the `AerClient` and `AerRegistry`:

```python
from aer.client import AerClient
from aer.registry import AerRegistry

# View available plugins and collections
registry = AerRegistry()
collections = registry.list_supported_collections()  # e.g. ["abi-l1b-radc", "VJ203IMG", ...]

# The client orchestrates tasks across plugins automatically
client = AerClient(registry=registry)
```

### Creating a New Plugin

`aer` relies on class-based inheritance for new plugins. To create a new search or extraction backend:

**1. Inherit from a core interface** and implement the required methods:

```python
from aer.interfaces import SearchProvider
from datetime import datetime
from typing import Sequence, Mapping, Any

class MySearchPlugin(SearchProvider):
    # MANDATORY: declares which collections this plugin handles
    supported_collections = ["my-collection-l1", "my-collection-l2"]

    def search(
        self,
        collections: Sequence[str],
        intersects: Any | None = None,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        search_params: Mapping[str, Any] | None = None,
    ):
        # Your search implementation returning a GeoDataFrame[AssetSchema]
        ...
```

**2. Register via entry points** in your `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
my_search = "my_package.plugin:MySearchPlugin"
```

Find the full walkthrough for writing new plugins in our [Plugin Developer Guide](./docs/build-your-own-plugin.md).

---

## 🛠 Usage Examples

### 1. Search Only

Use `AerClient.search()` to discover data across any installed search plugin. Results are returned as a schema-validated `GeoDataFrame`:

```python
from datetime import datetime, timezone
from aer.client import AerClient

client = AerClient()

# Search for data in a collection supported by an installed plugin
search_ctx = client.search(
    collections=["my-collection-l1"],
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
    search_params={"channels": ["1", "13"]},
)

results = search_ctx.search_results
print(f"Found {len(results)} assets")
print(results[["collection", "start_time", "href"]].head())
```

### 2. Search + Prepare + Extract

After searching, prepare batches and run extraction through the installed extractor plugin:

```python
from aer.client import AerClient, FailureMode
from datetime import datetime, timezone

client = AerClient()

# Step 1: Search
search_ctx = client.search(
    collections=["my-collection-l1"],
    start_datetime=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 2, tzinfo=timezone.utc),
)

# Step 2: Prepare — groups search results into extraction tasks
prep_ctx = search_ctx.prepare()

# Step 3: Extract — runs each extractor plugin on its assigned tasks
artifacts = prep_ctx.extract(failure_mode=FailureMode.BEST_EFFORT)
print(f"Extracted {len(artifacts)} artifacts")
```

### 3. Full Pipeline (one-liner)

Use `run_pipeline()` for the entire `search → prepare → extract` lifecycle:

```python
from aer.client import AerClient, FailureMode
from datetime import datetime, timezone

client = AerClient()

artifacts_df = client.run_pipeline(
    collections=["my-collection-l1"],
    start_datetime=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 2, tzinfo=timezone.utc),
    failure_mode=FailureMode.BEST_EFFORT,
)

print(f"Pipeline complete: {len(artifacts_df)} artifacts extracted")
```

### Available Pipeline API

| Method | Description |
|----------|-------------|
| `AerClient.search(...)` | Search for data by collection identifiers, returning `SearchResultContext` |
| `SearchResultContext.prepare(...)` | Group search results into extraction tasks (`PreparedExtractionContext`) |
| `PreparedExtractionContext.extract(...)` | Execute extraction for grouped tasks |
| `AerClient.run_pipeline(...)` | Convenience wrapper running all three steps sequentially |

---

## 📦 Installation & Setup

### Prerequisites
*   [uv](https://github.com/astral-sh/uv) (required for dependency management)

### Install `aer-core`

```bash
pip install aer-core
```

Then install the plugins you need. Search and extraction plugins are distributed as separate packages — install them to unlock specific data collection support.

### Development Setup

Clone the repository and sync the workspace for local development:

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
*   **Type Hinting**: `aer` uses strict type checking with `attrs`-based models and `pandera` schema validation.
*   **Plugin registration**: Plugins register under the `aer.plugins` entry point group and inherit from `SearchProvider` or `Extractor`.

---

## 📄 License

MIT
