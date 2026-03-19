# Build Your Own `aer` Plugin

The `aer` framework is designed to be fully extensible. Third-party developers can create standalone Python packages that seamlessly integrate into the `aer` ecosystem. This guide explains how to build and distribute your own plugins.

The **best and easiest approach** for building an `aer` plugin is to create a separate repository. This allows you to develop, test, and release your integration independently, without dealing with the core repository's Polylith architecture constraints.

## Step 1: Bootstrap Your Repository

We recommend using the [`enforce-template`](https://github.com/frandorr/enforce-template) as the foundation for your plugin. It comes pre-configured with the standard Python tooling (`uv`, `ruff`, `mypy`, `pytest` etc.) used across the `aer` ecosystem.

1. Go to [https://github.com/frandorr/enforce-template](https://github.com/frandorr/enforce-template).
2. Click **Use this template** -> **Create a new repository**.
3. Name your repository (e.g., `aer-plugin-acme`) and clone it locally.

## Step 2: Add Dependencies

Your plugin only needs to depend on the core `aer` package to access its taxonomies, models, and decorators.

Update your `pyproject.toml` dependencies to include `aer-core`:

```toml
[project]
name = "aer-plugin-acme"
version = "0.1.0"
dependencies = [
    "aer-core",
    # Add other dependencies your plugin requires (e.g., requests, boto3)
]
```

Install the dependencies:
```bash
uv sync
```

## Step 3: Write Your Plugin Logic

Plugins are simply typed functions decorated with the `@plugin` marker. `aer` uses these type hints to build a Capability Graph that resolves how data flows between components.

Create your plugin logic (e.g., in `acme_plugin/core.py`):

```python
import geopandas as gpd
from aer.plugin import plugin
from aer.search import SearchQuery

@plugin(name="acme_search", category="search")
def run_acme_search(query: SearchQuery) -> gpd.GeoDataFrame:
    """Search for data using the ACME system."""
    # ...
    return gpd.GeoDataFrame(...)

@plugin(name="acme_extract", category="extract")
def run_acme_extract(gdf: gpd.GeoDataFrame, output_dir: str) -> gpd.GeoDataFrame:
    """Extract and reproject ACME data to the grid cell in 'overlapping_spatial_extent'."""
    # ...
    return gpd.GeoDataFrame(...)
```

## Step 4: Register the Entry Point

`aer` discovers third-party plugins automatically using standard Python Entry Points.

Add the exact path to your decorated function into your `pyproject.toml` under the `[project.entry-points."aer.plugins"]` section:

```toml
[project.entry-points."aer.plugins"]
# Name = "module.path:function_name"
acme_search = "acme_plugin.core:run_acme_search"
```

## Step 5: Test and Distribute

You can now test your plugin locally. When users install both `aer-core` and your plugin package, the plugin will be detected automatically!

```python
from aer.bootstrap import bootstrap
from aer.plugin import plugin_registry

# Bootstraps the plugin system, scanning installed packages
bootstrap()

# Your plugin is now part of the ecosystem!
from aer.plugin import run_search, run_extract

# 1. Search
results = run_search("acme_search", query)

# 2. Extract
extracted = run_extract("acme_extract", results, "/tmp/acme")
```

Because your plugin is just a standard Python package, you can publish it to PyPI (`uv build` and `uv publish`) or share it internally. Users just `pip install aer-plugin-acme` and they are ready to go!
