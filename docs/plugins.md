# aereoeo Plugin System

`aereo` uses a modular, object-oriented plugin architecture built around standard Python `entry_points`. This allows developers to seamlessly register new search providers and extractors for satellite data collections without needing complex third-party hook libraries like `pluggy`.

## How it Works

The plugin system relies on clear, strongly-typed interfaces defined in `aer.interfaces`. Plugins subclass these base classes, and an internal `AerRegistry` discovers them at runtime.

### The Pipeline (`AerClient`)

The data orchestration lifecycle consists of three core stages, managed cohesively by the `AerClient`:

1.  **Search**: `SearchProvider` plugins query satellite data collections and return standardized `AssetSchema` GeoDataFrames. The `AerClient` concurrently dispatches searches across multiple plugins.
2.  **Prepare**: `Extractor` plugins break down the search results into discrete execution batches (e.g., grouping by time, location, or file).
3.  **Extract**: `Extractor` plugins download, reproject, and format the data into unified `ArtifactSchema` GeoDataFrames.

## The API Surface

`aer.interfaces` provides the core interfaces that plugins must implement:

### `SearchProvider`

Responsible for querying remote APIs and building the initial asset footprint.
Plugins must declare `supported_collections` as a sequence of strings.

```python
from typing import Mapping, Sequence, Any
from datetime import datetime
from shapely.geometry.base import BaseGeometry
from pandera.typing.geopandas import GeoDataFrame

from aereo.interfaces import SearchProvider
from aereo.schemas import AssetSchema

class MySearchProvider(SearchProvider):
    supported_collections = ["my-satellite-data"]

    def search(
        self,
        collections: Sequence[str],
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        search_params: Mapping[str, Any] | None,
    ) -> GeoDataFrame[AssetSchema]:
        ...
```

### `Extractor`

Responsible for generating task batches and running data extraction.
Plugins must declare `supported_collections` as a sequence of strings.

```python
from typing import Any
from pandera.typing.geopandas import GeoDataFrame
from aereo.interfaces import Extractor
from aereo.schemas import AssetSchema, ArtifactSchema

class MyExtractor(Extractor):
    supported_collections = ["my-satellite-data"]

    def prepare_for_extraction(
        self,
        search_results: GeoDataFrame[AssetSchema],
        prepare_params: dict[str, Any] | None,
    ) -> list[GeoDataFrame[AssetSchema]]:
        ...

    def extract(
        self,
        assets_batch: GeoDataFrame[AssetSchema],
        extract_params: dict[str, Any] | None,
    ) -> GeoDataFrame[ArtifactSchema]:
        ...
```

## Using the High-Level API (Recommended)

The `AerClient` provides a simple, robust interface that handles plugin discovery, collection routing, parallel search, and configurable error handling.

### Usage

```python
from datetime import datetime, timezone
from aereo.client import AerClient
from aereo.interfaces import AerProfile

client = AerClient()

profiles = [
    AerProfile(
        name="goes_c07",
        resolution=2000,
        collections={"ABI-L1b-RadF": ["C07"]},
        extract_params={"reader": "abi_l1b"},
    )
]

# 1. Search
search_results = client.search(
    profiles=profiles,
    start_datetime=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
)
print(f"Found {len(search_results)} assets.")

# 2. Prepare tasks
tasks = client.prepare_for_extraction(
    search_results,
    profiles=profiles,
    uri="output/goes",
)

from aereo.execution import LocalProcessBackend

# 3. Extract
backend = LocalProcessBackend(max_workers=4)
artifacts_df = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(artifacts_df)} artifacts.")
```

## Advanced: Manual Plugin Management

If you need fine-grained control, use the `AerRegistry` directly. It parses `entry_points` and provides instantiated plugin objects.

```python
from aereo.registry import AerRegistry

registry = AerRegistry()

# See what collections are supported overall
print(registry.list_supported_collections())

# Find which plugins can handle a specific collection
extractor_names = registry.find_extractors_for("ABI-L1b-RadF")

# Instantiate a specialized extractor
extractor = registry.get_extractor(extractor_names[0])
```

## Entry Points & Discovery

Plugins are discovered automatically via Python `entry_points`. Declare them in `pyproject.toml` under the unified `aereo.plugins` group:

```toml
[project.entry-points."aereo.plugins"]
my_searcher = "my_package.module:MySearchProvider"
my_extractor = "my_package.extraction:MyExtractor"
```

> [!IMPORTANT]
> **Workspace Discovery Root**: In a Polylith development environment, `importlib.metadata` reads discovery metadata from the package currently installed in the environment. If you add a new plugin to a `projects/` sub-package but **do not** add it to the root `pyproject.toml`, it will be missing during development. Always mirror your plugin entry points in the root configuration during active development.

To learn how to build and expose your own custom search providers and extractors natively, see [Build Your Own Plugin](./build-your-own-plugin.md).
