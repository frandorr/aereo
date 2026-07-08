# AerEO Examples

This directory contains runnable examples for the AerEO satellite data
extraction framework.

## Structure

```text
examples/
├── *.ipynb                 # Jupyter notebooks (one per sensor / workflow)
├── config/                 # Hydra config package (search, grid, patch, read, write, aoi)
└── serverless/             # AWS Lambda deployment examples
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
# examples/config/search/sentinel2_pc.yaml
_target_: aereo.builtins.SearchSTAC
stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
collections:
  sentinel-2-l2a: ["B04", "B08"]
intersects: config/aoi/chocon.geojson
start_datetime: "2024-01-01T00:00:00Z"
end_datetime: "2024-01-10T23:59:59Z"
```

```yaml
# examples/config/read/sentinel2.yaml
read:
  _target_: aereo.builtins.read.read_odc_stac
```

```yaml
# examples/config/write/sentinel2.yaml
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

Run the same configs from the command line:

```bash
cd examples/config

# Full pipeline
aereo action=run \
  search=sentinel2_pc \
  grid_dist=grid_10km \
  read=sentinel2 \
  write=sentinel2

# Search only
aereo action=search search=sentinel2_pc

# List installed plugins
aereo action=plugins
```

## Notebooks

| Notebook | Sensor | Description |
|----------|--------|-------------|
| `01-sentinel2.ipynb` | Sentinel-2 MSI | True-color extraction from Planetary Computer |
| `01b-sentinel2-ndvi.ipynb` | Sentinel-2 MSI | NDVI processing example |
| `step_by_step.ipynb` | Sentinel-2 MSI | Same pipeline as `01-sentinel2.ipynb`, but each stage is run and inspected explicitly |
| `step_by_step_raw.ipynb` | Sentinel-2 MSI | Same pipeline as `step_by_step.ipynb`, but built entirely from raw Python functions and parameters — no config files or Hydra |
| `02-viirs.ipynb` | VIIRS | Earthaccess search + Satpy read |
| `03-sentinel3.ipynb` | Sentinel-3 OLCI | Earthaccess search + Satpy read |
| `03b-sentinel3-ndvi.ipynb` | Sentinel-3 OLCI | NDVI processing example |
| `04-tessera.ipynb` | GeoTessera | Tessera tile search and extraction |
| `05-goes19.ipynb` | GOES-19 ABI | Public AWS S3 search + Satpy read |
| `06-swath-to-geobox-odc-vs-faiss.ipynb` | Synthetic swath | Reproject a 2-D lat/lon swath to a UTM GeoBox with `odc-geo` and FAISS nearest neighbours |
| `06b-viirs-swath-odc-vs-faiss.ipynb` | VIIRS I04 | Three-way comparison (`odc-geo`, Satpy `resample`, FAISS) on a real VIIRS L1B swath from NASA Earthdata |

## Shared data

| File | Description |
|---|---|
| `config/aoi/chocon.geojson` | AOI polygon — Chocón reservoir, Argentina |
| `config/aoi/cordoba.geojson` | AOI polygon — Córdoba, Argentina |
| `config/aoi/oxford.geojson` | AOI polygon — Oxford, UK |
| `config/aoi/sample.geojson` | Sample AOI |
