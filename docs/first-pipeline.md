---
title: Your First Pipeline
redirect_from: quickstart.md
---

# Your First Pipeline

Get from zero to your first extracted satellite image in under 5 minutes. This
tutorial uses the existing `examples/01-sentinel2.ipynb` notebook, which searches
Planetary Computer for Sentinel-2 data and extracts a true-color GeoTIFF on the
Major TOM grid.

---

## 1. Install

```bash
pip install aereo aereo-search-planetary-computer
```

You will also need a Planetary Computer subscription key if you want signed
assets. See [Install](install.md) for credential setup.

---

## 2. Open the notebook

```bash
cd examples
jupyter lab 01-sentinel2.ipynb
```

The notebook contains the full pipeline. Below is a cell-by-cell explanation.

---

## 3. Load the job from a Hydra config package

AEREO pipelines are easiest to run when they are declared as a Hydra config
package. The repo ships an example package under `examples/config`.

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)
print(job.name)
print(job.output_uri)
```

A job bundles four things:

| Ingredient | Purpose |
|------------|---------|
| `grid_config` | How the AOI is tiled into Major TOM cells. |
| `patch_config` | Physical patch dimensions for extraction. |
| `extract` | The stage pipeline: reader, reprojector, writer, processors. |
| `output_uri` | Where artifacts and the catalog are written. |

Search providers and task builders are runtime arguments, not part of the job.

---

## 4. Search

```python
from aereo.builtins import search_stac

results = job.search(
    search_stac,
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime="2024-01-01T00:00:00Z",
    end_datetime="2024-01-10T23:59:59Z",
)
print(f"Found {len(results)} assets")
```

`job.search()` takes a search function and keyword arguments, and returns a
validated `GeoDataFrame[AssetSchema]`.

> [!TIP]
> **Search returns empty?** Check these three things:
> 1. **Collection name** — Collection names are case-sensitive. `sentinel-2-l1c` is wrong; `sentinel-2-l2a` is correct.
> 2. **Date range** — Sentinel-2 has a 5-day revisit at the equator. A one-day window may contain zero scenes for a small AOI; try widening to a week or month.
> 3. **AOI** — Make sure your GeoJSON intersects the sensor's orbit footprint.

---

## 5. Prepare tasks

```python
from aereo.builtins import build_grouped_tasks

tasks = job.build_tasks(results, build_grouped_tasks, cells_per_task=5)
print(f"Prepared {len(tasks)} extraction tasks")
```

`build_tasks()` turns search results into a list of `ExtractionTask` objects,
each carrying the grid cells, assets, and extraction stages it needs.

---

## 6. Extract

```python
from aereo.executors import LocalExecutor

artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
print(f"Extracted {len(artifacts)} artifacts")
```

Each task is run through the stage pipeline configured in `job.extract`. The
result is a `GeoDataFrame[ArtifactSchema]` with one row per extracted GeoTIFF.

---

## 7. Verify

Open `job.output_uri` and look for `.tif` files organized by Major TOM cell and
date. You now have analysis-ready GeoTIFFs on a shared grid.

---

## Next steps

- Run the same pipeline from the command line: [Run with CLI](run/run-with-cli.md)
- Understand the stage pipeline model: [Pipeline Architecture](concepts/pipeline-architecture.md)
- Choose grid settings for your AOI: [Working with Grids](concepts/grids.md)
- Browse more sensors: [Examples Gallery](examples/index.md)
- Build your own reader or search plugin: [Build Your First Plugin](plugins/build-first-plugin.md)
