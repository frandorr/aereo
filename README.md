<p align="center">
  <img src="docs/banner.svg" alt="AerEO banner" width="400">
</p>

# AerEO

> **Access, extract, reproject for Earth Observation — locally or remotely, with a pluggable pipeline, without reinventing the wheel.**

[![Install](https://img.shields.io/badge/install-uv%20add%20aereo-3776AB?logo=python&logoColor=white)](https://frandorr.github.io/aereo/install/)
[![Docs](https://img.shields.io/badge/docs-frandorr.github.io%2Faereo-2ea44f?logo=materialformkdocs)](https://frandorr.github.io/aereo)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

AerEO is a plugin-based satellite data extraction framework. It wires together
the catalog, reading, reprojection, and writing tools you already trust (STAC,
Earthaccess, Satpy, `odc-geo`) behind a single pipeline where every step can be
replaced. The result: analysis-ready GeoTIFFs aligned to the [Major TOM
grid](https://github.com/ESA-PhiLab/Major-TOM), ready for ML or downstream analysis.

Each stage below is a plain Python function you can swap. You can keep the
built-ins, replace one step, or plug in an entirely different block at any
point in the pipeline.

```mermaid
flowchart TB
    classDef required stroke-width:4px
    classDef optional stroke-dasharray: 5 5

    subgraph SearchAndPrepare ["Search and prepare"]
        direction LR
        Search["Search"] --> Build["Build tasks"]
    end

    subgraph Extract ["Extract"]
        direction LR
        Read["Read assets"] --> Preprocess["Preprocess"] --> Reproject["Reproject"] --> Postprocess["Postprocess"]
    end

    subgraph WriteArtifacts ["Write artifacts"]
        direction LR
        Write["Write GeoTIFF"] --> Catalog["Major TOM catalog<br/>artifacts.parquet"]
    end

    SearchAndPrepare --> Extract
    Extract --> WriteArtifacts

    class Search,Build,Read,Write required
    class Preprocess,Reproject,Postprocess,Catalog optional

    style Search fill:#e3f2fd,stroke:#1565c0
    style Build fill:#e8f5e9,stroke:#2e7d32
    style Read fill:#fff3e0,stroke:#ef6c00
    style Preprocess fill:#f3e5f5,stroke:#6a1b9a
    style Reproject fill:#fce4ec,stroke:#c2185b
    style Postprocess fill:#f3e5f5,stroke:#6a1b9a
    style Write fill:#e0f2f1,stroke:#00695c
    style Catalog fill:#e8eaf6,stroke:#283593
```

*Solid borders = required stages. Dashed borders = optional stages. Every stage is interchangeable.*

<p align="center">
  <img src="docs/assets/images/01c-sentinel2-ndwi-search-sentinel2.png" alt="Sentinel-2 NDWI extracted on the Major TOM grid" width="500">
</p>

*Sentinel-2 NDWI extracted as Major TOM grid cells. Every job writes an
`artifacts.parquet` catalog where each row is a Major TOM grid cell referencing
the file that was just extracted; the default writer emits GeoTIFFs, but you
can swap in any writer plugin. Because everything is aligned to the same grid,
outputs from different sensors and dates can be merged directly into ML
datasets.*

## Install

The fastest way to get started is to install AerEO with all optional extras:

```bash
uv add "aereo[all]"
# or
pip install "aereo[all]"
```

Sensor-specific search and I/O plugins are separate packages, so you only ship
what you need. For per-sensor install commands and credentials, see
[Install](https://frandorr.github.io/aereo/install/).

> **First-run checklist**
> - Python 3.12 or newer
> - `pip` or `uv`
> - Credentials for any catalog that requires them (e.g. NASA Earthdata for VIIRS / Sentinel-3)
> - Run in the same AWS region as your data source for large extractions

> **Performance tip:** Run AerEO in the same region as your data source. During
> extraction, data is downloaded from the source catalog; if your runtime is not
> in the same AWS region as the data, downloads can be **very slow**. Being in the
> same region is **HIGHLY recommended** to avoid slow transfers and egress
> charges.

Full documentation: https://frandorr.github.io/aereo

<details>
<summary><b>Optional extras</b></summary>

AerEO's core install covers STAC search, ODC-based reprojection, GeoTIFF writing,
and local execution. A few built-in capabilities need extra dependencies:

| Extra | Enables | Install |
|---|---|---|
| `serverless` | `LambdaExecutor` and S3 staging (via `boto3`) | `uv add aereo[serverless]` |
| `swath` | `reproject_swath` / `reproject_pyresample` for 2-D lat/lon swath data | `uv add aereo[swath]` |
| `viz` | Cartopy-backed plots in `aereo.viz` | `uv add aereo[viz]` |
| `pc` | Microsoft Planetary Computer integration | `uv add aereo[pc]` |
| `all` | Everything above in one command | `uv add aereo[all]` |

</details>

## Which example should I run?

| I want to... | Start with | Why |
|---|---|---|
| Try without credentials | [01 — Sentinel-2](examples/01-sentinel2.ipynb) | STAC, public data, no auth |
| Learn the raw API | [Step by step raw pipeline](examples/step_by_step_raw.ipynb) | No Hydra, no config files |
| Compute an index (NDVI) | [01b — Sentinel-2 NDVI](examples/01b-sentinel2-ndvi.ipynb) | Shows the `postprocess` stage |
| Use NASA data (VIIRS / Sentinel-3) | [02 — VIIRS](examples/02-viirs.ipynb) or [03 — Sentinel-3 OLCI](examples/03-sentinel3.ipynb) | Earthaccess + Satpy |
| Run multiple sensors on the same grid | [06 — Multiple constellations](examples/06-multiple-constellation.ipynb) | Compares VIIRS and GOES-19 ABI |

## Examples

All tutorial notebooks can be opened directly in Google Colab. Each notebook starts with a setup cell that installs AerEO and any sensor-specific plugins it needs.

| Notebook | Sensor(s) | Open in Colab |
|---|---|---|
| [01 — Sentinel-2](examples/01-sentinel2.ipynb) | Sentinel-2 L2A | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/01-sentinel2.ipynb) |
| [01b — Sentinel-2 NDVI](examples/01b-sentinel2-ndvi.ipynb) | Sentinel-2 L2A (NDVI) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/01b-sentinel2-ndvi.ipynb) |
| [01c — Sentinel-2 NDWI](examples/01c-sentinel2-ndwi.ipynb) | Sentinel-2 L2A (NDWI) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/01c-sentinel2-ndwi.ipynb) |
| [02 — VIIRS](examples/02-viirs.ipynb) | VIIRS | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/02-viirs.ipynb) |
| [03 — Sentinel-3 OLCI](examples/03-sentinel3.ipynb) | Sentinel-3 OLCI | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/03-sentinel3.ipynb) |
| [03b — Sentinel-3 NDVI](examples/03b-sentinel3-ndvi.ipynb) | Sentinel-3 OLCI (NDVI) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/03b-sentinel3-ndvi.ipynb) |
| [04 — GeoTessera](examples/04-tessera.ipynb) | GeoTessera | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/04-tessera.ipynb) |
| [05 — GOES-19 ABI](examples/05-goes19.ipynb) | GOES-19 ABI | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/05-goes19.ipynb) |
| [06 — Multiple constellations](examples/06-multiple-constellation.ipynb) | VIIRS + GOES-19 | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/06-multiple-constellation.ipynb) |
| [Step by step raw pipeline](examples/step_by_step_raw.ipynb) | Sentinel-2 (raw API) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/frandorr/aereo/blob/main/examples/step_by_step_raw.ipynb) |

