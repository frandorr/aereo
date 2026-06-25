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
│    Input:  SearchProvider                                                   │
│    Output: GeoDataFrame[AssetSchema]                                        │
│    ──────────────────────────────────────────────────────────────────────── │
│    id | collection | geometry | start_time | end_time | href                │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. PREPARE TASKS                                                            │
│    Input:  search_results + ExtractionJob (grid, patch, extract, output)    │
│    Output: Sequence[ExtractionTask]                                         │
│    ──────────────────────────────────────────────────────────────────────── │
│    task.assets      → GeoDataFrame[AssetSchema]                             │
│    task.extract     → ExtractConfig (reader / processors / reprojector /    │
│                       postprocessors / writer)                              │
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
│    Per task: Reader → Pre-processors → Reprojector → Post-processors →      │
│    Writer                                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ EOIDS on disk                                                               │
│ loc-<cell>/date-<YYYYMMDD>/profile-<name>/collection-<col>/variable-<var>/  │
│   loc-..._start-..._end-..._profile-..._collection-..._variable-..._res-...m.tif
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Search

### Purpose

Find satellite granules across one or more collections that intersect a given
AOI and time range. The `SearchProvider` is responsible for the catalog query;
`ExtractionJob.search()` simply invokes it and validates the result.

### Sequence diagram

```text
┌─────────┐          ┌───────────────┐              ┌─────────────────────┐
│  User   │          │  ExtractionJob│              │  SearchProvider     │
│         │          │               │              │  (plugin)           │
└────┬────┘          └───────┬───────┘              └──────────┬──────────┘
     │                       │                                 │
     │  job.search(provider) │                                 │
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
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
results = job.search(provider)
```

Runtime search arguments win over the job's fixed `target_aoi`:

```python
results = job.search(
    provider,
    aoi=geojson_dict,
    start_datetime=datetime(2024, 1, 1),
    end_datetime=datetime(2024, 2, 1),
)
```

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
│  GeoDataFrame   │          │  ExtractionJob│              │    Task builder     │
│ [AssetSchema]   │          │               │              │                     │
└────────┬────────┘          └───────┬───────┘              └──────────┬──────────┘
         │                           │                                 │
         │  job.build_tasks(         │                                 │
         │    assets,                │                                 │
         │    task_builder)          │                                 │
         │──────────────────────────▶│                                 │
         │                           │                                 │
         │                           │─── 1. Resolve effective AOI     │
         │                           │     (target_aoi)                │
         │                           │                                 │
         │                           │─── 2. Build grid cells ────────▶│
         │                           │     (GridDefinition over AOI)   │
         │                           │                                 │
         │                           │─── 3. Filter cells by swath ───▶│
         │                           │     (intersection/within/       │
         │                           │      coverage)                  │
         │                           │                                 │
         │                           │─── 4. Chunk into tasks ────────▶│
         │                           │     (cells_per_task)            │
         │                           │                                 │
         │◀──────────────────────────│  Sequence[ExtractionTask]       │
         │                           │                                 │
```

### API

```python
tasks = job.build_tasks(results, task_builder)
```

`build_tasks()` always receives a complete ``ExtractionJob``. Construct one
in Python or load it from a Hydra config package:

```python
from aereo.pipeline import ExtractionJob
from aereo.builtins import GroupedTaskBuilder

job = ExtractionJob(
    grid_config=grid_config,
    patch_config=patch_config,
    output_uri="/tmp/out",
    extract=extract_config,
)

tasks = job.build_tasks(
    results,
    GroupedTaskBuilder(),
    cells_per_task=50,
)
```

### Output: `Sequence[ExtractionTask]`

Each `ExtractionTask` contains:

| Attribute | Type | Description |
|-----------|------|-------------|
| `assets` | `GeoDataFrame[AssetSchema]` | The granule batch this task will process. |
| `patches` | `Sequence[ExtractionPatch]` | Spatial patches this task covers. |
| `job` | `ExtractionJob` | Parent job owning `extract`, `output_uri`, `grid_config`, and `patch_config`. |
| `extract` | `ExtractConfig` | Declarative configuration of extraction stages. |
| `output_uri` | `str` | Destination path or URI for artifacts. |
| `grid_config` | `GridConfig` | Tiling specification for this run. |
| `patch_config` | `PatchConfig` | ML physical patch dimensions. |
| `aoi` | `BaseGeometry \| None` | Clipping geometry used during preparation. |
| `task_context` | `Mapping[str, Any]` | Metadata such as `chunk_id`, `total_chunks`, `start_time`. |

---

## Phase 3: Execute tasks

### Purpose

Run every `ExtractionTask` through a configurable executor. Each task is handed
to a stage pipeline that reads data, optionally processes it, reprojects it to
the target grid, optionally processes it again, and writes the result.

### Stage pipeline

```text
┌────────┐     ┌─────────────────┐     ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│ Reader │───▶ │ Pre-processors  │───▶ │ Reprojector │───▶ │ Post-processors  │───▶ │ Writer      │
└────────┘     └─────────────────┘     └─────────────┘     └──────────────────┘     └─────────────┘
```

| Stage | Base class | Responsibility |
|-------|------------|----------------|
| **Reader** | `Reader` | Open the source asset and return an `xr.DataArray` or similar. |
| **Processors** | `Processor` | Transform data: select bands, compute NDVI, mask clouds, normalize, composite. |
| **Reprojector** | `Reprojector` | Reproject to the task's target grid / GeoBox. |
| **Writer** | `Writer` | Write final artifacts to disk or object store in EOIDS layout. |

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
    overrides=["patch_config=high_res"],
)
```

Or write the same layout as a single YAML file. `grid_config` and
`patch_config` are concrete Pydantic models, so they do not need `_target_`;
plugin stages inside `extract` do:

```yaml
name: sentinel2_demo
output_uri: /tmp/aereo_extraction
grid_config:
  target_grid_dist: 10000
patch_config:
  resolution: 10.0
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  reproject:
    _target_: aereo.builtins.ReprojectODC
  write:
    _target_: aereo.builtins.WriteGeoTIFF
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
│ SearchProvider│ │  Reader   │ │ Reprojector │
│  (abstract) │ │ (abstract)│ │  (abstract) │
└──────┬──────┘ └─────┬─────┘ └──────┬──────┘
       │              │              │
  ┌────┴────┐    ┌────┴────┐    ┌────┴────┐
  ▼         ▼    ▼         ▼    ▼         ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────────┐
│Search │ │Search│ │Read  │ │Read  │ │ReprojectODC  │
│STAC   │ │Earth-│ │ODC   │ │Satpy │ │ReprojectSatpy│
│       │ │access│ │STAC  │ │      │ │              │
└──────┘ └──────┘ └──────┘ └──────┘ └──────────────┘
```

Declare plugins in `pyproject.toml`:

```toml
[project.entry-points."aereo.plugins"]
my_searcher = "my_package.module:MySearchProvider"
my_reader = "my_package.module:MyReader"
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
            loc-<cell_id>_start-<ISO>_end-<ISO>_profile-<name>_collection-<collection>_variable-<variable>_res-<resolution>m.tif
```

This makes it trivial to:

- Filter by cell, date, profile, collection, variable, or resolution.
- Feed into `mosaic_eoids_tiles()` for reprojection and merging.
- Load into ML pipelines where the filename itself carries metadata.
