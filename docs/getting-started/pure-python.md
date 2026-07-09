# Pure Python Quickstart

You do not need YAML or Hydra to use AerEO. Every pipeline stage is a plain
Python function, so you can build an `ExtractionJob` directly and pass the
functions you need.

## Full example

```python
import os
from datetime import datetime, timezone

from shapely.geometry import Polygon

from aereo.builtins import (
    build_grouped_tasks,
    read_odc_stac,
    search_stac,
    write_geotiff,
)
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")

# Tiny AOI around Chocón reservoir, Argentina.
aoi = Polygon(
    [
        (-68.90986824592407, -39.23705421799603),
        (-68.65925870907353, -39.23705421799603),
        (-68.65925870907353, -39.41589522092947),
        (-68.90986824592407, -39.41589522092947),
        (-68.90986824592407, -39.23705421799603),
    ]
)

job = ExtractionJob(
    name="quickstart",
    grid_dist=10_000,
    output_uri="/tmp/aereo_quickstart",
    read=read_odc_stac,
    write=write_geotiff,
    target_aoi=aoi,
)

if DRY_RUN:
    print("DRY_RUN enabled: skipping search/build-tasks/extract.")
else:
    assets = job.search(
        search_stac,
        stac_api_url="https://earth-search.aws.element84.com/v1",
        collections={"sentinel-2-l2a": ["red", "nir"]},
        intersects=aoi,
        start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )
    print(f"Found {len(assets)} asset rows")

    tasks = job.build_tasks(assets, build_grouped_tasks, cells_per_task=5)
    print(f"Built {len(tasks)} task(s)")

    artifacts = job.execute(tasks, executor=LocalExecutor(workers=1))
    print(f"Extracted {len(artifacts)} artifact(s)")

    catalog_uri = job.write_catalog(artifacts)
    print(f"Catalog written to: {catalog_uri}")
```

Run it without network calls:

```bash
DRY_RUN=true uv run python examples/quickstart_pure_python.py
```

Run it for real:

```bash
uv run python examples/quickstart_pure_python.py
```

## What is happening?

1. **Build the job** — `ExtractionJob` holds the grid size, output URI, AOI,
   and the `read`/`write` functions that define the extraction pipeline.
2. **Search** — `job.search(search_stac, ...)` returns a validated
   `GeoDataFrame[AssetSchema]`.
3. **Build tasks** — `job.build_tasks(assets, build_grouped_tasks, ...)` groups
   assets by time and native CRS into `ExtractionTask` objects.
4. **Execute** — `job.execute(tasks, executor=...)` runs each task and writes
   GeoTIFFs plus an `artifacts.parquet` catalog.

## When to use pure Python

- Prototyping in a notebook.
- Building dynamic jobs where the AOI or time range comes from another part of
  your code.
- Writing unit tests for plugins.

For production and reusable configs, the Hydra package shown in
[Config Package](../configuration/config-package.md) is usually more convenient.
See the [YAML Schema](../configuration/yaml-schema.md) section for details on the
YAML schema and overrides.
