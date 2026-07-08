# Your First Pipeline

Get from zero to your first extracted satellite image in under 5 minutes. This
tutorial uses the Sentinel-2 Hydra config package that ships with AerEO.

## 1. Install

```bash
uv add aereo
# or
pip install aereo
```

AerEO's core includes built-in STAC and NASA Earthaccess search, plus reading
and writing. Plugins for other sensors and formats are installed separately;
see [Install](../install.md) for common combinations.

## 2. Load the job

AerEO pipelines are easiest to run when they are declared as a Hydra config
package. The repo ships an example package under `examples/config`. See the
[Configuration](../configuration/config-package.md) section for a deep dive into
the YAML files and Hydra composition.

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)
print(job.name)
print(job.output_uri)
```

A job bundles the stable parts of an extraction:

| Ingredient | Purpose |
|---|---|
| `grid_dist` | How the AOI is tiled into Major TOM cells. |
| `resolution` | Target pixel resolution in metres (used by reprojection / grid indexing). |
| `read` | Callable that opens assets into an `xr.Dataset`. |
| `write` | Callable that writes extracted patches to disk or object store. |
| `output_uri` | Where artifacts and the catalog are written. |

Search providers and task builders are runtime arguments, not part of the job.

## 3. Search

```python
from aereo.builtins import search_stac

assets = job.search(
    search_stac,
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime="2024-01-01T00:00:00Z",
    end_datetime="2024-01-10T23:59:59Z",
)
print(f"Found {len(assets)} assets")
```

`job.search()` takes a search function and keyword arguments, and returns a
validated `GeoDataFrame[AssetSchema]`.

!!! tip "Search returns empty?"

    1. **Collection name** — Collection names are case-sensitive. Use
       `sentinel-2-l2a`, not `sentinel-2-l1c`.
    2. **Date range** — Sentinel-2 has a 5-day revisit at the equator. A one-day
       window may contain zero scenes for a small AOI; try widening to a week or
       month.
    3. **AOI** — Make sure your GeoJSON intersects the sensor's orbit footprint.

## 4. Prepare tasks

```python
from aereo.builtins import build_grouped_tasks

tasks = job.build_tasks(
    assets, build_grouped_tasks, cells_per_task=5
)
print(f"Prepared {len(tasks)} extraction tasks")
```

`build_tasks()` turns search results into a list of `ExtractionTask` objects,
each carrying the assets and the parent job that defines the extraction
pipeline.

## 5. Extract

```python
from aereo.executors import LocalExecutor

artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
print(f"Extracted {len(artifacts)} artifacts")
```

Open `job.output_uri` — you have GeoTIFFs on the Major TOM grid and an
`artifacts.parquet` catalog.

## Next steps

- [Configuration](../configuration/config-package.md) — understand the config package and YAML schema.
- [Pure Python Quickstart](pure-python.md) — build the same pipeline without
  Hydra.
- [Core Concepts](concepts.md) — learn how jobs, tasks, and plugins fit
  together.
- [Sentinel-2 tutorial](../examples/01-sentinel2.ipynb) — a runnable notebook
  with outputs.
