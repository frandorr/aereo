# aer 🪐

**aer** (from the Greek word for *air*) is a modular, high-performance Python framework for satellite data discovery, extraction, and processing. Built with the Polylith architecture, it provides an extensible foundation for handling multi-sensor Earth observation data with a focus on type-safety and cloud-native workflows.

---

## ⚡️ Quickstart: The Simplest Example Ever

We designed `aer` so you can go from zero to extracted satellite data in minutes.

### 1. Installation

Install the core framework. We highly recommend using [`uv`](https://github.com/astral-sh/uv) to manage your Python projects!

```bash
pip install aer-core

# Optional: Install any community plugins you need for specific satellites.
# e.g., pip install aer-search-aws-goes
```

### 2. The One-Liner Pipeline

The easiest way to use `aer` is via the `run_pipeline` method. Give it a collection and a time range, and `aer` automatically handles searching, preparing, and extracting the data behind the scenes.

```python
from datetime import datetime, timezone
from aer.client import AerClient, FailureMode

# 1. Initialize the client (auto-discovers your installed plugins)
client = AerClient()

# 2. Run the end-to-end pipeline
results_df = client.run_pipeline(
    collections=["abi-l1b-radc"], # Use any collection supported by an installed plugin
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
    failure_mode=FailureMode.BEST_EFFORT,
)

print(f"Success! Pipeline completed with {len(results_df)} artifacts.")
```

---

## 📈 Intermediate: Step-by-Step Control

Sometimes you need more control than the automated pipeline. `aer` allows you to break the process into explicit, manageable steps: **Search**, **Prepare**, and **Extract**.

### Step 1: Search (Discovery)
Find available satellite data before committing time to download or process it. Results are returned as a schema-validated GeoDataFrame.

```python
search_results = client.search(
    collections=["abi-l1b-radc"],
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
)
print(f"Found {len(search_results)} matching assets across providers.")
```

### Step 2: Prepare (Task Generation)
Group your search results into logical extraction tasks. This is where you declare your output resolution or remote storage locations.

```python
tasks = client.prepare_for_extraction(
    search_results,
    resolution=1000.0,
    uri="s3://my-aer-bucket/processed_data/",
)
```

### Step 3: Extract (Processing)
Execute the prepared tasks. `aer` automatically routes tasks to the correct extraction plugins.

```python
artifacts = client.extract_batches(
    tasks,
    failure_mode=FailureMode.BEST_EFFORT,
    max_batch_workers=4  # 🚀 Enable multi-core parallel extraction!
)
print(f"Successfully processed {len(artifacts)} files.")
```

> [!TIP]
> Use `max_batch_workers` to parallelize extraction across multiple CPU cores. This is particularly effective for I/O bound tasks like downloading and resampling satellite granules.

---

## 🧠 Advanced: Building Plugins & Extending `aer`

`aer` is powered by an extensible plugin system based on standard Python entry points. If you need support for an unsupported satellite or catalog, you can just build a new plugin.

### The Plugin Registry
When you initialize `aer`, it scans your python environment for registered plugins. You can explore them manually:

```python
from aer.registry import AerRegistry

registry = AerRegistry()

# See exactly what your current environment is capable of processing
print("Supported collections:", registry.list_supported_collections())
```

### Core Architecture Concepts
`aer` consists of specialized, interoperable components decoupled into reusable Python Polylith blocks:
*   **Instrument-Agnostic Models**: Strongly typed data models for spectral bands, spatial grids, and temporal ranges.
*   **Vectorized Grid Engine**: A MajorTOM-compatible grid engine that uses vectorized grid cell generation and standard UTM projections.
*   **Extensible Extraction Profiles**: `ExtractionProfile` defines blueprints for extraction (resolution, variables) and includes an `extra_params` container for plugin-specific configuration (e.g., Satpy reader mappings).
*   **Decoupled Extraction Tasks**: `ExtractionTask` objects are now first-class citizens with explicit `aoi` and `prepare_params` attributes, making it easier to build plugins that respond to user constraints.
*   **Type-Safety First**: Uses `attrs` and `pandera` to ensure strict runtime enforcement of data models and geospatial dataframe schemas.

### Creating Your First Plugin

Plugins use object-oriented patterns under strict interfaces (`SearchProvider` and `Extractor`).

**1. Inherit from the interface:**

```python
from aer.interfaces import SearchProvider
from datetime import datetime
from typing import Sequence, Mapping, Any

class MyAwesomeSearch(SearchProvider):
    # MANDATORY: Declare what you handle!
    supported_collections = ["my-custom-sensor-l1"]

    def search(
        self,
        collections: Sequence[str],
        intersects: Any | None = None,
        start_datetime: datetime | None = None, # ...
    ):
        # Return a matched GeoDataFrame of results!
        ...
```

**2. Hook it in via `pyproject.toml`:**

```toml
[project.entry-points."aer.plugins"]
my_search = "my_package.plugin:MyAwesomeSearch"
```

For the full, detailed tutorial, check out the [Plugin Developer Guide](./docs/build-your-own-plugin.md).

---

## 🤝 Participating in Development

`aer` uses the **Polylith** architecture to make building, testing, and scaling large multi-module repositories a breeze.

### Setup locally
```bash
git clone https://github.com/frandorr/aer.git
cd aer
uv sync
```

### Testing
Because components are fully decoupled, you can test specifically what you change:

```bash
# Run tests for a specific component only
uv run pytest test/components/aer/spatial/

# Run the entire test suite
uv run pytest
```

### Adding New Components
Use the `uv poly` toolsuite to seamlessly spawn new infrastructure:
```bash
uv run poly create component --name my_feature
```

---

## 📄 License
MIT License
