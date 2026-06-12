# AEREO Config Package Example

This directory demonstrates the Hydra config-package layout enabled by the
flat ``ExtractionJob`` schema:

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
└── extract/
    ├── sentinel2.yaml
    ├── viirs.yaml
    └── goes.yaml
```

`grid_config` and `patch_config` are concrete Pydantic models, so their YAML
files only need the field values; ``_target_`` is optional. ``_target_`` is
required for plugin/config groups that select an implementation, such as
``search``, ``extract.read``, ``extract.reproject``, and ``extract.write``.

Top-level keys (``grid_config``, ``patch_config``, ``output_uri``,
``target_aoi``) are first-class citizens of the job config, so they can be
swapped independently via Hydra ``defaults`` composition.

## Usage

The easiest way to consume a config package is through
``ExtractionJob.load_from_config``. It wraps Hydra composition, plugin
instantiation, and Pydantic validation in one call. It is **not** the same
schema as the AEREO CLI config (which also includes ``action``, ``verbose``,
etc.).

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="main_config",
)

print(job.output_uri)
print(job.grid_config.target_grid_dist)
print(job.patch_config.resolution)
print(job.effective_target_aoi)  # target_aoi or search.intersects
```

Override configuration values with Hydra-style overrides:

```python
job = ExtractionJob.load_from_config(
    "examples/config",
    overrides=["patch_config=high_res"],
)
```

If you need full control over Hydra, you can still compose and instantiate
manually:

```python
from hydra import initialize_config_dir, compose
from pathlib import Path
import hydra
from aereo.pipeline import ExtractionJob

config_dir = str(Path("examples/config").resolve())
with initialize_config_dir(version_base=None, config_dir=config_dir):
    cfg = compose(config_name="main_config")
    instantiated = hydra.utils.instantiate(cfg, _convert_="all")
    job = ExtractionJob.model_validate(instantiated)
```

## Passing an AOI geometry

Both ``SearchProvider.intersects`` and the top-level ``target_aoi`` key accept
a Shapely geometry, a GeoJSON dict, or a path to a GeoJSON file.
``target_aoi`` is the AOI used to clip prepared extraction tasks; when it is
omitted, ``ExtractionJob.effective_target_aoi`` automatically falls back to
``search.intersects``.

In a config package you can point to an AOI file with an override:

```python
aoi_path = str(Path("examples/config/aoi/sample.geojson").resolve())
cfg = compose(
    config_name="main_config",
    overrides=[f"target_aoi={aoi_path}"],
)
```

Or in a single-file ``ExtractionJob`` YAML:

```yaml
grid_config:
  target_grid_dist: 10000
patch_config:
  resolution: 10.0
output_uri: /tmp/aereo_extraction
target_aoi: /absolute/path/to/aoi.geojson
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04"]
  intersects: /absolute/path/to/aoi.geojson
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  ...
```

Relative paths are resolved against the current working directory of the
process, so absolute paths are recommended in composed configs.

## Direct load

You can also point ``ExtractionJob.from_yaml`` at a fully-resolved YAML file
that follows the same flat structure:

```yaml
grid_config:
  target_grid_dist: 10000
patch_config:
  resolution: 10.0
output_uri: /tmp/aereo_extraction
search:
  _target_: aereo.builtins.SearchSTAC
  intersects: /absolute/path/to/aoi.geojson
  ...
extract:
  read:
    _target_: aereo.builtins.ReadODCSTAC
  ...
```

The ``output_uri`` can be a local path or an object-store URI such as
``s3://bucket/prefix``.
