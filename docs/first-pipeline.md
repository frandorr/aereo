---
title: Your First Pipeline
redirect_from: quickstart.md
---

# Your First Pipeline

Get from zero to your first extracted satellite image in under 5 minutes.

AEREO's entire user experience is built around three `AereoClient` methods: `search()`, `prepare_for_extraction()`, and `execute_tasks()`. This tutorial walks you through each one with a single sensor. For the full parameter reference and advanced patterns, see [Pipeline Options](pipeline-options.md).

## 1. Install

Install AEREO and the GOES plugins (public S3, no authentication required):

```bash
pip install aereo aereo-search-aws-goes aereo-extract-satpy
```

## 2. Define a profile

An `AereoProfile` describes *what* you want to extract, *from which sensor*, and *how*.

```python
from aereo.interfaces import AereoProfile

profile = AereoProfile(
    name="goes_c02",
    resolution=1000,
    collections={"ABI-L1b-RadF": ["C02"]},
    plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
    search_params={"satellite": "GOES-19"},
    extract_params={"reader": "abi_l1b", "calibration": "reflectance"},
)
```

## 3. Search

Find granules matching your time range and area of interest:

```python
from datetime import datetime, timezone
from shapely.geometry import box
from aereo.client import AereoClient

aoi = box(-70, -40, -68, -39)
client = AereoClient()

results = client.search(
    profiles=[profile],
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 10, tzinfo=timezone.utc),
    intersects=aoi,
)
print(f"Found {len(results)} assets")
```

## 4. Prepare

Turn search results into extraction tasks. AEREO builds a grid over your AOI and chunks everything into parallelizable tasks.

```python
from aereo.interfaces import GridConfig

tasks = client.prepare_for_extraction(
    results,
    profiles=[profile],
    uri="./out",
    grid_config=GridConfig(target_grid_dist=256000),
)
print(f"Prepared {len(tasks)} extraction tasks")
```

## 5. Extract

Run the extraction. Each task is handed to the extractor plugin, which downloads granules, resamples to the target grid, and writes GeoTIFFs.

```python
from aereo.execution import LocalProcessBackend

backend = LocalProcessBackend(max_workers=4)
artifacts = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(artifacts)} artifacts")
```

## 6. Verify

Open your output directory (`./out/`) and look for `.tif` files. You now have analysis-ready GeoTIFFs on disk.

---

## Next Steps

- Explore more sensors in [Examples Gallery](examples-gallery.md) and [How Plugins Work](plugin-overview.md)
- Understand grid options in [Working with Grids](grids.md)
- Prefer the command line? See the [CLI Recipes](cli-recipes.md)
- Learn advanced pipeline options in [Pipeline Options](pipeline-options.md)
