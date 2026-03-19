---
description: "Create public API for search → extract workflow"
depends_on: []
wave: 1
autonomous: true
files_modified:
  - components/aer/plugin/core.py
  - components/aer/plugin/__init__.py
  - test/components/aer/plugin/test_api.py
requirements:
  - PIPE-01
  - PIPE-02
  - PIPE-03
---

<objective>
Create a simple public API function that orchestrates search → extract. No Pipeline class changes — just a callable function that finds and invokes plugins by name and category via the existing PluginRegistry. Bootstrap already discovers extract plugins since they register under `aer.plugins`.
</objective>

<task>
  <objective>Add a public `run_search` function to `aer.plugin`</objective>
  <read_first>
    - components/aer/plugin/core.py
    - components/aer/search/core.py
    - components/aer/extract/core.py
  </read_first>
  <action>
    In `components/aer/plugin/core.py`, add a top-level function:

    ```python
    def run_search(plugin_name: str, query: "SearchQuery", **kwargs: Any) -> gpd.GeoDataFrame:
        """Run a search plugin by name and return results."""
        info = plugin_registry.get(plugin_name, "search")
        return info(query, **kwargs)
    ```

    Import `geopandas as gpd` at the top (or use `from __future__ import annotations` + string annotation).
    This is a thin convenience wrapper around `plugin_registry.get()`.
  </action>
  <acceptance_criteria>
    - `components/aer/plugin/core.py` contains `def run_search(`
    - Function calls `plugin_registry.get(plugin_name, "search")`
  </acceptance_criteria>
</task>

<task>
  <objective>Add a public `run_extract` function to `aer.plugin`</objective>
  <read_first>
    - components/aer/plugin/core.py
    - components/aer/extract/core.py
  </read_first>
  <action>
    In `components/aer/plugin/core.py`, add a top-level function:

    ```python
    def run_extract(plugin_name: str, gdf: gpd.GeoDataFrame, output_dir: str, **kwargs: Any) -> gpd.GeoDataFrame:
        """Run an extract plugin by name on search results."""
        info = plugin_registry.get(plugin_name, "extract")
        return info(gdf, output_dir, **kwargs)
    ```

    This mirrors `run_search` for the extract step. Users call search, get a GeoDataFrame, then call extract.
  </action>
  <acceptance_criteria>
    - `components/aer/plugin/core.py` contains `def run_extract(`
    - Function calls `plugin_registry.get(plugin_name, "extract")`
  </acceptance_criteria>
</task>

<task>
  <objective>Export new functions from `aer.plugin.__init__`</objective>
  <read_first>
    - components/aer/plugin/__init__.py
  </read_first>
  <action>
    Add `run_search` and `run_extract` to imports and `__all__` in `components/aer/plugin/__init__.py`:

    ```python
    from aer.plugin.core import (
        PluginRegistry,
        plugin,
        plugin_registry,
        Pipeline,
        PluginInfo,
        run_search,
        run_extract,
    )

    __all__ = ["PluginRegistry", "plugin", "plugin_registry", "Pipeline", "PluginInfo", "run_search", "run_extract"]
    ```
  </action>
  <acceptance_criteria>
    - `components/aer/plugin/__init__.py` contains `run_search`
    - `components/aer/plugin/__init__.py` contains `run_extract`
    - `__all__` includes both new functions
  </acceptance_criteria>
</task>

<task>
  <objective>Write unit tests for the public API</objective>
  <read_first>
    - components/aer/plugin/core.py
    - test/components/aer/plugin/
  </read_first>
  <action>
    Create `test/components/aer/plugin/test_api.py` with tests:

    1. `test_run_search()` — Register a mock search plugin with `@plugin(name="mock", category="search")`, call `run_search("mock", query)`, assert it returns expected data.
    2. `test_run_extract()` — Register a mock extract plugin with `@plugin(name="mock", category="extract")`, call `run_extract("mock", gdf, output_dir)`, assert return.
    3. `test_run_search_not_found()` — Call `run_search("nonexistent", query)`, assert `KeyError` raised.
    4. `test_run_extract_not_found()` — Call `run_extract("nonexistent", gdf, dir)`, assert `KeyError` raised.

    Run tests with `uv run pytest test/components/aer/plugin/test_api.py`.
  </action>
  <acceptance_criteria>
    - `test/components/aer/plugin/test_api.py` contains `def test_run_search`
    - `test/components/aer/plugin/test_api.py` contains `def test_run_extract`
    - Command `uv run pytest test/components/aer/plugin/test_api.py` exits with code 0
  </acceptance_criteria>
</task>

<verification>
<must_haves>
- `run_search` and `run_extract` are importable from `aer.plugin`
- Both dispatch to `plugin_registry.get(name, category)` and call the plugin
- Tests pass with mock plugins
- No changes to existing Pipeline class
</must_haves>
<step>
Run `uv run pytest test/components/aer/plugin/test_api.py` to validate.
</step>
</verification>
