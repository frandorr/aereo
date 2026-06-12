# AEREO Config Package Example

This directory demonstrates the Hydra config-package layout enabled by the
flat ``ExtractionJob`` schema:

```
.
├── main_config.yaml
├── search/
│   └── default.yaml
├── grid_config/
│   └── default.yaml
├── patch_config/
│   ├── base.yaml
│   └── high_res.yaml
└── extract/
    ├── sentinel2.yaml
    ├── viirs.yaml
    └── goes.yaml
```

Top-level keys (``grid_config``, ``patch_config``, ``output_uri``) are first-class
citizens of the job config, so they can be swapped independently via Hydra
``defaults`` composition.

## Usage

This config package is consumed through ``ExtractionJob.from_yaml`` or via the
Python API with Hydra composition. It is **not** the same schema as the AEREO
CLI config (which also includes ``action``, ``verbose``, etc.).

```python
from hydra import initialize_config_dir, compose
from aereo.pipeline import ExtractionJob
from pathlib import Path

config_dir = str(Path("examples/config_package").resolve())
with initialize_config_dir(version_base=None, config_dir=config_dir):
    cfg = compose(config_name="main_config")
    instantiated = hydra.utils.instantiate(cfg, _convert_="all")
    job = ExtractionJob.model_validate(instantiated)

print(job.output_uri)
print(job.grid_config.target_grid_dist)
print(job.patch_config.resolution)
```

Override the patch configuration on the command line:

```python
cfg = compose(config_name="main_config", overrides=["patch_config=high_res"])
```

## Direct load

You can also point ``ExtractionJob.from_yaml`` at a fully-resolved YAML file
that follows the same flat structure:

```yaml
grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 10000
patch_config:
  _target_: aereo.interfaces.PatchConfig
  resolution: 10.0
output_uri: /tmp/aereo_extraction
search:
  _target_: aereo.builtins.SearchSTAC
  ...
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  ...
```

The ``output_uri`` can be a local path or an object-store URI such as
``s3://bucket/prefix``.
