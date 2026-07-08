# AerEO Examples

This directory contains runnable examples for the AerEO satellite data
extraction framework.

## Structure

```text
examples/
├── *.ipynb                 # Jupyter notebooks (one per sensor / workflow)
└── config/                 # Hydra config package (job YAMLs and AOI GeoJSON)
```

## Quickstart

The recommended entry point is the Sentinel-2 notebook:

```bash
cd examples
jupyter lab 01-sentinel2.ipynb
```

This notebook demonstrates the full **search → prepare → extract** pipeline
using the Hydra config package in `examples/config`.

## Configuration

All pipeline configurations live under `examples/config` and use the Hydra
`_target_` convention for declarative instantiation:

```yaml
# examples/config/job_sentinel2.yaml
name: sentinel2_demo
grid_dist: 10000
output_uri: ./out
resolution: 10.0
margin: 0.0
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
```

Load the full job from the config package:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)
```

Or load a single YAML file:

```python
job = ExtractionJob.from_yaml("my_job.yaml")
```

## CLI

Run the same pipeline from the command line with the `aereo` CLI. See the
[CLI guide](https://frandorr.github.io/aereo/user-guide/cli/) for the full
command reference and current Hydra override syntax.

```bash
# List installed plugins
aereo action=plugins

# Show parameters for a plugin
aereo action=plugin_params plugin=search_stac
```

## Notebooks

| Notebook | Sensor | Description |
|----------|--------|-------------|
| `01-sentinel2.ipynb` | Sentinel-2 MSI | `red` and `nir` extraction from Earth Search |
| `01b-sentinel2-ndvi.ipynb` | Sentinel-2 MSI | NDVI processing example |
| `01c-sentinel2-ndwi.ipynb` | Sentinel-2 MSI | NDWI processing example |
| `step_by_step_raw.ipynb` | Sentinel-2 MSI | Sentinel-2 pipeline built entirely from raw Python functions and parameters — no config files or Hydra |
| `02-viirs.ipynb` | VIIRS | Earthaccess search + Satpy read |
| `03-sentinel3.ipynb` | Sentinel-3 OLCI | Earthaccess search + Satpy read |
| `03b-sentinel3-ndvi.ipynb` | Sentinel-3 OLCI | NDVI processing example |
| `04-tessera.ipynb` | GeoTessera | Tessera tile search and extraction |
| `05-goes19.ipynb` | GOES-19 ABI | Public AWS S3 search + Satpy read |
| `06-multiple-constellation.ipynb` | Sentinel-2 + VIIRS | Search and extract multiple sensors with a shared cache |

## Shared data

| File | Description |
|---|---|
| `config/aoi/chocon.geojson` | AOI polygon — Chocón reservoir, Argentina |
| `config/aoi/cordoba.geojson` | AOI polygon — Córdoba, Argentina |
| `config/aoi/oxford.geojson` | AOI polygon — Oxford, UK |
| `config/aoi/sample.geojson` | Sample AOI |
