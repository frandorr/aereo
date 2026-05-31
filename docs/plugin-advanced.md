# Advanced Plugin Patterns

This page covers advanced topics for plugin developers: local development workflows, custom schemas, testing strategies, and multi-backend support.

---

## Local Development alongside `aereo`

If you are developing your plugin *simultaneously* with the `aereo` core framework on the same machine (e.g., using `uv` workspace paths), you might notice that `uv sync` installs dependencies into your `.venv` and masks your local source edits.

This happens because `aereo` uses `hatch-polylith-bricks`, which by default bundles files during an editable install.

To fix this and force `hatchling` to use `.pth` namespace pointer files instead of copying physical files, add `build.dev-mode-dirs` to the `[tool.hatch]` configuration in both your plugin's and `aereo`'s `pyproject.toml` files:

```toml
[tool.hatch]
build.dev-mode-dirs = [ "../../components", "../../bases", "../../development", "." ]
# Make sure to adjust paths based on your repository structure!
```

Then clear the cached packages and reinstall:

```bash
rm -rf .venv/lib/python*/site-packages/aereo
uv sync --reinstall-package aereo --reinstall-package aereo-plugin-acme
```

Your local imports will now properly resolve directly to your hot-reloading `components/` directory.

> [!TIP]
> The `projects/aereo-core/pyproject.toml` in the core repo already configures `build.dev-mode-dirs` for the main workspace. You only need to add the same setting to your plugin's `pyproject.toml` when working across both repositories.

---

## Custom Schemas

By default, plugins return `GeoDataFrame[AssetSchema]` (search) and `GeoDataFrame[ArtifactSchema]` (extraction). These schemas enforce a common column structure across all plugins.

If your data source requires additional metadata columns, you can extend the base schemas. However, keep in mind that downstream tools expecting the standard columns may ignore extra fields. Document any additional columns clearly in your plugin's README.

```python
from pandera import DataFrameSchema, Column
import pandera as pa

# Example: extending with a custom quality-score column
ExtendedAssetSchema = AssetSchema.add_columns(
    {"quality_score": Column(pa.Float, nullable=True)}
)
```

---

## Multi-Backend Extraction

The `AereoClient` abstracts backend selection, but you can also invoke backends directly in custom workflows:

```python
from aereo.backends import LocalProcessBackend, ThreadBackend

# Single-machine parallel extraction (CPU-bound)
local = LocalProcessBackend(max_workers=4)

# Single-machine parallel extraction (I/O-bound)
threads = ThreadBackend(max_workers=8)
```

When designing an `Extractor`, keep the `extract` method stateless and idempotent. The backend handles scheduling and retry logic; your plugin should focus on the per-batch data transformation.

---

## Testing Strategies

Unit-test your plugin without requiring live satellite data by mocking the search and extract inputs:

```python
import geopandas as gpd
from shapely.geometry import Point
from aereo.schemas import AssetSchema

# Build a minimal valid search-results GeoDataFrame
mock_results = gpd.GeoDataFrame({
    "id": ["test-001"],
    "collection": ["acme-l1"],
    "datetime": ["2023-01-01T00:00:00Z"],
    "geometry": [Point(0, 0)],
    "assets": [{"data": {"href": "https://example.com/data.tif"}}],
})

# Validate against AssetSchema before passing to your extractor
validated = AssetSchema.validate(mock_results)
```

For integration tests, use `pytest` fixtures that spin up a temporary `AereoClient` and assert that your plugin is discovered correctly:

```python
from aereo.registry import AereoRegistry

def test_plugin_discovery():
    registry = AereoRegistry()
    assert "acme_search" in registry._searchers
    assert "acme_extract" in registry._extractors
```

---

## Plugin Parameter Best Practices

- **Use `required_params` sparingly.** Prefer `optional_params` with sensible defaults so users can get started quickly.
- **Choose descriptive `description` strings.** These surface in CLI help text and auto-generated documentation.
- **Use `"choice"` types for enums.** This enables UI widgets (dropdowns) in future marketplace tools.
- **Validate inside `search`/`extract`, not just in params.** Parameter metadata is for introspection; runtime validation should still guard against malformed API responses.
