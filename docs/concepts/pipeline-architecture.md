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
│    Input:  search_results + ExtractionJob + patch_config                    │
│    Output: Sequence[ExtractionTask]                                         │
│    ──────────────────────────────────────────────────────────────────────── │
│    task.assets      → GeoDataFrame[AssetSchema]                             │
│    task.read        → reader callable (delegated from job)                  │
│    task.write       → writer callable (delegated from job)                  │
│    task.patches     → Sequence[ExtractionPatch] (UTM cells)                 │
│    task.output_uri  → destination path                                      │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. EXECUTE TASKS                                                            │
│    Input:  tasks + Executor                                                 │
│    Output: GeoDataFrame[ArtifactSchema]                                     │
│    ──────────────────────────────────────────────────────────────────────── │
│    Per task: read function → write function (per patch)                     │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ EOIDS on disk                                                               │
│ loc-<cell>/date-<YYYYMMDD>/profile-<name>/collection-<col>/variable-<var>/  │
│   collection-..._loc-..._start-..._end-..._variable-..._res-...m_job-...tif
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

Transform search results into a batch of `ExtractionTask` objects. AEREO builds
a grid over the effective AOI, filters cells by asset geometry, and chunks them
into parallelizable units.

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
         │                           │─── 2. Build grid cells ────────▶│
         │                           │     (GridDefinition over AOI)   │
         │                           │                                 │
         │                           │─── 3. Filter cells by swath ───▶│
         │                           │     (keep cells touching the    │
         │                           │      asset geometry)            │
         │                           │                                 │
         │                           │─── 4. Chunk into tasks ────────▶│
         │                           │     (cells_per_task)            │
         │                           │                                 │
         │◀──────────────────────────│  Sequence[ExtractionTask]       │
         │                           │                                 │
```

### API

```python
from aereo.builtins import build_grouped_tasks
from aereo.interfaces import PatchConfig

tasks = job.build_tasks(
    results,
    build_grouped_tasks,
    patch_config=PatchConfig(resolution=10.0),
    cells_per_task=50,
)
```

`build_tasks()` always receives a complete ``ExtractionJob``. Construct one
in Python or load it from a Hydra config package:

```python
from aereo.pipeline import ExtractionJob
from aereo.interfaces import PatchConfig
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
    patch_config=PatchConfig(resolution=10.0),
    cells_per_task=50,
)
```

### Output: `Sequence[ExtractionTask]`

Each `ExtractionTask` contains:

| Attribute | Type | Description |
|-----------|------|-------------|
| `assets` | `GeoDataFrame[AssetSchema]` | The granule batch this task will process. |
| `patches` | `Sequence[ExtractionPatch]` | Spatial patches this task covers. |
| `job` | `ExtractionJob` | Parent job owning `read`, `write`, `output_uri`, and `grid_dist`. |
| `read` | `Reader` | Reader callable delegated from `job`. |
| `write` | `Writer \| None` | Writer callable delegated from `job`. |
| `output_uri` | `str` | Destination path or URI for artifacts. |
| `grid_dist` | `int` | Grid cell size in metres for this run. |
| `aoi` | `BaseGeometry \| None` | Clipping geometry used during preparation. |
| `task_context` | `Mapping[str, Any]` | Metadata such as `chunk_id`, `total_chunks`, `start_time`. |

---

## Phase 3: Execute tasks

### Purpose

Run every `ExtractionTask` through a configurable executor. Each task calls its
reader once and then calls its writer once per patch.

### Stage pipeline

```text
┌─────────────┐     ┌─────────────────┐
│ read fn     │───▶ │ write fn        │
└─────────────┘     └─────────────────┘
```

| Stage | Responsibility |
|-------|----------------|
| **Reader** | Open the source asset and return an `xr.Dataset`. |
| **Writer** | Write final artifacts to disk or object store in EOIDS layout, once per patch. |

The reader runs once per task; the writer runs once per patch. Both receive the
`ExtractionTask`; the writer also receives the dataset and the current patch.

### API

```python
from aereo.executors import LocalExecutor

artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))
```

The default executor is `LocalExecutor()` (sequential). The resulting
`GeoDataFrame` can be written to a catalog with `job.write_catalog(artifacts)`.

### Output schema: `ArtifactSchema`

Validated `GeoDataFrame` inheriting from `GridSchema`, with these additional
columns:

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
```

---

## EOIDS output structure

Artifacts are written to disk following the **Earth Observation Imaging Data
Structure (EOIDS)** convention:

```text
<uri>/
  loc-<cell_id>/
    date-<YYYYMMDD>/
      profile-<name>/
        collection-<collection>/
          variable-<variable>/
            collection-<collection>_loc-<cell_id>_start-<ISO>_end-<ISO>_variable-<variable>_res-<resolution>m_job-<job_name>.tif
```

This makes it trivial to:

- Filter by cell, date, profile, collection, variable, or resolution.
- Feed into `mosaic_eoids_tiles()` for reprojection and merging.
- Load into ML pipelines where the filename itself carries metadata.
