# aer Installation Guide

## For Users (pip install)

### 1. Install the Core

```bash
pip install aer-core
```

This installs the `aer` package with all base components: `aer.client`, `aer.interfaces`, `aer.registry`, `aer.schemas`, `aer.spectral`, `aer.spatial`, `aer.grid`, and `aer.eoids`.

### 2. Install Plugins

`aer` is plugin-based — install only the plugins you need for your target sensors:

```bash
# GOES ABI (public S3, no auth needed) — recommended for first use
pip install aer-search-aws-goes aer-extract-satpy

# Sentinel-2 (Planetary Computer STAC, no auth needed)
pip install aer-search-pc-sentinel2 aer-extract-pc-sentinel2

# NASA sensors: MODIS, VIIRS, Sentinel-3 (Earthdata login required)
pip install aer-search-earthaccess aer-extract-satpy
```

### 3. Verify Installation

```python
from aer.registry import AerRegistry

registry = AerRegistry()
print("Supported collections:", registry.list_supported_collections())
# e.g. ['ABI-L1b-RadF', 'ABI-L2-AODF', 'MOD021KM', 'VJ202IMG', ...]
```

### 4. Earthdata Authentication (NASA sensors only)

MODIS, VIIRS, and Sentinel-3 data are hosted by NASA and require [Earthdata](https://urs.earthdata.nasa.gov/) credentials:

```bash
# Option 1: .netrc file (persistent)
echo "machine urs.earthdata.nasa.gov login YOUR_USER password YOUR_PASS" >> ~/.netrc
chmod 600 ~/.netrc

# Option 2: Environment variables (session-only)
export EARTHDATA_USERNAME=YOUR_USER
export EARTHDATA_PASSWORD=YOUR_PASS
```

---

## For Developers (from source)

### 1. Clone and Sync

```bash
git clone https://github.com/frandorr/aer.git
cd aer
uv sync
```

This installs the core framework, all plugins (editable), and development tools (`pytest`, `ruff`, `basedpyright`, etc.).

### 2. Verify

```bash
uv run python -c "from aer.registry import AerRegistry; r = AerRegistry(); print(r.list_supported_collections())"
```

### 3. Run Tests

```bash
# Specific component
uv run pytest test/components/aer/spatial/

# Full suite
uv run pytest
```

---

## Using the Plugin System

Once plugins are installed, the `AerClient` automatically discovers them via Python's `entry_points` mechanism. No manual registration needed.

### Basic Usage

```python
from datetime import datetime, timezone
from aer.client import AerClient
from aer.interfaces import ExtractionProfile

client = AerClient()

# Search automatically finds and dispatches to registered plugins
search_results = client.search(
    collections=["ABI-L1b-RadF"],
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
)
print(f"Found {len(search_results)} assets!")
```

---

## How Plugin Discovery Works

The plugin system uses Python's standard `importlib.metadata` entry points mechanism:

1. Plugins declare their classes in `pyproject.toml` under `[project.entry-points."aer.plugins"]`
2. The `AerRegistry` scans installed packages for these hooks dynamically upon instantiation
3. Classes listed in entry points are stored, matching their declared `supported_collections` for fast lookup

Collection name matching is **case-insensitive** — `"abi-l1b-radf"` and `"ABI-L1b-RadF"` both resolve to the same plugin.

To learn how to implement the code for a search provider or extractor, read [Build Your Own Plugin](./build-your-own-plugin.md).

---

## Creating a New Plugin Project

To create a new plugin natively inside the `aer` repository using the Polylith structure:

### 1. Create a New Polylith Project

```bash
uv run poly create project --name aer_my_plugin --description "Description of my plugin"
```

### 2. Configure the Project

Edit `projects/aer_my_plugin/pyproject.toml` to include foundational components:

```toml
[tool.polylith.bricks]
"components/aer/interfaces" = "aer/interfaces"
"components/aer/schemas" = "aer/schemas"
"components/aer/my_plugin" = "aer/my_plugin"
```

### 3. Build and Distribute

```bash
cd projects/aer_my_plugin
uv build
```
