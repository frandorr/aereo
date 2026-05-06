# AER Pipeline Architecture

This document describes the three-phase AER pipeline — **Search**, **Prepare**, and **Extract** — with UML-like diagrams, input/output schemas, and the exact parameters each phase accepts and produces.

---

## High-Level Flow

```
┌─────────────┐     ┌─────────────────────────┐     ┌─────────────────┐     ┌──────────────┐
│   User      │────▶│   1. search()           │────▶│ 2. prepare_for_ │────▶│ 3. extract_  │
│  Query      │     │   (AerClient)           │     │    extraction() │     │   batches()  │
└─────────────┘     └─────────────────────────┘     └─────────────────┘     └──────────────┘
                              │                              │                       │
                              ▼                              ▼                       ▼
                    ┌─────────────────┐            ┌─────────────────┐      ┌─────────────────┐
                    │ GeoDataFrame    │            │ Sequence[       │      │ GeoDataFrame    │
                    │ [AssetSchema]   │            │  ExtractionTask]│      │ [ArtifactSchema]│
                    └─────────────────┘            └─────────────────┘      └─────────────────┘
```

---

## Phase 1: Search

### Purpose
Find satellite granules across one or more collections that intersect a given AOI and time range. AER fans out the query to registered **SearchProvider** plugins in parallel.

### Sequence Diagram

```
┌─────────┐          ┌─────────────┐              ┌─────────────────────┐
│  User   │          │  AerClient  │              │  SearchProvider     │
│         │          │             │              │  (plugin)           │
└────┬────┘          └──────┬──────┘              └──────────┬──────────┘
     │                      │                                │
     │  search(collections, │                                │
     │         intersects,  │                                │
     │         start, end)  │                                │
     │────────────────────▶│                                │
     │                      │                                │
     │                      │─── 1. Resolve plugins ─────────▶│
     │                      │    (registry lookup per        │
     │                      │     collection)                │
     │                      │                                │
     │                      │─── 2. Group by (plugin, params)│
     │                      │                                │
     │                      │─── 3. ThreadPoolExecutor ──────▶│
     │                      │    (parallel fan-out)          │
     │                      │                                │
     │                      │◀── 4. GeoDataFrame results ────│
     │                      │                                │
     │                      │─── 5. Validate & concat ───────▶│
     │                      │                                │
     │◀─────────────────────│  GeoDataFrame[AssetSchema]     │
     │                      │                                │
```

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collections` | `Sequence[str]` | Yes | Collection identifiers to search (e.g. `["MOD021KM", "VJ202IMG"]`). |
| `intersects` | `BaseGeometry \| dict \| None` | No | Spatial filter. Shapely geometry or GeoJSON dict. |
| `start_datetime` | `datetime \| None` | No | Temporal start (UTC). |
| `end_datetime` | `datetime \| None` | No | Temporal end (UTC). |
| `search_params` | `Mapping[str, Any] \| None` | No | Per-collection or global params forwarded to the search plugin. Collection names as top-level keys trigger per-collection overrides. |
| `init_params` | `Mapping[str, Any] \| None` | No | Constructor kwargs for plugin instantiation. Same override rules as `search_params`. |
| `plugin_hints` | `Mapping[str, str \| Sequence[str]] \| None` | No | Force a plugin for a collection. Two formats: `{"collection": "plugin"}` or inverted `{"plugin": ["collection"]}` |
| `failure_mode` | `FailureMode` | No | `STRICT` (raise on any failure) or `BEST_EFFORT` (log and continue). Default: `BEST_EFFORT`. |

### Output Schema: `AssetSchema`

Validated `GeoDataFrame` with these columns:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `str` | No | Unique granule/asset identifier. |
| `collection` | `str` | No | Collection this asset belongs to. |
| `geometry` | `geometry` | Yes | Actual satellite swath footprint (not just bounding box). |
| `start_time` | `datetime` | No | Acquisition start time. |
| `end_time` | `datetime` | No | Acquisition end time. |
| `href` | `str` | No | Download URL or reference to the data source. |

---

## Phase 2: Prepare for Extraction

### Purpose
Transform search results into a batch of `ExtractionTask` objects. Groups assets by profile and start time, generates grid cells over the AOI, optionally filters them by swath coverage, and chunks into parallelizable units.

### Sequence Diagram

```
┌─────────────────┐          ┌─────────────┐              ┌─────────────────────┐
│  GeoDataFrame   │          │  AerClient  │              │  Extractor          │
│ [AssetSchema]   │          │             │              │  (plugin)           │
└────────┬────────┘          └──────┬──────┘              └──────────┬──────────┘
         │                          │                                │
         │  prepare_for_extraction( │                                │
         │    search_results,       │                                │
         │    profiles,             │                                │
         │    target_aoi)           │                                │
         │─────────────────────────▶│                                │
         │                          │                                │
         │                          │─── 1. Resolve extractor ──────▶│
         │                          │    (single plugin for all      │
         │                          │     collections)               │
         │                          │                                │
         │                          │─── 2. Filter assets per profile │
         │                          │    (collection_variables_map)  │
         │                          │                                │
         │                          │─── 3. Group by start_time ────▶│
         │                          │                                │
         │                          │─── 4. Generate grid cells ────▶│
         │                          │    (GridDefinition over AOI)   │
         │                          │                                │
         │                          │─── 5. Filter cells by swath ──▶│
         │                          │    (intersection/within/       │
         │                          │     coverage)                  │
         │                          │                                │
         │                          │─── 6. Chunk into tasks ───────▶│
         │                          │    (cells_per_chunk)           │
         │                          │                                │
         │◀─────────────────────────│  Sequence[ExtractionTask]      │
         │                          │                                │
