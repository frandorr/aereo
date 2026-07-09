# Config Package

AerEO uses [Hydra](https://hydra.cc) to load and compose extraction jobs from
plain YAML files. A **config package** is just a directory of YAML files, and
AerEO validates the composed result with the `ExtractionJob` Pydantic model.

The repo ships an example package at `examples/config`. Each sensor has a
single root YAML file where every step of the pipeline is defined.

## A plain YAML job

The simplest AerEO config is one self-contained YAML file. For example,
`examples/config/job_sentinel2.yaml`:

```yaml
# Helper variables that ExtractionJob ignores — used to keep the file DRY
target_bands: [red, nir]
aoi_path: config/aoi/chocon.geojson

# Job definition
name: sentinel2_sample
grid_dist: 10_000
grid_cells_margin: 10
target_aoi: ${aoi_path}
output_uri: /tmp/aereo_extraction
overwrite: false

# Pipeline steps
search:
  _target_: aereo.builtins.search_stac
  _partial_: true
  stac_api_url: "https://earth-search.aws.element84.com/v1"
  collections:
    sentinel-2-l2a: ${target_bands}
  intersects: ${aoi_path}
  start_datetime: "2024-01-01T00:00:00Z"
  end_datetime: "2024-01-10T23:59:59Z"

read:
  _partial_: true
  _target_: aereo.builtins.read.read_odc_stac

write:
  _target_: aereo.builtins.write.write_geotiff
```

Every pipeline step lives in the same file:

| Key | Purpose |
|---|---|
| `name`, `grid_dist`, `target_aoi`, `output_uri` | Job settings validated by `ExtractionJob`. |
| `search` | How to query the catalog. |
| `read` | How to open the matched assets into an `xr.Dataset`. |
| `preprocess` / `postprocess` | Optional processors (NDVI, QA mask, etc.). |
| `reproject` / `reproject_mode` | Optional reprojection to a target CRS or grid cell. |
| `write` | How to serialize the result. |
| `task_builder` | How search results become `ExtractionTask` objects. |

Helper variables such as `target_bands` or `aoi_path` are ignored by
`ExtractionJob`. They are only there to avoid repeating values.

## `_target_` and `_partial_`

Hydra instantiates YAML blocks that contain `_target_`. For function targets,
AerEO needs Hydra to return a *bound callable*, not the result of calling the
function. This is done with `_partial_: true`:

```yaml
read:
  _target_: aereo.builtins.read.read_odc_stac
  _partial_: true
```

If you omit `_partial_`, `ExtractionJob.load_from_config` injects it
automatically, so the config still works. Being explicit is recommended.

Extra keys at the same level become keyword arguments bound to the callable:

```yaml
reproject:
  _target_: aereo.builtins.reproject.reproject_odc
  _partial_: true
  crs: EPSG:32633
  resolution: 10.0
```

## Loading a config in Python

`ExtractionJob.load_from_config` is the shortest path from a config package to a
validated job:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)

print(job.name)
print(job.output_uri)
print(job.grid_dist)
print(job.read)
print(job.write)
```

When `search` and `task_builder` are defined in the YAML, you can run the full
pipeline with no extra imports:

```python
from aereo.executors import LocalExecutor

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

assets = job.search()
tasks = job.build_tasks(assets)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))
job.write_catalog(artifacts)
```

You can still pass search providers and task builders explicitly, which is
useful for sharing them across jobs or overriding config values at runtime. Use
[`load_plugin`](yaml-schema.md#loading-individual-plugins) for the shortest path.

## Optional Hydra composition

Because the config is a Hydra package, you can compose YAML files with
`defaults:`. For example, `examples/config/job_sentinel2-ndvi.yaml` reuses the
base Sentinel-2 job and adds a `preprocess` stage:

```yaml
defaults:
  - job_sentinel2
  - _self_

name: sentinel2_ndvi
preprocess:
  - _target_: aereo.builtins.ndvi
    _partial_: true
    ndvi_nir_band: nir
    ndvi_red_band: red
```

You can also split common choices into config groups (`search/`, `read/`,
`write/`, `grid_dist/`) and select them with Hydra overrides. But this is
optional: a single root YAML file with every step defined is enough for most
jobs.

## Next steps

- [YAML Schema](yaml-schema.md) — every `ExtractionJob` field explained.
- [Hydra Overrides](overrides.md) — override values from Python.
- [Pure Python Quickstart](../getting-started/pure-python.md) — run a job without writing YAML.
