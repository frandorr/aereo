# aer Plugin System

`aer` uses a modular, object-oriented plugin architecture built around standard Python `entry_points`. This allows developers to seamlessly register new search providers and extractors for satellite data collections without needing complex third-party hook libraries like `pluggy`.

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

from aer.interfaces import SearchProvider
from aer.schemas import AssetSchema

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

from aer.interfaces import Extractor
from aer.schemas import AssetSchema, ArtifactSchema

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

The `AerClient` module provides a simple, robust interface that handles object discovery, mapping collections to plugins, parallel search execution, and unified error handling (`FailureMode`).

```python
from datetime import datetime
from aer.client import AerClient, FailureMode

client = AerClient()

# 1. Run the entire pipeline in one go
artifacts_df = client.run_pipeline(
    collections=["my-satellite-data"],
    start_datetime=datetime(2023, 1, 1),
    end_datetime=datetime(2023, 1, 31),
    failure_mode=FailureMode.BEST_EFFORT, # Continue if some plugins fail
)

# 2. Or, run step-by-step for more control
search_ctx = client.search(
    collections=["my-satellite-data"],
    start_datetime=datetime(2023, 1, 1),
    end_datetime=datetime(2023, 1, 31)
)

print(f"Found {len(search_ctx.search_results)} assets.")

prep_ctx = search_ctx.prepare(prepare_params={"chunk_size": 10})
final_df = prep_ctx.extract(extract_params={"bands": ["B04"]})
```

## Advanced: Manual Plugin Management

If you need fine-grained control, use the `AerRegistry` directly. It parses `entry_points` and provides instantiated plugin objects.

```python
from aer.registry import AerRegistry

registry = AerRegistry()

# See what collections are supported overall
print(registry.list_supported_collections())

# Find which plugins can handle a specific collection
extractor_names = registry.find_extractors_for("my-satellite-data")

# Instantiate a specialized extractor
extractor = registry.get_extractor(extractor_names[0], global_config="...")
```

## Entry Points & Discovery

Plugins are discovered automatically via Python `entry_points`. Declare them in `pyproject.toml` under explicitly defined groups:

```toml
[project.entry-points."aer.search_providers"]
my_searcher = "my_package.module:MySearchProvider"

[project.entry-points."aer.extractors"]
my_extractor = "my_package.extraction:MyExtractor"
```

> [!IMPORTANT]
> **Workspace Discovery Root**: In a Polylith development environment, `importlib.metadata` reads discovery metadata from the package currently installed in the environment. If you add a new plugin to a `projects/` sub-package but **do not** add it to the root `pyproject.toml`, it will be missing during development. Always mirror your plugin entry points in the root configuration during active development.

To learn how to build and expose your own custom search providers and extractors natively, see [Build Your Own Plugin](./build-your-own-plugin.md).
