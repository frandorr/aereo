# Core Concepts

AEREO is built around a small number of ideas. Understanding them makes every
tutorial and API page easier to follow.

## The big picture

```mermaid
flowchart LR
    A["Search provider"] --> B["Task builder"]
    B --> C["Executor"]
    C --> D["Artifacts + catalog"]
```

A typical AEREO program has three steps:

1. **Search** — find scenes/assets for a sensor, AOI, and time range.
2. **Prepare** — turn search results into `ExtractionTask` objects.
3. **Execute** — run each task and write grid-aligned outputs.

## ExtractionJob

An `ExtractionJob` is a validated bundle that describes *what* to extract and
*how* to write it. It is created from a Hydra config package or directly in
Python.

Key fields:

| Field | Meaning |
|---|---|
| `name` | Human-readable job name. |
| `grid_dist` | Major TOM grid cell size in metres. |
| `output_uri` | Local path or object-store URI for outputs. |
| `target_aoi` | AOI used to build the grid. |
| `read` | Function that opens assets into an `xr.Dataset`. |
| `write` | Function that serializes a dataset to disk or object store. |
| `preprocess` / `postprocess` | Optional processing functions. |
| `reproject` / `reproject_mode` | Optional reprojection logic. |

## ExtractionTask

An `ExtractionTask` is one unit of work. It carries:

- the assets to read,
- the grid cells to extract,
- a reference to the parent `ExtractionJob` (so it knows the read/write
  pipeline).

You usually do not create tasks by hand; `job.build_tasks(...)` does it for
you.

## Per-task pipeline

Inside the executor, every task runs the same fixed pipeline:

```mermaid
flowchart LR
    read["read"] --> preprocess["preprocess"]
    preprocess --> reproject["reproject"]
    reproject --> postprocess["postprocess"]
    postprocess --> write["write"]
```

- **read** — open the source assets (e.g. `read_odc_stac`).
- **preprocess** — select bands, apply QA masks, etc.
- **reproject** — warp to a target CRS/geobox.
- **postprocess** — compute indices like NDVI/NDWI, normalize, composite.
- **write** — serialize each time slice (e.g. `write_geotiff`).

Any stage can be omitted by not passing a function for it.

## Plugins are plain functions

AEREO discovers plugins through the `aereo.plugins` entry-point group. The
prefix of the entry-point name determines the stage:

| Prefix | Stage | Example |
|---|---|---|
| `search_` | Search provider | `search_stac` |
| `task_builder_` | Task builder | `build_grouped_tasks` |
| `read_` | Reader | `read_odc_stac` |
| `reproject_` | Reprojector | `reproject_odc` |
| `process_` | Processor | `ndvi`, `qa_mask` |
| `write_` | Writer | `write_geotiff` |

A plugin is just a Python function with a typed signature, usually decorated
with Pydantic's `@validate_call`. You do not need to subclass anything.

## Grid alignment

AEREO uses the [Major TOM grid](https://github.com/majortom-eg) to tile the
AOI. Every output artifact is indexed against this grid, which means outputs
from different sensors can be stacked by grid cell ID.

Learn more in the [Grids](../user-guide/grids.md) guide.

## Artifact catalog

After extraction, `job.write_catalog(artifacts)` writes a `GeoDataFrame` with
one row per artifact. The catalog is stored as `artifacts.parquet` under the
job's `output_uri` and is the starting point for ML training pipelines.

## Next steps

- [User Guide: Choosing a Sensor](../user-guide/choosing-a-sensor.md)
- [User Guide: Search](../user-guide/search.md)
- [Plugins Overview](../plugins/overview.md)