<details>
<summary><b>NASA Earthaccess authentication for Colab</b></summary>

The [VIIRS](examples/02-viirs.ipynb), [Sentinel-3 OLCI](examples/03-sentinel3.ipynb), and [Sentinel-3 NDVI](examples/03b-sentinel3-ndvi.ipynb) notebooks use `earthaccess` to query NASA data. You must configure authentication first. The recommended way is to create a `~/.netrc` file — follow the [earthaccess authentication guide](https://earthaccess.readthedocs.io/en/latest/user/howto/authenticate/).

For Google Colab, run this cell once to create `~/.netrc`:

```python
import os
from getpass import getpass

earthdata_username = getpass("Earthdata username: ")
earthdata_password = getpass("Earthdata password: ")

netrc_path = os.path.expanduser("~/.netrc")
with open(netrc_path, "w") as f:
    f.write("machine urs.earthdata.nasa.gov login {username} password {password}\n".format(
        username=earthdata_username,
        password=earthdata_password
    ))
os.chmod(netrc_path, 0o600)
print(f"Successfully created {netrc_path} for Earthdata authentication.")
```

</details>

## Quickstart with a YAML config

This five-step guide extracts Sentinel-2 red + nir bands from Microsoft Planetary
Computer over the Chocón reservoir in Argentina. Planetary Computer serves data
from Azure Blob Storage, so this works well even when your runtime is not in an
AWS data region. No repo clone required.

<details>
<summary><b>Step 1: create a project (30 seconds)</b></summary>

```bash
mkdir my_first_job && cd my_first_job
uv init
uv add "aereo[pc]"
```

`aereo[pc]` includes the core framework plus the Planetary Computer signing helper, which gives fast global access to Sentinel-2 data.

</details>

<details>
<summary><b>Step 2: download a sample AOI</b></summary>

```bash
curl -L -o aoi.geojson https://raw.githubusercontent.com/frandorr/aereo/main/examples/config/aoi/chocon.geojson
```

</details>

<details>
<summary><b>Step 3: write the job config</b></summary>

Create `job.yaml`:

```yaml
name: pc_s2_demo
grid_dist: 10_000
output_uri: ./output
target_aoi: ./aoi.geojson

search:
  _target_: aereo.builtins.search_stac
  _partial_: true
  stac_api_url: "https://planetarycomputer.microsoft.com/api/stac/v1"
  collections:
    sentinel-2-l2a: [B04, B08]
  intersects: ./aoi.geojson
  start_datetime: "2024-01-01T00:00:00Z"
  end_datetime: "2024-01-03T23:59:59Z"
  pystac_open_params:
    modifier:
      _target_: planetary_computer.sign_inplace

read:
  _partial_: true
  _target_: aereo.builtins.read_odc_stac
  patch_url:
    _target_: planetary_computer.sign
  dtype: "uint16"
  nodata: 0
write:
  _target_: aereo.builtins.write.write_geotiff
```

*Key fields:*
- `grid_dist`: Major TOM grid spacing in meters (`10_000` = 10 km cells).
- `target_aoi`: Path to a GeoJSON polygon.
- `collections`: Map of STAC collection names to the bands you want (`B04`, `B08` for Sentinel-2 red / nir).
- `pystac_open_params.modifier` / `read.patch_url`: Planetary Computer URL signing; required to fetch assets from Azure Blob Storage.

</details>

<details>
<summary><b>Step 4: write the runner script</b></summary>

Create `run_job.py`:

```python
from aereo.pipeline import ExtractionJob
from aereo.builtins import build_grouped_tasks
from aereo.executors import LocalExecutor

job = ExtractionJob.load_from_config(".", config_name="job")

assets = job.search()
if assets.empty:
    raise SystemExit("No assets found.")

tasks = job.build_tasks(assets, build_grouped_tasks)

# Run only the first task for demo speed.
artifacts = job.execute(tasks[:1], executor=LocalExecutor(workers=1))
catalog_uri = job.write_catalog(artifacts)
print(f"Catalog: {catalog_uri}")
```

*Why `tasks[:1]`?* A real extraction runs every task; slicing to one task keeps the first demo fast and avoids downloading more data than needed.

</details>

<details>
<summary><b>Step 5: run it</b></summary>

```bash
uv run run_job.py
```

You will get GeoTIFFs in `./output` plus `output/artifacts.parquet`, where each row is one Major TOM grid cell.

</details>

## Copy/paste example

Save this as `quickstart.py` and run it with `uv run quickstart.py`:

> **Network speed note:** This example downloads Sentinel-2 data from Earth Search over the public internet. From a local machine the download can be a bottleneck. For the fastest first experience, run it in Google Colab or an AWS compute instance in the same region as the data (`us-west-2` for Earth Search).

```python
"""Pure-Python quickstart for AerEO.
To run the full pipeline:

    uv run python examples/quickstart_pure_python.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from shapely.geometry import Polygon

from aereo.builtins import (
    build_grouped_tasks,
    read_odc_stac,
    search_stac,
    write_geotiff,
)
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob


def main() -> None:
    """Build a job in pure Python and run the extraction pipeline."""
    # Tiny AOI around Chocón reservoir, Argentina.
    aoi = Polygon(
        [
            (-68.90986824592407, -39.23705421799603),
            (-68.65925870907353, -39.23705421799603),
            (-68.65925870907353, -39.41589522092947),
            (-68.90986824592407, -39.41589522092947),
            (-68.90986824592407, -39.23705421799603),
        ]
    )

    job = ExtractionJob(
        name="quickstart",
        grid_dist=10_000,
        output_uri="/tmp/aereo_quickstart",
        search=search_stac,
        read=read_odc_stac,
        write=write_geotiff,
        target_aoi=aoi,
    )

    print("--- ExtractionJob ---")
    print(f"name: {job.name}")
    print(f"output_uri: {job.output_uri}")
    print(f"grid_dist: {job.grid_dist}")

    print("\n--- Search ---")
    assets = job.search(
        stac_api_url="https://earth-search.aws.element84.com/v1",
        collections={"sentinel-2-l2a": ["red", "nir"]},
        intersects=aoi,
        start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )
    print(f"Found {len(assets)} asset rows")

    if assets.empty:
        print("No assets found; nothing to extract.")
        return

    print("\n--- Build tasks ---")
    tasks = job.build_tasks(assets, build_grouped_tasks)
    print(f"Built {len(tasks)} task(s)")

    print("\n--- Extract ---")
    # Run only the first task for demo speed.
    artifacts = job.execute(tasks[:1], executor=LocalExecutor(workers=1))
    print(f"Extracted {len(artifacts)} artifact(s)")

    catalog_uri = job.write_catalog(artifacts)
    print(f"\nCatalog written to: {catalog_uri}")


if __name__ == "__main__":
    main()
```

Open `/tmp/aereo_quickstart` — you have GeoTIFFs on the Major TOM grid. The script also calls `job.write_catalog(artifacts)`, so an `artifacts.parquet` catalog is written next to the GeoTIFFs.

## Configuration with Hydra

For reusable jobs, put YAML configs in a Hydra package and load them with
`ExtractionJob.load_from_config`. This is the same Sentinel-2 job as the
quickstart, expressed as config:

```yaml
# examples/config/job_sentinel2.yaml
target_bands: [red, nir]
aoi_path: config/aoi/chocon.geojson

name: sentinel2_sample
grid_dist: 10_000
grid_cells_margin: 10
target_aoi: ${aoi_path}
output_uri: /tmp/aereo_extraction
overwrite: false

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
  _target_: aereo.builtins.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
```

Load and override values from Python:

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    config_dir="examples/config",
    config_name="job_sentinel2",
    overrides=[
        "grid_dist=50_000",
        "search.start_datetime=2024-02-01T00:00:00Z",
    ],
)
```

The `overrides` use Hydra dot notation, so any field in the YAML can be changed
without editing the file.

## How it works

<details>
<summary><b>Pipeline overview</b></summary>

```mermaid
flowchart LR
    Search["Search provider"] --> Prepare["Prepare tasks\n(grid + grouping)"]
    Prepare --> Execute["Execute\n(local / Lambda)"]
    Execute --> Catalog["Output catalog\n+ GeoTIFFs"]
