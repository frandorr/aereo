# Build Your First Plugin

The `aereo` framework is fully extensible using Python's standard `entry_points` mechanism. Third-party developers can create standalone Python packages that integrate seamlessly into the `aereo` ecosystem.

The **best and easiest approach** is to create a separate repository. This lets you develop, test, and release independently, without dealing with the core repository's Polylith architecture constraints.

---

## Step 1: Bootstrap Your Repository

We recommend using the [`aereo-plugin-template`](https://github.com/frandorr/aereo-plugin-template) as the foundation. It is pre-configured with the standard Python tooling (`uv`, `ruff`, `pyright`, `pytest`) used across the `aereo` ecosystem.

1. Go to [https://github.com/frandorr/aereo-plugin-template](https://github.com/frandorr/aereo-plugin-template).
2. Click **Use this template** → **Create a new repository**.
3. Name your repository (e.g., `aereo-plugin-acme`) and clone it locally.

---

## Step 2: Add Dependencies

Your plugin only needs to depend on the core `aereo` package to access its interfaces and schemas.

Update `pyproject.toml`:

```toml
[project]
name = "aereo-plugin-acme"
version = "0.1.0"
dependencies = [
    "aereo",
    "geopandas",  # For returning standard schemas
    "pandera",    # For schema validation (optional but recommended)
]
```

Install the dependencies:

```bash
uv sync
```

---

## Step 3: Write Your Plugin Logic

Plugins are standard Python classes that inherit from `SearchProvider` or `Extractor` base classes defined in `aereo.interfaces`.

### Search Plugin

Create a search provider (e.g., in `acme_plugin/search.py`). Search plugins **must** declare `supported_collections`.

```python
"""ACME search plugin for aereo."""

from datetime import datetime
from typing import Any, Mapping, Sequence

import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

from aereo.interfaces import PluginParam, SearchProvider
from aereo.schemas import AssetSchema


class AcmeSearchProvider(SearchProvider):
    """Search plugin for ACME satellite data."""

    # REQUIRED: sequence of collections this plugin supports
    supported_collections = ["acme-l1", "acme-l2"]

    # OPTIONAL: declare parameters for introspection and validation
    required_params = [
        PluginParam(name="api_key", type="str", description="ACME API key", required=True),
    ]
    optional_params = [
        PluginParam(name="max_results", type="int", description="Max results per page", default=100),
    ]

    def search(
        self,
        collections: Sequence[str],
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        search_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[AssetSchema]:
        """Search ACME API for satellite data."""
        # Your ACME API search logic here

        # Example: Mocking a search request
        # results = acme_api.search(...)

        # Format the response as a GeoDataFrame that aligns with AssetSchema
        df = pd.DataFrame([
            {
                "id": "acme_item_001",
                "collection": collections[0],
                "datetime": datetime.utcnow(),
                "geometry": intersects if intersects else None,
                "assets": {"data": {"href": "https://acme.org/data.tif"}}
            }
        ])

        # Ensure it matches AssetSchema
        gdf = GeoDataFrame(df, geometry="geometry")
        return AssetSchema.validate(gdf)
```

### Extract Plugin

Create an extractor (e.g., in `acme_plugin/extract.py`). Extract plugins **must** declare `supported_collections` and implement both `prepare_for_extraction` and `extract`.

```python
"""ACME extract plugin for aereo."""

from typing import Any

from pandera.typing.geopandas import GeoDataFrame
from aereo.interfaces import PluginParam, Extractor
from aereo.schemas import AssetSchema, ArtifactSchema


class AcmeExtractor(Extractor):
    """Extract plugin for ACME data."""

    # REQUIRED: sequence of collections this plugin supports
    supported_collections = ["acme-l1"]

    # OPTIONAL: declare extraction parameters
    required_params = [
        PluginParam(name="output_format", type="choice", description="Output raster format", choices=["geotiff", "netcdf"], required=True),
    ]
    optional_params = [
        PluginParam(name="compression", type="str", description="GeoTIFF compression", default="deflate"),
    ]

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        prepare_params: dict[str, Any] | None,
    ) -> list[GeoDataFrame[AssetSchema]]:
        """Group search results into extraction batches."""

        # By default, split into single-row batches for individual download
        batches = []
        for i in range(len(search_results)):
            batches.append(search_results.iloc[[i]].copy())

        return batches

    def extract(
        self,
        assets_batch: GeoDataFrame[AssetSchema],
        extract_params: dict[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Download and extract ACME data for a batch."""
        extracted_artifacts = []

        for _, asset_row in assets_batch.iterrows():
            item_id = asset_row["id"]

            try:
                # 1. Download
                # file_path = download_file(asset_row["assets"]["data"]["href"])
                file_path = f"/tmp/extracted_{item_id}.tif"

                # 2. Append success artifact
                payload = asset_row.to_dict()
                payload["file_path"] = file_path
                payload["status"] = "SUCCESS"
                extracted_artifacts.append(payload)

            except Exception as e:
                # Append failed artifact
                payload = asset_row.to_dict()
                payload["status"] = "FAILED"
                payload["error"] = str(e)
                extracted_artifacts.append(payload)

        # Ensure return type matches ArtifactSchema rules
        from geopandas import GeoDataFrame as gpd_GeoDataFrame
        return ArtifactSchema.validate(gpd_GeoDataFrame(extracted_artifacts, geometry="geometry"))
```

---

## Step 4: Register the Entry Point

`aereo` discovers third-party plugins automatically using **Python Entry Points**.

Add the plugin class paths to `pyproject.toml` under the unified `aereo.plugins` group:

```toml
[project.entry-points."aereo.plugins"]
# alias = "module.path:ClassName"
acme_search = "acme_plugin.search:AcmeSearchProvider"
acme_extract = "acme_plugin.extract:AcmeExtractor"
```

---

## Step 5: Document Your Parameters

If you declared `required_params` and `optional_params`, users can introspect them at runtime via the `AereoRegistry`:

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()

# Get params for a single plugin
params = registry.get_plugin_params("acme_search")
print(params["required"])   # [PluginParam(name="api_key", ...)]
print(params["optional"])   # [PluginParam(name="max_results", ...)]

# Export a JSON catalog of every plugin's params
import json
print(json.dumps(registry.list_all_params(), indent=2))
```

This powers CLI help text, config validation, and plugin marketplace listings.

---

## Step 6: Configure Your Profiles

`AereoProfile` (also available as the backward-compat alias `ExtractionProfile`) is a **Pydantic `BaseModel`**. You get declarative validation, frozen immutability, and native JSON/YAML deserialization.

### Construct profiles in code

```python
from aereo.interfaces import AereoProfile

profile = AereoProfile(
    name="acme_l1",
    resolution=250,
    collections={"acme-l1": ["B01"]},
    plugin_hints={"search": "acme_search", "extract": "acme_extract"},
)
```

`AereoProfile` is frozen (`model_config = {"frozen": True}`) and forbids unknown fields (`"extra": "forbid"`), so typos raise a clear `ValidationError` immediately.

### Load profiles from YAML or JSON

```yaml
# profiles.yaml
profiles:
  - name: acme_l1
    resolution: 250
    collections:
      acme-l1: ["B01"]
    plugin_hints:
      search: acme_search
      extract: acme_extract
```

```python
from pathlib import Path
from aereo.interfaces import AereoProfile

# From a YAML file
profiles = AereoProfile.from_yaml(Path("profiles.yaml"))

# From a YAML string
profiles = AereoProfile.from_yaml_string(yaml_text)

# From a JSON file
profiles = AereoProfile.from_json(Path("profiles.json"))

# From a directory containing *.yaml / *.yml / *.json
profiles = AereoProfile.from_config_dir(Path("configs/"))
```

### Referencing a downloader by import path

The `downloader` field accepts a live callable or a dotted import path string. When loading from config, write the string and Pydantic's `ImportString` resolves it at validation time:

```yaml
profiles:
  - name: acme_l1
    resolution: 250
    collections:
      acme-l1: ["B01"]
    downloader: my_package.downloaders.custom_downloader
```

The resolved callable must match the `Downloader` signature: `Callable[[str, Path], None]`. If the module or attribute does not exist, Pydantic raises a clear `ValidationError`.

---

## Step 7: Test Your Plugin

Test your plugin using the high-level `AereoClient` API:

```python
from aereo.client import AereoClient
from aereo.interfaces import AereoProfile
from datetime import datetime
from pathlib import Path

# The client automatically discovers your entry points!
client = AereoClient()

# Load profiles from config (or build them in code)
profiles = AereoProfile.from_yaml(Path("profiles.yaml"))

# 1. Search
results = client.search(
    collections=["acme-l1"],
    start_datetime=datetime(2023, 1, 1),
    end_datetime=datetime(2023, 1, 31),
)

# 2. Prepare
tasks = client.prepare_for_extraction(
    results,
    profiles=profiles,
    uri="output/acme",
)

# 3. Extract
from aereo.execution import LocalProcessBackend

backend = LocalProcessBackend()
artifacts = client.execute_tasks(tasks, backend=backend)
print(artifacts[["id", "uri"]])
```

---

## Step 8: Distribute

Your plugin is just a standard Python package. Publish it to PyPI:

```bash
uv build
uv publish
```

Users install it like any other package:

```bash
pip install aereo-plugin-acme
```

---

## Interface Reference

| Interface | Purpose | Key Methods |
|-----------|---------|-------------|
| `SearchProvider` | Query satellite data | `search` |
| `Extractor` | Configure and run extractions | `prepare_for_extraction`, `extract` |

See the `aereo.interfaces` module for detailed documentation.

---

## Next Steps

- Read [How Plugins Work](plugin-overview.md) for a deeper dive into the plugin system and discovery mechanics.
- Explore [Advanced Plugin Patterns](plugin-advanced.md) for local development tips, custom schemas, and multi-backend strategies.
