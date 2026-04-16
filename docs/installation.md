# aer Core and Plugin Installation

The `aer` project uses a Polylith architecture, allowing for a lightweight core package and optional plugin extensions that use Python's standard `entry_points` system.

## Installing aer-core

`aer-core` provides the foundational domain models for spectral data, temporal ranges, spatial grids, and the plugin interfaces.

To install the core package:

```bash
# From the repository root
pip install projects/aer-core
```

This will install the `aer` package with the base components:
- `aer.spectral`: Instruments, Satellites, and Products
- `aer.temporal`: TimeRange logic
- `aer.spatial`: Grid and cell management
- `aer.schemas`: Pydantic/Pandera schemas for Assets and Artifacts
- `aer.interfaces`: Interfaces for plugins (`SearchProvider`, `Extractor`)
- `aer.registry`: The automatic plugin discovery `AerRegistry`
- `aer.client`: The primary entrypoint `AerClient`
- `aer.settings`: Environment configuration

## Using the Plugin System

The plugin system dynamically discovers packages that declare specifically named entry points. The highest level API is `AerClient`.

### Basic Usage

```python
from datetime import datetime
from aer.client import AerClient

# Create the pipeline orchestrator
client = AerClient()

# It will automatically find and dispatch searches to registered plugins supporting "my-collection"
search_ctx = client.search(
    collections=["my-collection"],
    start_datetime=datetime(2024, 1, 1),
    end_datetime=datetime(2024, 2, 1),
    intersects=my_geometry
)

print(f"Found {len(search_ctx.search_results)} assets!")
```

## Installing a Plugin

Plugins provide concrete implementations (e.g., search fetchers, download backends).

Using `aer-search-earthaccess` as an example:

```bash
pip install projects/aer-search-earthaccess
```

Once installed, the plugin automatically registers itself. You can verify this in a Python REPL:

```python
from aer.registry import AerRegistry

registry = AerRegistry()

# Check registered implementations
print(registry.find_searchers_for("HLSL30"))
# ["earthaccess"]
```

## Developer Guide: Creating a New Plugin Project

To create a new plugin natively inside the `aer` repository using the Polylith structure:

### 1. Create a New Polylith Project
Project definitions live in `projects/` and determine which components (bricks) are bundled into the distribution.

```bash
uv run poly create project --name aer_my_plugin --description "Description of my plugin"
```

### 2. Configure the Project
Edit `projects/aer_my_plugin/pyproject.toml` to include the foundational components and your specific implementation component.

```toml
[tool.polylith.bricks]
"components/aer/interfaces" = "aer/interfaces"   # Plugin interfaces
"components/aer/schemas" = "aer/schemas"         # Data schemas
"components/aer/my_plugin" = "aer/my_plugin"     # Your implementation component
# ... other dependencies
```

### 3. Build and Distribute
You can now build a wheel for your plugin:

```bash
cd projects/aer_my_plugin
uv build
```

## How Plugin Discovery Works

The plugin system uses Python's standard `importlib.metadata` entry points mechanism:

1. You declare plugins in `pyproject.toml` under `[project.entry-points."aer.search_providers"]` and `[project.entry-points."aer.extractors"]`
2. The `AerRegistry` scans installed packages for these hooks dynamically upon instantiation.
3. Classes listed in entry points are stored, matching their declared `supported_collections` to facilitate fast lookups and automated execution dynamically.

To learn how to implement the code for a search provider or extractor, read [Build Your Own Plugin](./build-your-own-plugin.md).