```

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `search_results` | `GeoDataFrame[AssetSchema]` | Yes | Output from `search()`. |
| `target_aoi` | `BaseGeometry \| dict \| None` | No | AOI to clip grid generation. If `None`, uses the union of all asset geometries. |
| `profiles` | `Sequence[ExtractionProfile]` | Yes** | Blueprints for extraction. **Required** if `resolution` is not provided. |
| `resolution` | `float \| None` | Yes** | Fallback target resolution (creates a default profile). **Required** if `profiles` is not provided. |
| `uri` | `str \| None` | No | Base output directory or URI prefix for artifacts. |
| `prepare_params` | `Mapping[str, Any] \| None` | No | Params forwarded to the extractor's `prepare_for_extraction`. Common keys: `cells_per_chunk`, `grid_filter_mode`, `min_coverage`. |
| `init_params` | `Mapping[str, Any] \| None` | No | Constructor kwargs for extractor instantiation. Same override rules as in `search`. |
| `plugin_hints` | `Mapping[str, str \| Sequence[str]] \| None` | No | Force extractor plugin. Same format as search hints. |
| `target_grid_dist` | `int \| None` | No | Override grid cell size in metres (default: extractor's `target_grid_d`). |
| `target_grid_overlap` | `bool \| None` | No | Override grid overlap setting (default: extractor's `target_grid_overlap`). |

### Output: `Sequence[ExtractionTask]`

Each `ExtractionTask` (from `aer.interfaces.core`) contains:

| Attribute | Type | Description |
|-----------|------|-------------|
| `assets` | `GeoDataFrame[AssetSchema]` | The granule batch this task will extract. |
| `profile` | `ExtractionProfile` | Target bands, resolution, and extra params. |
| `uri` | `str` | Destination path for artifacts. |
| `grid_cells` | `Sequence[GridCell]` | Spatial cells this task covers. |
| `aoi` | `BaseGeometry \| None` | Clipping geometry used during preparation. |
| `prepare_params` | `Mapping[str, Any]` | Params that drove task construction (e.g. `chunk_id`, `cells_per_chunk`). |
| `task_context` | `Mapping[str, Any]` | Observability metadata: `chunk_id`, `total_chunks`, `start_time`. |

### `ExtractionProfile` Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Label for bookkeeping. |
| `resolution` | `float` | Target pixel size in metres. |
| `collection_variables_map` | `Mapping[str, Sequence[str]]` | Which bands/variables to extract per collection. |
| `extra_params` | `Mapping[str, Any]` | Plugin-specific settings (e.g. `{"reader": "abi_l1b"}`). |

---

## Phase 3: Extract Batches

### Purpose
Execute all `ExtractionTask` objects. Can run sequentially or in parallel via `ProcessPoolExecutor`. Each task is handed to the registered **Extractor** plugin, which downloads granules, resamples to the target grid, and writes GeoTIFFs in EOIDS format.

### Sequence Diagram

```
┌─────────────────────┐          ┌─────────────┐              ┌─────────────────────┐
│  Sequence[          │          │  AerClient  │              │  Extractor          │
│   ExtractionTask]   │          │             │              │  (plugin)           │
└──────────┬──────────┘          └──────┬──────┘              └──────────┬──────────┘
           │                            │                                │
           │  extract_batches(          │                                │
           │    tasks,                  │                                │
           │    extract_params)         │                                │
           │───────────────────────────▶│                                │
           │                            │                                │
           │                            │─── 1. Resolve extractor ──────▶│
           │                            │                                │
           │                            │─── 2. Sequential or Parallel ─▶│
           │                            │    (ProcessPoolExecutor if      │
           │                            │     max_batch_workers set)     │
           │                            │                                │
           │                            │◀── 3. Per-task GeoDataFrame ──│
           │                            │    [ArtifactSchema]            │
           │                            │                                │
           │                            │─── 4. Concat & validate ──────▶│
           │                            │                                │
           │◀───────────────────────────│  GeoDataFrame[ArtifactSchema]  │
           │                            │                                │