```

1. **Search** — query a catalog and get a validated `GeoDataFrame[AssetSchema]`.
2. **Prepare** — group assets by time and native CRS into `ExtractionTask` objects.
3. **Execute** — run each task through `read → preprocess → reproject → postprocess → write`, producing grid-aligned artifacts and a catalog.

Any stage can be replaced by a function you write. Learn how in
[Build a Plugin](https://frandorr.github.io/aereo/plugins/build-a-plugin/).

</details>

## Why AerEO?

| Problem | How AerEO solves it |
|---|---|
| Every catalog has a different API | One `job.search(...)` call with swappable search functions. |
| Tiles do not line up across sensors | Built-in Major TOM grid + local UTM patch geoboxes. |
| Reprojection boilerplate | Readers/writers can call `reproject_odc` (or any reprojector) as needed. |
| Mixed-CRS scenes fail | `build_grouped_tasks` groups assets by native CRS. |
| Notebook → production is hard | Same config package runs in Python and AWS Lambda. |
| Plugin frameworks force inheritance | AerEO plugins are `@validate_call` functions + standard entry points. |

## Core concepts

<details>
<summary><b>Core concepts</b></summary>

1. **`ExtractionJob`** — a validated bundle of grid size, output URI, AOI, and reader/writer callables.
2. **Search function** — e.g. `search_stac`. Pass it to `job.search(...)` with kwargs.
3. **Task builder function** — e.g. `build_grouped_tasks`. Groups assets into `ExtractionTask` objects.
4. **`ExtractionTask`** — one unit of work: assets + grid patches + stage pipeline.
5. **Stage functions** — `read_odc_stac`, `reproject_odc`, `ndvi`, `write_geotiff`, etc. Passed directly to `ExtractionJob(read=..., write=...)`.
6. **`LocalExecutor`** — runs tasks locally. Swap for `LambdaExecutor` later without changing the pipeline.

</details>

## What you get

These outputs come straight from the tutorial notebooks. Every plot shows
grid-aligned patches on the Major TOM grid, with the target AOI overlaid.

### [Sentinel-2 (nir, red)](examples/01-sentinel2.ipynb)

<img src="docs/assets/images/01-sentinel2-plot-patches.png" alt="Sentinel-2 extracted patches" width="500">

### [Sentinel-2 NDVI](examples/01b-sentinel2-ndvi.ipynb)

<img src="docs/assets/images/01b-sentinel2-ndvi-plot-patches.png" alt="Sentinel-2 NDVI patches" width="500">

### [VIIRS](examples/02-viirs.ipynb)

<img src="docs/assets/images/02-viirs-plot-patches.png" alt="VIIRS extracted patches" width="500">

### VIIRS vs GOES-19 ABI — same grid, different sensors

The same Major TOM grid cells extracted from two very different sensors:

| GOES-19 ABI | VIIRS |
|---|---|
| <img src="docs/assets/images/06-multiple-constellation-f6d7b8aa.png" alt="GOES-19 ABI on the shared grid" width="400"> | <img src="docs/assets/images/06-multiple-constellation-7790c104.png" alt="VIIRS on the shared grid" width="400"> |

See the full walkthrough in [06 — Multiple constellations](examples/06-multiple-constellation.ipynb).

## For ML users

AerEO outputs are designed to be loaded directly into ML pipelines. After a run you have:

- GeoTIFFs aligned to the Major TOM grid, so multi-sensor and multi-date stacks line up without manual reprojection.
- `artifacts.parquet`, a per-cell catalog with columns: `id`, `source_ids`, `start_time`, `end_time`, `uri`, `collection`, `geometry`, `grid_cell`, `grid_dist`, `cell_geometry`, `cell_utm_crs`, `cell_utm_footprint`.

Load the catalog and read the rasters:

```python
import geopandas as gpd
import rasterio

