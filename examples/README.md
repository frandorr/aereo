# AEREO Examples

This directory contains reference examples and data for working with the AEREO satellite data extraction framework.

## Structure

```
examples/
├── data/                 # Shared input data (AOI GeoJSONs, grid configs)
├── grid/                 # Notebooks demonstrating the AEREO grid system
├── grid_configs/         # Example JSON grid configurations
├── helpers/              # Shared Python helper utilities used by examples
└── serverless/           # AWS Lambda deployment examples
```

## Quickstart

The recommended entry point is the interactive search notebook:

```bash
cd development/local/search
jupyter notebook search.ipynb
```

This notebook demonstrates the full **search → prepare → extract** pipeline using a Hydra-native YAML configuration loaded from `development/local/data/search_job.yaml`.

## Configuration

All pipeline configurations use the Hydra `_target_` convention for declarative instantiation:

```yaml
# development/local/data/search_job.yaml
search:
  _target_: aereo.builtins.SearchSTAC
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: ["B04", "B03", "B02"]
  start_datetime: "2024-01-01T00:00:00Z"
  end_datetime: "2024-01-10T00:00:00Z"

pipeline:
  - _target_: aereo.builtins.ReadODCSTAC
  - _target_: aereo.builtins.ReprojectODC
    resolution: 10.0
  - _target_: aereo.builtins.WriteGeoTIFF

grid_config:
  _target_: aereo.interfaces.GridConfig
  target_grid_dist: 50000

uri: "/tmp/output"
```

Configurations can be loaded and instantiated programmatically:

```python
from omegaconf import OmegaConf
import hydra

cfg = OmegaConf.load("development/local/data/search_job.yaml")
job = hydra.utils.instantiate(cfg, _convert_="all")
```

Or loaded directly from a YAML file into an `ExtractionJob`:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.from_yaml("my_job.yaml")
```

## CLI

Run extractions from the command line using Hydra overrides:

```bash
# Full run with a job config file
aereo action=run search.start_datetime="2024-01-01T00:00:00Z"

# Search only
aereo action=search

# List installed plugins
aereo action=plugins
```

## Shared Data

| File | Description |
|---|---|
| `data/chocon.geojson` | AOI polygon — Chocon reservoir, Argentina |
| `data/lake_barkley.geojson` | AOI polygon — Lake Barkley, USA |
| `data/grid_config.yaml` | 50 km grid configuration |
| `data/grid_config_10km.yaml` | 10 km grid configuration |