```

### Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extraction_task_batch` | `Sequence[ExtractionTask]` | Yes | Output from `prepare_for_extraction()`. |
| `extract_params` | `Mapping[str, Any] \| None` | No | Flat dict forwarded directly to the extractor plugin. Common keys: `padding`, `resampling`/`resampler`, `calibration`, `reader`, `downloader`, `satellite`. |
| `init_params` | `Mapping[str, Any] \| None` | No | Constructor kwargs for extractor instantiation. |
| `plugin_hints` | `Mapping[str, str \| Sequence[str]] \| None` | No | Force extractor plugin. |
| `failure_mode` | `FailureMode` | No | `STRICT` or `BEST_EFFORT`. Default: `STRICT` for extraction. |
| `max_batch_workers` | `int \| None` | No | Number of parallel processes. `None` = sequential. |

### Output Schema: `ArtifactSchema`

Validated `GeoDataFrame` inheriting from `GridSchema`, with these additional columns:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | `str` | No | Unique artifact identifier. |
| `source_ids` | `str` | No | Comma-separated list of source granule IDs that contributed. |
| `start_time` | `datetime` | Yes | Acquisition start time. |
| `end_time` | `datetime` | Yes | Acquisition end time. |
| `uri` | `str` | No | Absolute path to the extracted GeoTIFF. |
| `geometry` | `geometry` | No | Spatial footprint of the extracted tile. |
| `collection` | `str` | Yes | Collection identifier. |
| `grid_cell` | `str` | No | Cell ID (e.g. `17D20L`). Inherited from `GridSchema`. |
| `grid_dist` | `int` | No | Cell size in metres. Inherited from `GridSchema`. |
| `cell_geometry` | `geometry` | No | Cell polygon in WGS84. Inherited from `GridSchema`. |
| `cell_utm_crs` | `str` | No | UTM EPSG code. Inherited from `GridSchema`. |
| `cell_utm_footprint` | `geometry` | No | Cell polygon in UTM. Inherited from `GridSchema`. |

---

## EOIDS Output Structure

Artifacts are written to disk following the **Earth Observation Imaging Data Structure (EOIDS)** convention:

```
<uri>/
  loc-<cell_id>/
    date-<YYYYMMDD>/
      sat-<platform>/
        loc-<cell_id>_start-<ISO>_end-<ISO>_sat-<platform>_prod-<product>_band-<band>_res-<resolution>m.tif
```

This makes it trivial to:
- Filter by cell, date, satellite, band, or resolution.
- Feed into `mosaic_eoids_tiles()` for reprojection and merging.
- Load into ML pipelines where the filename itself carries metadata.

---

## Plugin Discovery & Registration

Plugins are discovered automatically via Python `entry_points(group="aer.plugins")`. Each plugin must inherit from `SearchProvider` or `Extractor` and declare `supported_collections`.

```
┌─────────────────────────────────────────┐
│           Python Entry Points           │
│         (group="aer.plugins")            │
└─────────────────────────────────────────┘
                    │
        ┌──────────┴──────────┐
        ▼                     ▼
┌───────────────┐     ┌───────────────┐
│ SearchProvider│     │  Extractor    │
│   (abstract)  │     │  (abstract)   │
└───────┬───────┘     └───────┬───────┘
        │                     │
   ┌────┴────┐           ┌────┴────┐
   ▼         ▼           ▼         ▼
┌──────┐ ┌──────┐   ┌──────┐ ┌──────────────┐
│search_│ │search│   │extract│ │extract_pc_   │
│earth- │ │_aws_ │   │_satpy│ │sentinel2     │
│access │ │goes  │   │      │ │              │
└──────┘ └──────┘   └──────┘ └──────────────┘
```

---

## Complete Pipeline Data Flow

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SEARCH                                                                   │
│    Input:  collections, intersects, start/end, plugin_hints, search_params │
│    Output: GeoDataFrame[AssetSchema]                                         │
│    ──────────────────────────────────────────────────────────────────────── │
│    id | collection | geometry | start_time | end_time | href               │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. PREPARE FOR EXTRACTION                                                   │
│    Input:  search_results, profiles, target_aoi, prepare_params, uri      │
│    Output: Sequence[ExtractionTask]                                         │
│    ──────────────────────────────────────────────────────────────────────── │
│    task.assets  → GeoDataFrame[AssetSchema]                                 │
│    task.profile → ExtractionProfile (bands, resolution, extra_params)       │
│    task.grid_cells → Sequence[GridCell] (with UTM CRS & area_def)           │
│    task.uri     → output path                                               │
│    task.task_context → {chunk_id, total_chunks, start_time}                 │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. EXTRACT BATCHES                                                          │
│    Input:  tasks, extract_params, max_batch_workers                         │
│    Output: GeoDataFrame[ArtifactSchema]                                     │
│    ──────────────────────────────────────────────────────────────────────── │
│    id | source_ids | start_time | end_time | uri | geometry | collection     │
│    grid_cell | grid_dist | cell_geometry | cell_utm_crs | cell_utm_footprint │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ EOIDS on Disk                                                               │
│ loc-<cell>/date-<YYYYMMDD>/sat-<platform>/loc-..._band-..._res-...m.tif     │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ OPTIONAL: mosaic_eoids_tiles(root_dir, target_crs='EPSG:4326')            │
│ Output: (mosaic: NDArray, transform: Affine, crs: CRS)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```
