# AEREO Config Package Example

This directory demonstrates the Hydra config-package layout enabled by the flat
``ExtractionJob`` schema:

```
.
├── main_config.yaml
├── aoi/
│   └── sample.geojson
├── search/
│   └── default.yaml
├── grid_config/
│   └── grid_10km.yaml
├── patch_config/
│   ├── base.yaml
│   └── high_res.yaml
├── task_builder/
│   └── grouped.yaml
└── extract/
    ├── sentinel2.yaml
    ├── viirs.yaml
    └── goes.yaml
```

`grid_config` and `patch_config` are concrete Pydantic models, so their YAML
files only need the field values; ``_target_`` is optional. ``_target_`` is
required for plugin/config groups that select an implementation, such as
``extract.read``, ``extract.reproject``, ``extract.write``, and the runtime
``search`` and ``task_builder`` configs.

Top-level keys (``grid_config``, ``patch_config``, ``output_uri``, ``extract``)
are first-class citizens of the job config, so they can be swapped
independently via Hydra ``defaults`` composition. ``search`` and
``task_builder`` are *runtime* plugins and are not stored on ``ExtractionJob``.

## Usage

The easiest way to consume the job part of a config package is through
``ExtractionJob.load_from_config``. It wraps Hydra composition and Pydantic
validation in one call:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)

print(job.output_uri)
print(job.grid_config.target_grid_dist)
print(job.patch_config.resolution)
print(job.effective_target_aoi)
```

Override configuration values with Hydra-style overrides:

```python
job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
    overrides=["patch_config=high_res"],
)
```

Because search providers and task builders are supplied at runtime, load them
separately and pass them to the job orchestration methods:

```python
import hydra
from aereo.builtins import GroupedTaskBuilder, SearchSTAC
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

# Option A: instantiate plugins directly
search_provider = SearchSTAC(
    stac_api_url="https://planetarycomputer.microsoft.com/api/stac/v1",
    collections={"sentinel-2-l2a": ["B04"]},
    intersects="examples/config/aoi/sample.geojson",
)
task_builder = GroupedTaskBuilder(cells_per_task=20)

# Option B: load them from the same config package
from omegaconf import OmegaConf
search_cfg = OmegaConf.load("examples/config/search/sentinel2_pc.yaml")
search_provider = hydra.utils.instantiate(search_cfg, _convert_="all")

# Run the pipeline
assets = job.search(search_provider)
tasks = job.build_tasks(assets, task_builder)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=4))
job.write_catalog(artifacts)
```

If you need full control over Hydra, you can still compose and instantiate
manually. Just make sure the dict you pass to ``ExtractionJob`` contains only
job fields:

```python
from hydra import initialize_config_dir, compose
from pathlib import Path
import hydra
from aereo.pipeline import ExtractionJob

config_dir = str(Path("examples/config").resolve())
with initialize_config_dir(version_base=None, config_dir=config_dir):
    cfg = compose(config_name="job_sentinel2")
    instantiated = hydra.utils.instantiate(cfg, _convert_="all")
    # Remove runtime plugin keys before validating the job model
    instantiated.pop("search", None)
    instantiated.pop("task_builder", None)
    job = ExtractionJob.model_validate(instantiated)
```

## Passing an AOI geometry

The top-level ``target_aoi`` key accepts a Shapely geometry, a GeoJSON dict,
or a path to a GeoJSON file. ``target_aoi`` is the AOI used to clip prepared
extraction tasks.

In a config package you can point to an AOI file with an override:

```python
aoi_path = str(Path("examples/config/aoi/sample.geojson").resolve())
job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
    overrides=[f"target_aoi={aoi_path}"],
)
```

Or in a single-file ``ExtractionJob`` YAML:

```yaml
name: sentinel2_demo
grid_config:
  target_grid_dist: 10000
  grid_filter_mode: intersection
patch_config:
  resolution: 10.0
  padding: 0
output_uri: /tmp/aereo_extraction
target_aoi: /absolute/path/to/aoi.geojson
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
    ...
  preprocess:
    - _target_: aereo.builtins.processor.CloudMask
      ...
  reproject:
    _target_: aereo.builtins.reproject.ReprojectToPatches
    ...
  postprocess:
    - _target_: aereo.builtins.processor.NDVI
      ...
  write:
    _target_: aereo.builtins.write.WriteGeoTIFF
      ...
```

Relative paths are resolved against the current working directory of the
process, so absolute paths are recommended in composed configs.

## Direct load

You can also point ``ExtractionJob.from_yaml`` at a fully-resolved YAML file
that follows the same flat structure:

```yaml
name: sentinel2_demo
grid_config:
  target_grid_dist: 10000
patch_config:
  resolution: 10.0
output_uri: /tmp/aereo_extraction
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
    ...
```

The ``output_uri`` can be a local path or an object-store URI such as
``s3://bucket/prefix``.

## Run the full pipeline

See ``run_job.py`` in this directory for a complete example that loads the job,
search provider, and task builder from the config package and executes the
pipeline with ``ExtractionJob.search``, ``ExtractionJob.build_tasks``, and
``ExtractionJob.execute``.
