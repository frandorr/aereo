# Quick Start

Get from zero to your first extracted satellite image in under 5 minutes.

## 1. Install

Install AER and the GOES plugins (public S3, no authentication required):

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

Turn search results into extraction tasks. AER builds a grid over your AOI and chunks everything into parallelizable tasks.

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
client.execute_tasks(tasks)
```

## 6. Verify

Open your output directory (`./out/`) and look for `.tif` files. You now have analysis-ready GeoTIFFs on disk.

---

## Next Steps

- Explore more sensors in [Examples](examples.md) and [Using Plugins](using-plugins.md)
- Understand grid options in [Grid System](grid.md)
- Prefer the command line? See the [CLI guide](cli.md)
