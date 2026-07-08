# YAML Schema

Every AerEO job is validated against the `ExtractionJob` Pydantic model. This
page walks through the fields you will see in the YAML files, explains the Hydra
instantiation conventions, and links each stage to its input/output schema.

## Top-level job fields

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | Human-readable job name. |
| `grid_dist` | `int` | Major TOM grid cell size in metres. |
| `output_uri` | `str` | Local path or object-store URI for outputs (`s3://bucket/prefix`). |
| `overwrite` | `bool` | Whether to overwrite existing artifacts. Default: `false`. |
| `target_aoi` | `str` / `dict` / geometry | AOI used to build the grid. Accepts a GeoJSON file path, a GeoJSON dict, or a Shapely geometry. |
| `resolution` | `float \| None` | Target pixel size in metres. Used by grid builders and reprojectors. |
| `margin` | `float \| None` | Extra buffer around cells or scenes to avoid edge effects. |
| `crop_buffer` | `float \| None` | Buffer used when cropping scenes in grid-mode reprojection. |
| `grid_cells_margin` | `int \| float` | Additional margin used when intersecting cells with the AOI. |
| `alignment_resolution` | `float \| None` | Resolution used to align the grid. |
| `read` | `Reader` | Function that opens assets into an `xr.Dataset`. |
| `preprocess` | `Processor \| list[Processor]` | Optional function(s) run before reprojection. |
| `reproject` | `Reprojector` | Optional function that warps the dataset to a target CRS/geobox. |
| `reproject_mode` | `"raw" \| "grid" \| None` | How reprojection is applied. See [Reprojection](../user-guide/reprojection.md). |
| `postprocess` | `Processor \| list[Processor]` | Optional function(s) run after reprojection. |
| `write` | `Writer` | Function that serializes a dataset to disk or object store. |
| `search` / `search_provider` | `SearchProvider` | Search function. May also be passed at runtime. |
| `task_builder` | `TaskBuilder` | Function that turns search results into `ExtractionTask` objects. |

`ExtractionJob` uses `extra="forbid"`, so unknown top-level keys will raise a
validation error. Helper variables that should be ignored can be added freely;
`load_from_config` strips them before validation.

## `_target_` and `_partial_`

Hydra instantiates YAML blocks that contain `_target_`. For function targets,
AerEO needs Hydra to return a *bound callable*, not the result of calling the
function. This is done with `_partial_: true`:

```yaml
read:
  _target_: aereo.builtins.read.read_odc_stac
  _partial_: true
```

If you omit `_partial_`, `ExtractionJob.load_from_config` will inject it for you
so the config still works. Being explicit is recommended.

Extra keys at the same level become keyword arguments bound to the callable:

```yaml
reproject:
  _target_: aereo.builtins.reproject.reproject_odc
  _partial_: true
  crs: EPSG:32633
  resolution: 10.0
```

## Schemas for each stage

AerEO uses schemas to guarantee that plugins agree on the shape of data moving
between stages.

| Stage | Protocol | Input | Output |
|---|---|---|---|
| Search | `SearchProvider` | `collections`, `intersects`, time range | `GeoDataFrame[AssetSchema]` |
| Task builder | `TaskBuilder` | `GeoDataFrame[AssetSchema]`, `ExtractionJob` | `Sequence[ExtractionTask]` |
| Read | `Reader` | `ExtractionTask` | `xr.Dataset` |
| Preprocess | `Processor` | `xr.Dataset` | `xr.Dataset` |
| Reproject | `Reprojector` | `xr.Dataset` | `xr.Dataset` |
| Postprocess | `Processor` | `xr.Dataset` | `xr.Dataset` |
| Write | `Writer` | `xr.Dataset`, path | `str` (artifact path/URI) |

The catalog produced by `job.write_catalog(artifacts)` is a
`GeoDataFrame[ArtifactSchema]`. See [Outputs & Catalog](../user-guide/outputs.md)
for details.

## Loading individual plugins

Sometimes you want to load just a search provider or task builder from the
config package, not the whole job. Use `load_plugin`:

```python
from aereo.pipeline import ExtractionJob, load_plugin
from aereo.executors import LocalExecutor

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

search_provider = load_plugin("examples/config", "search", "sentinel2_pc")
task_builder = load_plugin("examples/config", "task_builder", "grouped")

assets = job.search(search_provider)
tasks = job.build_tasks(assets, task_builder)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))
job.write_catalog(artifacts)
```

`load_plugin(config_dir, group, name)` composes the single config group and
returns the instantiated callable.

## Single-file jobs

If you prefer one self-contained YAML file, use `ExtractionJob.from_yaml`:

```yaml
name: sentinel2_demo
grid_dist: 10_000
output_uri: /tmp/aereo_extraction
target_aoi: /absolute/path/to/aoi.geojson
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
```

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.from_yaml("/path/to/job.yaml")
```

Relative paths in `target_aoi` are resolved from the current working directory,
so absolute paths are recommended in composed configs.

## Next steps

- [Hydra Overrides](overrides.md) — change any value from Python.
- [Build a Plugin](../plugins/build-a-plugin.md) — write your own stage functions.
- [API: Pipeline](../api/pipeline.md) — `ExtractionJob` reference.