df = gpd.read_parquet("output/artifacts.parquet")
print(df[["grid_cell", "start_time", "uri"]].head())

with rasterio.open(df.iloc[0].uri) as src:
    print(src.shape, src.count, src.crs)
```

Because every sensor writes the same grid cells, you can join rows by `grid_cell` and `start_time` to build multi-sensor training samples.

## Troubleshooting

<details>
<summary><b>Common issues</b></summary>

| Symptom | Likely cause | Fix |
|---|---|---|
| `No assets found` | Date range or AOI too restrictive | Widen the time range or check the AOI geometry |
| Downloads are very slow | Running in a different AWS region than the data | Move your runtime to the same region as the catalog (e.g. `us-west-2` for Earth Search) |
| `earthaccess` authentication error | Missing `.netrc` or expired credentials | Create `~/.netrc` following the [earthaccess guide](https://earthaccess.readthedocs.io/en/latest/user/howto/authenticate/) |
| `grid_dist` looks wrong | It is in meters, not pixels or degrees | Use values like `10_000` for 10 km cells |
| Outputs do not line up | Different sensors without a shared grid | Ensure all jobs use the same `grid_dist` and Major TOM grid |

</details>

## Docs

- [Install](https://frandorr.github.io/aereo/install/) — per-sensor install and credentials
- [Pure Python Quickstart](https://frandorr.github.io/aereo/getting-started/pure-python/) — first extraction in 5 minutes
- [Configuration](https://frandorr.github.io/aereo/configuration/config-package/) — Hydra config package and YAML schema
- [Tutorials](https://frandorr.github.io/aereo/examples/) — Sentinel-2, VIIRS, Sentinel-3, Tessera, GOES-19
- [Build a Plugin](https://frandorr.github.io/aereo/plugins/build-a-plugin/) — add a search, reader, or processing step
- [Run on AWS Lambda](https://frandorr.github.io/aereo/serverless/lambda/) — go serverless by changing one line

## Acknowledgments

- AerEO is inspired by the work done in [FDL sat-extractor](https://github.com/FrontierDevelopmentLab/sat-extractor).

  <img src="https://github.com/FrontierDevelopmentLab/sat-extractor/raw/main/images/fdleuropeESA.png" alt="FDL Europe / ESA" width="200">

- It is built upon the [Major TOM grid from ESA](https://github.com/ESA-PhiLab/Major-TOM).

  <img src="docs/assets/images/major-tom-grid-overview.jpeg" alt="Major TOM grid overview" width="200">

---

Apache License 2.0
