# Build Your Own `aer` Plugin

The `aer` framework is designed to be fully extensible using Python's standard **pluggy** plugin system. Third-party developers can create standalone Python packages that seamlessly integrate into the `aer` ecosystem.

## Quick Start

The **best and easiest approach** for building an `aer` plugin is to create a separate repository. This allows you to develop, test, and release your integration independently, without dealing with the core repository's Polylith architecture constraints.

## Step 1: Bootstrap Your Repository

We recommend using the [`enforce-template`](https://github.com/frandorr/enforce-template) as the foundation for your plugin. It comes pre-configured with the standard Python tooling (`uv`, `ruff`, `mypy`, `pytest` etc.) used across the `aer` ecosystem.

1. Go to [https://github.com/frandorr/enforce-template](https://github.com/frandorr/enforce-template).
2. Click **Use this template** -> **Create a new repository**.
3. Name your repository (e.g., `aer-plugin-acme`) and clone it locally.

## Step 2: Add Dependencies

Your plugin only needs to depend on the core `aer` package to access its hookspecs and types.

Update your `pyproject.toml` dependencies to include `aer-core`:

```toml
[project]
name = "aer-plugin-acme"
version = "0.1.0"
dependencies = [
    "aer-core",
    "geopandas",  # For search results
    # Add other dependencies your plugin requires (e.g., requests, boto3)
]
```

Install the dependencies:
```bash
uv sync
```

## Step 3: Write Your Plugin Logic

Plugins are classes that implement one or more **hookspecs** using the `@hookimpl` decorator. `aer` uses Python's **pluggy** library to manage plugins.

### Search Plugin Example

Create your plugin (e.g., in `acme_plugin/core.py`):

```python
"""ACME search plugin for aer."""

import geopandas as gpd
from pandera.typing.geopandas import GeoDataFrame

from aer.plugin import hookimpl
from aer.search import SearchQuery


class AcmeSearchPlugin:
    """Search plugin for ACME satellite data."""

    @hookimpl
    def search(self, query: SearchQuery) -> GeoDataFrame:
        """Search ACME API for satellite data.

        Parameters
        ----------
        query : SearchQuery
            Search parameters including collections, time range, spatial extent.

        Returns
        -------
        GeoDataFrame
            Search results with columns: collection, id, datetime, geometry.
        """
        # Your ACME API search logic here
        results = acme_api.search(
            collections=query.collections,
            datetime=query.datetime,
            intersects=query.intersects,
        )
        return gpd.GeoDataFrame(results)
```

### Extract Plugin Example

```python
"""ACME extract plugin for aer."""

from aer.plugin import hookimpl
from aer.extract import ExtractionTask


class AcmeExtractPlugin:
    """Extract plugin for ACME data."""

    @hookimpl
    def extract(self, task: ExtractionTask) -> ExtractionTask:
        """Download and extract ACME data.

        Parameters
        ----------
        task : ExtractionTask
            Task with source_url, output_path, and parameters.

        Returns
        -------
        ExtractionTask
            Task with status updated to SUCCESS or FAILED.
        """
        try:
            # Download from ACME source
            download(task.source_url, task.output_path)

            # Process/reproject if needed
            process(task.output_path)

            task.status = "SUCCESS"
            task.output_files = [task.output_path]
        except Exception as e:
            task.status = "FAILED"
            task.error = str(e)

        return task
```

## Step 4: Register the Entry Point

`aer` discovers third-party plugins automatically using **Python Entry Points**.

Add the plugin class path to your `pyproject.toml`:

```toml
[project.entry-points."aer.plugins"]
# Name = "module.path:ClassName"
acme_search = "acme_plugin.core:AcmeSearchPlugin"
acme_extract = "acme_plugin.extract:AcmeExtractPlugin"
```

## Step 5: Test Your Plugin

Test your plugin using pluggy's PluginManager:

```python
import pluggy
from aer.plugin import AerSpec, PROJECT_NAME
from acme_plugin.core import AcmeSearchPlugin

# Create plugin manager
pm = pluggy.PluginManager(PROJECT_NAME)
pm.add_hookspecs(AerSpec)

# Register your plugin
pm.register(AcmeSearchPlugin())

# Test the hook
from aer.search import SearchQuery
query = SearchQuery(
    collections=["acme_collection"],
    datetime="2024-01-01/2024-12-31",
    intersects=some_geometry,
)
results = pm.hook.search(query=query)
```

## Step 6: Distribute

Your plugin is just a standard Python package. Publish it to PyPI:

```bash
uv build
uv publish
```

Users install it like any other package:

```bash
pip install aer-plugin-acme
```

The plugin is automatically discovered when users create a plugin manager:

```python
import pluggy
from aer.plugin import AerSpec, PROJECT_NAME

pm = pluggy.PluginManager(PROJECT_NAME)
pm.add_hookspecs(AerSpec)
pm.load_setuptools_entrypoints("aer.plugins")  # Loads your plugin!
```

## Available Hooks

| Hook | Purpose | Input | Output |
|------|---------|-------|--------|
| `search` | Query satellite data | `SearchQuery` | `GeoDataFrame` |
| `prepare_tasks` | Create extraction tasks | `SearchQuery` | `list[ExtractionTask]` |
| `extract` | Download and process | `ExtractionTask` | `ExtractionTask` |

See `AerSpec` class in `aer.plugin` for detailed documentation.

---

## Troubleshooting: Local Development alongside `aer`

If you are developing your plugin *simultaneously* with the `aer` core framework on the same machine (e.g., using `uv` workspace paths), you might notice that `uv sync` installs the dependencies into your `.venv` and masks your local source edits.

This happens because `aer` uses `hatch-polylith-bricks`, which by default bundles files during an editable install.

To fix this and force `hatchling` to use `.pth` namespace pointer files instead of copying physical files, add `build.dev-mode-dirs` to the `[tool.hatch]` configuration in both your plugin's and `aer-core`'s `pyproject.toml` files:

```toml
[tool.hatch]
build.dev-mode-dirs = [ "../../components", "../../bases", "../../development", "." ]
# Make sure to adjust paths based on your repository structure!
```

Then clear the cached packages and reinstall:
```bash
rm -rf .venv/lib/python*/site-packages/aer
uv sync --reinstall-package aer-core --reinstall-package aer-plugin-acme
```
Your local imports will now properly resolve directly to your hot-reloading `components/` directory.

---

## Advanced: Hook Options

### Multiple Implementations

Multiple plugins can implement the same hook. Use `tryfirst` or `trylast` to control order:

```python
class PrimaryPlugin:
    @hookimpl(tryfirst=True)
    def search(self, query):
        # This runs first
        return results

class FallbackPlugin:
    @hookimpl(trylast=True)
    def search(self, query):
        # This runs last
        return fallback_results
```

### Optional Hooks

Mark hooks as optional if they might not exist in the spec:

```python
class ExperimentalPlugin:
    @hookimpl(optional=True)
    def experimental_feature(self, data):
        return processed_data
```

### Spec Name Aliasing

Map a method to a different hook name:

```python
class AliasedPlugin:
    @hookimpl(specname="search")
    def my_custom_search_method(self, query):
        return results
```
