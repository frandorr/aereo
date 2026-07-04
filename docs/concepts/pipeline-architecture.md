# AEREO Pipeline Architecture

This document describes the three-phase AEREO pipeline — **Search**, **Prepare**,
and **Execute** — and the stage model that runs inside each extraction task.

---

## High-level flow

```text
User Query / Config
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SEARCH                                                                   │
│    Input:  search function                                                  │
│    Output: GeoDataFrame[AssetSchema]                                        │
│    ──────────────────────────────────────────────────────────────────────── │
│    id | collection | geometry | start_time | end_time | href                │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. PREPARE TASKS                                                            │
│    Input:  search_results + ExtractionJob + task_builder                    │
│    Output: Sequence[ExtractionTask]                                         │
│    ──────────────────────────────────────────────────────────────────────── │
│    task.id          → stable task identifier                                │
│    task.assets      → GeoDataFrame[AssetSchema]                             │
│    task.job         → parent ExtractionJob (read/write/reproject/...)       │
│    task.grid_cells  → explicit MajorTOM grid cells for this task (optional) │
│    task.task_context→ metadata such as chunk_id, total_chunks               │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. EXECUTE TASKS                                                            │
│    Input:  tasks + Executor                                                 │
│    Output: GeoDataFrame[ArtifactSchema]                                     │
│    ──────────────────────────────────────────────────────────────────────── │
│    Per task: read → preprocess → reproject → postprocess → write            │
│    The orchestrator builds grid cells, splits time, writes files, and       │
│    emits one ArtifactSchema row per intersecting grid cell.                 │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ EOIDS on disk                                                               │
│ job-<name>/date-<YYYYMMDD>/collection-..._loc-..._start-..._end-..._       │
│   variable-..._res-...m_job-...tif                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Search

### Purpose

Find satellite granules across one or more collections that intersect a given
AOI and time range. The search function is responsible for the catalog query;
`ExtractionJob.search()` simply invokes it and validates the result.

### Sequence diagram

```text
┌─────────┐          ┌───────────────┐              ┌─────────────────────┐
│  User   │          │  ExtractionJob│              │  search function    │
│         │          │               │              │  (plugin)           │
└────┬────┘          └───────┬───────┘              └──────────┬──────────┘
     │                       │                                 │
     │  job.search(search_fn)│                                 │
     │──────────────────────▶│                                 │
     │                       │─── 1. Merge AOI / kwargs ──────▶│
     │                       │                                 │
     │                       │◀── 2. GeoDataFrame results ─────│
     │                       │                                 │
     │                       │─── 3. Validate against          │
     │                       │     AssetSchema                 │
     │◀──────────────────────│  GeoDataFrame[AssetSchema]      │
     │                       │                                 │
```

### API

```python
from datetime import datetime, timezone
from aereo.builtins import search_stac
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
results = job.search(
    search_stac,
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc),
)
```

Runtime search arguments win over the job's fixed `target_aoi`.

### Output schema: `AssetSchema`

Validated `GeoDataFrame` with these columns:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `str` | No | Unique granule/asset identifier. |
| `collection` | `str` | No | Collection this asset belongs to. |
| `geometry` | `geometry` | Yes | Satellite swath footprint. |
| `start_time` | `datetime` | No | Acquisition start time. |
| `end_time` | `datetime` | No | Acquisition end time. |
| `href` | `str` | No | Download URL or data reference. |

---

## Phase 2: Prepare tasks

### Purpose

Transform search results into a batch of `ExtractionTask` objects. AEREO's
default task builder groups assets by `start_time` and native CRS so that each
task can be read and written as a single coherent unit.

Grid cells are no longer attached to tasks. The orchestrator builds the MajorTOM
grid at execution time and uses it only for artifact indexing (and for
`reproject_mode="grid"`).

### Sequence diagram

```text
┌─────────────────┐          ┌───────────────┐              ┌─────────────────────┐
│  GeoDataFrame   │          │  ExtractionJob│              │  task builder       │
│ [AssetSchema]   │          │               │              │  function           │
└────────┬────────┘          └───────┬───────┘              └──────────┬──────────┘
         │                           │                                 │
         │  job.build_tasks(         │                                 │
         │    assets,                │                                 │
         │    build_grouped_tasks)   │                                 │
         │──────────────────────────▶│                                 │
         │                           │                                 │
         │                           │─── 1. Resolve effective AOI     │
         │                           │     (target_aoi)                │
         │                           │                                 │
         │                           │─── 2. Group assets by           │
         │                           │     start_time / crs ──────────▶│
         │                           │                                 │
         │                           │─── 3. Chunk into tasks ────────▶│
         │                           │     (cells_per_task)            │
         │                           │                                 │
         │◀──────────────────────────│  Sequence[ExtractionTask]       │
         │                           │                                 │
