# AEREO Pipeline Walkthrough

This page walks through a complete AEREO extraction end-to-end, showing the
objects you meet at each step and how they fit together. The screenshots come
from the Sentinel-2 sample notebook (`examples/01-sentinel2.ipynb`), but the
same flow applies to any sensor plugin.

---

## What we are building

AEREO turns a **user query** (AOI + time range + collections) into
analysis-ready GeoTIFFs. The pipeline has three logical steps:

1. **Search and task preparation** — find the satellite assets and turn them
   into parallel `ExtractionTask`s.
2. **Extraction pipeline** — for every task, read the raw data and optionally
   preprocess, reproject, and postprocess it.
3. **Write and catalog** — the orchestrator writes files, intersects each file
   with the MajorTOM grid, and returns a validated artifact catalog.

---

## Step 1: Search and Task preparation

### Architecture

<img src="../assets/pipeline-walkthrough/01-step1-search-and-task-preparation.png" alt="Step 1: SearchProvider produces a GeoDataFrame that the TaskBuilder turns into extraction tasks" width="400px">

The first step is orchestrated by `ExtractionJob.search()` and
`ExtractionJob.build_tasks()`:

* **`SearchProvider`** queries the chosen catalog (STAC, Earthaccess, etc.) and
  returns a `GeoDataFrame` validated against `AssetSchema`.
* **`TaskBuilder`** takes that `GeoDataFrame` and groups assets into
  `ExtractionTask` objects. The default builder groups by `start_time` and
  native CRS.

The result is a sequence of isolated tasks that can later be executed in
parallel.

### Search output: `GeoDataFrame[AssetSchema]`

<img src="../assets/pipeline-walkthrough/02-search-results-geodataframe.png" alt="Search results as a GeoDataFrame with one row per asset/granule" width="700px">

Each row is one discovered asset. The key columns are:

| Column | Why it matters |
|--------|----------------|
| `id` | Unique granule/asset identifier used downstream. |
| `collection` | Collection name, e.g. `sentinel-2-l2a`. |
| `geometry` | Satellite swath footprint in WGS84. |
| `channel_id` | Band or channel name when assets are split by band. |
| `start_time` / `end_time` | Acquisition window. |

### Prepared tasks: `Sequence[ExtractionTask]`

<img src="../assets/pipeline-walkthrough/03-extraction-tasks.png" alt="A list of ExtractionTask objects produced by the TaskBuilder" width="700px">

`build_tasks()` returns `ExtractionTask` objects. Each task carries:

* `id` — a stable identifier,
* `assets` — the subset of the search results this task will read,
* `job` — the configured reader, processors, reprojector, and writer,
* `output_uri` — where the artifacts should land.

Because each task is self-contained, the next step can run them in parallel
without shared state.

---

## Step 2: Extraction pipeline

### Architecture

![Step 2: each ExtractionTask runs Reader -> Preprocessor -> Reprojector -> Postprocessor -> Writer](../assets/pipeline-walkthrough/05-step2-extraction-pipeline.png)

Every `ExtractionTask` is executed independently through the same stage
pipeline:

1. **Reader** opens the source assets and returns an `xr.Dataset`.
2. **Preprocessors** (optional) transform the data — select bands, mask clouds,
   compute indices, etc.
3. **Reprojector** (optional) warps the data to a target CRS/resolution or to
   each grid cell's GeoBox.
4. **Postprocessors** (optional) apply final transformations.

Because tasks are isolated, you can safely parallelize this step with an
executor such as `LocalExecutor` or `LambdaExecutor`.

### Reader output: raw `xr.Dataset`

<img src="../assets/pipeline-walkthrough/06-reader-output-xarray-dataset.png" alt="Raw xarray.Dataset returned by the Reader, before any reprojection" width="450px">

The reader loads the requested variables (`red`, `nir`) into a single
`xarray.Dataset`. Notice:

* Dimensions are still in the **native projection** (`y`, `x`, `time`).
* `time` has length 1 because this example uses a single acquisition.
* Coordinates include `spatial_ref` (the EPSG code) and the original
  acquisition timestamps.
* Data are loaded lazily as Dask arrays when the reader supports it.

### Reprojector output

With `reproject_mode="raw"`, the whole scene is warped to a single target
CRS/resolution. With `reproject_mode="grid"`, the orchestrator loops over the
MajorTOM cells that intersect the dataset footprint and reprojects each cell to
its local UTM geobox. In both cases the result is an `xr.Dataset` ready for the
writer.

---

## Step 3: Write and catalog

### Architecture

<img src="../assets/pipeline-walkthrough/08-step3-write-to-grid.png" alt="Step 3: the orchestrator writes files and builds the artifact catalog" width="400px">

The final step is handled by the orchestrator:

1. **Time splitting** — if the dataset has a `time` dimension, one file is
   written per time step.
2. **Writer** — persists each slice as a GeoTIFF following the EOIDS layout.
3. **Artifact catalog** — reads the written file's footprint, intersects it
   with the MajorTOM grid, and emits one `ArtifactSchema` row per cell.

### Artifact output: `GeoDataFrame[ArtifactSchema]`

<img src="../assets/pipeline-walkthrough/09-artifact-output-geodataframe.png" alt="Final artifact GeoDataFrame with one row per intersecting grid cell" width="700px">

`job.execute()` returns a validated `GeoDataFrame` with one row per
intersecting grid cell:

| Column | Why it matters |
|--------|----------------|
| `id` | Unique artifact ID, often combining cell, variable and timestamp. |
| `uri` | Absolute path to the written GeoTIFF. |
| `grid_cell` | MajorTOM cell ID, e.g., `439D_593L`. |
| `start_time` / `end_time` | Acquisition window carried over from the source asset. |

For raw extractions that cover many cells, multiple rows point to the same
output file URI.

### Visual check: resulting artifacts on the grid

<img src="../assets/pipeline-walkthrough/04-extracted-patches-spatial-overview.png" alt="Extracted patches spatial overview showing the resulting MajorTOM grid cells and satellite scene" width="750px">

The red solid lines are the MajorTOM grid cells that intersect the satellite
scene; the dashed rectangle is the full scene extent. This is the final mosaic
of extracted artifacts — each cell has been written as a separate GeoTIFF on the
shared grid.

---

## Full code snippet

```python
from aereo.builtins import build_grouped_tasks, search_stac
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

# 1. Load the declarative job configuration
job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)

# 2. Step 1: search + prepare tasks
results = job.search(search_stac(...))
tasks = job.build_tasks(results, build_grouped_tasks)

# 3. Steps 2 & 3: extract, write, and catalog
artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))

print(f"Wrote {len(artifacts)} artifacts to {job.output_uri}")
```

---

## Where to go next

* Learn the stage model in detail: [Pipeline Architecture](pipeline-architecture.md)
* Choose grid settings for your AOI: [Working with Grids](grids.md)
* Run the same pipeline from the CLI: [Run with CLI](../run/run-with-cli.md)
* Build a custom reader or search plugin: [Build Your First Plugin](../plugins/build-first-plugin.md)
