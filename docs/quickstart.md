# Quick Start

Get from zero to your first extracted satellite image in under 5 minutes.

## Before You Begin

Install AER and the GOES plugins:

```bash
pip install aer-eo aer-search-aws-goes aer-extract-satpy
```

## Step 1: Search

Find granules matching your time range, area of interest, and profile.
AER fans the query out to registered search plugins in parallel and returns a GeoDataFrame of matching assets.

```python
from datetime import datetime, timezone
from shapely.geometry import box
from aer.client import AerClient
from aer.interfaces import AerProfile

# Define the area of interest (longitude/latitude bounds)
aoi = box(-69.76, -39.98, -68.24, -39.05)

# Describe what you want to extract
profiles = [
    AerProfile(
        name="goes_c02",
        resolution=500,  # output pixel size in metres
        collections={"ABI-L1b-RadF": ["C02"]},
        plugin_hints={"search": "search_aws_goes", "extract": "extract_satpy"},
        extract_params={"reader": "abi_l1b", "calibration": "reflectance"},
        search_params={"satellite": "GOES-19"},
    )
]

client = AerClient()

results = client.search(
    profiles=profiles,
    start_datetime=datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc),
    end_datetime=datetime(2026, 4, 2, 14, 9, tzinfo=timezone.utc),
    intersects=aoi,
)
print(f"Found {len(results)} assets")
```

## Step 2: Prepare

Turn search results into extraction tasks. AER builds a grid over your AOI, groups assets by time, and chunks everything into parallelizable tasks.

`target_grid_dist` sets the cell size in metres (here 256 km).
`target_grid_overlap=False` keeps cells from overlapping.
See the [Grid System](grid.md) docs for filter modes and advanced options.

```python
tasks = client.prepare_for_extraction(
    results,
    target_aoi=aoi,
    uri="/tmp/goes_extraction",
    profiles=profiles,
    target_grid_dist=256000,
    target_grid_overlap=False,
    prepare_params={"cells_per_chunk": 10},
)
print(f"Prepared {len(tasks)} extraction tasks")
```

## Step 3: Extract

Run the extraction. Each task is handed to the extractor plugin, which downloads granules, resamples to the target grid, and writes GeoTIFFs in EOIDS format.

```python
artifacts = client.extract_batches(
    tasks,
    max_batch_workers=None,  # set to e.g. 4 for parallel extraction
)
print(f"Extracted {len(artifacts)} artifacts")
```

The returned `artifacts` GeoDataFrame contains one row per extracted tile with columns such as `uri`, `geometry`, `grid_cell`, and `collection`.

## Next Steps

- Learn the full API in [Running the Pipeline](pipeline.md)
- Understand grid options in [Grid System](grid.md)
- Explore more sensors in [Using Plugins](using-plugins.md) and [Plugins](plugins.md)