```

### API

```python
from aereo.builtins import build_grouped_tasks

tasks = job.build_tasks(
    results,
    build_grouped_tasks,
    cells_per_task=50,
)
```

`build_tasks()` always receives a complete ``ExtractionJob``. Construct one
in Python or load it from a Hydra config package:

```python
from aereo.pipeline import ExtractionJob
from aereo.builtins import read_odc_stac, write_geotiff

job = ExtractionJob(
    grid_dist=10_000,
    output_uri="/tmp/out",
    read=read_odc_stac,
    write=write_geotiff,
)

tasks = job.build_tasks(
    results,
    build_grouped_tasks,
    cells_per_task=50,
)
```

### Output: `Sequence[ExtractionTask]`

Each `ExtractionTask` contains:

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Stable task identifier generated by the builder. |
| `assets` | `GeoDataFrame[AssetSchema]` | The granule batch this task will process. |
| `job` | `ExtractionJob` | Parent job owning `read`, `write`, `reproject`, etc. |
| `grid_cells` | `Sequence[GridCell] \| None` | Explicit MajorTOM grid cells for this task; when present, the executor uses them directly instead of rediscovering them from the AOI. |
| `task_context` | `dict[str, Any]` | Metadata such as `chunk_id`, `total_chunks`, `start_time`. |

The task also exposes delegated read-only properties for convenience:

| Property | Type | Description |
|----------|------|-------------|
| `read` | `Reader` | Reader callable delegated from `job`. |
| `write` | `Writer \| None` | Writer callable delegated from `job`. |
| `output_uri` | `str` | Destination path or URI for artifacts. |
| `grid_dist` | `int` | Grid cell size in metres for this run. |

---

## Phase 3: Execute tasks

### Purpose

Run every `ExtractionTask` through a configurable executor. The orchestrator
`run_task` runs the fixed step pipeline and builds the artifact catalog.

### Stage pipeline

```text
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ read fn     │───▶ │ preprocess fn   │───▶ │ reproject fn    │───┐
└─────────────┘     └─────────────────┘     └─────────────────┘   │
                                                                  ▼
┌─────────────────┐     ┌─────────────────┐
│ write fn        │◀────│ postprocess fn  │
└─────────────────┘     └─────────────────┘
```

| Stage | Responsibility |
|-------|----------------|
| **Reader** | Open the source assets and return an `xr.Dataset`. |
| **Preprocessor** | Optional transform before reprojection (band selection, masking, indices). |
| **Reprojector** | Optional warp to a target CRS/resolution or to each grid cell's geobox. |
| **Postprocessor** | Optional transform after reprojection (scaling, renaming, composites). |
| **Writer** | Persist the final dataset to a path constructed by the orchestrator. |

The reader receives only the filename list derived from `task.assets["href"]`.
Processors and reprojectors receive only the `xr.Dataset`. The writer receives
the dataset and the fully constructed output path. No plugin receives the full
`ExtractionTask`.

### Reprojection modes

`ExtractionJob.reproject_mode` controls how the optional reprojector is used:

| Mode | Behaviour |
|------|-----------|
| `None` | No reprojection; the dataset is written in its native projection. |
| `"raw"` | Reproject the whole dataset once, write one file, intersect the file footprint with the grid. |
| `"grid"` | Iterate over intersecting grid cells, inject `geobox` into each reproject call, write one file per cell. |

### API

```python
from aereo.executors import LocalExecutor

artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))
```

The default executor is `LocalExecutor()` (sequential). The resulting
`GeoDataFrame` can be written to a catalog with `job.write_catalog(artifacts)`.

### Output schema: `ArtifactSchema`

Validated `GeoDataFrame` with these additional columns:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `str` | No | Unique artifact identifier. |
| `source_ids` | `str` | No | Comma-separated source granule IDs. |
| `start_time` | `datetime` | Yes | Acquisition start time. |
| `end_time` | `datetime` | Yes | Acquisition end time. |
| `uri` | `str` | No | Absolute path to the extracted GeoTIFF. |
| `geometry` | `geometry` | No | Spatial footprint of the extracted tile. |
| `collection` | `str` | Yes | Collection identifier. |
| `grid_cell` | `str` | No | Cell ID (e.g., `17D20L`). |
| `grid_dist` | `int` | No | Cell size in metres. |
| `cell_geometry` | `geometry` | No | Cell polygon in WGS84. |
| `cell_utm_crs` | `str` | No | UTM EPSG code. |
| `cell_utm_footprint` | `geometry` | No | Cell polygon in UTM. |

A raw extraction that spans many grid cells produces one artifact row per
intersecting cell, all pointing to the same output file URI.

---

## Declarative `ExtractionJob` config

`ExtractionJob` bundles the whole pipeline into one Hydra-compatible Pydantic
model. Load it from a config package:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
    overrides=["grid_dist=grid_50km"],
)
```

Or write the same layout as a single YAML file. `grid_dist` is a concrete value,
so it does not need `_target_`; plugin stages selected by `read` and `write` do:

```yaml
name: sentinel2_demo
output_uri: /tmp/aereo_extraction
grid_dist: 10000
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
```

Search providers and task builders are **not** part of the job model; they are
supplied at runtime to `job.search()` and `job.build_tasks()`.

---

## Plugin discovery & registration

Plugins are discovered automatically via Python `entry_points` in the
`aereo.plugins` group. The `AereoRegistry` organizes them by stage:

```text
┌─────────────────────────────────────────┐
│           Python Entry Points           │
│         (group="aereo.plugins")         │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌─────────────┐ ┌───────────┐ ┌─────────────┐
│ Searcher    │ │ Reader    │ │ Reprojector │
│ function    │ │ function  │ │ function    │
└──────┬──────┘ └─────┬─────┘ └──────┬──────┘
       │              │              │
   ┌───┴───┐     ┌────┴────┐    ┌────┴────┐
   ▼       ▼     ▼         ▼    ▼         ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────────┐
│search│ │search│ │read  │ │read  │ │reproject_odc │
│_stac │ │_earth│ │_odc  │ │_satpy│ │reproject_    │
│      │ │access│ │_stac │ │      │ │satpy         │
└──────┘ └──────┘ └──────┘ └──────┘ └──────────────┘
```

Declare plugins in `pyproject.toml`:

```toml
[project.entry-points."aereo.plugins"]
my_searcher = "my_package.module:my_search_function"
my_reader = "my_package.module:my_reader_function"
my_writer = "my_package.module:my_writer_function"
```

---

## EOIDS output structure

Artifacts are written to disk following the **Earth Observation Imaging Data
Structure (EOIDS)** convention:

```text
<uri>/
  job-<job_name>/
    date-<YYYYMMDD>/
      collection-<collection>_loc-<cell_id>_start-<ISO>_end-<ISO>_variable-<variable>_res-<resolution>m_job-<job_name>.tif
```

This makes it trivial to:

- Filter by cell, date, collection, variable, or resolution.
- Feed into `mosaic_eoids_tiles()` for reprojection and merging.
- Load into ML pipelines where the filename itself carries metadata.
