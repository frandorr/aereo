# AerEO 🪐

[![PyPI](https://img.shields.io/pypi/v/aereo.svg)](https://pypi.org/project/aereo)
[![PyPI Downloads](https://img.shields.io/pypi/dm/aereo.svg)](https://pypi.org/project/aereo)
[![Python Versions](https://img.shields.io/pypi/pyversions/aereo.svg)](https://pypi.org/project/aereo)
[![CI](https://github.com/frandorr/aereo/actions/workflows/ci.yml/badge.svg)](https://github.com/frandorr/aereo/actions/workflows/ci.yml)
[![GitHub Issues](https://img.shields.io/github/issues/frandorr/aereo.svg)](https://github.com/frandorr/aereo/issues)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/frandorr/aereo/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://frandorr.github.io/aereo)

> **Access, extract, reproject for Earth Observation — locally or on AWS Lambda, without reinventing the wheel.**

AerEO is a plugin-based satellite data extraction framework. It wires together
the catalog, reading, reprojection, and writing tools you already trust (STAC,
Earthaccess, Satpy, `odc-geo`) behind a single, replaceable-step pipeline. The
result: analysis-ready GeoTIFFs aligned to the [Major TOM
grid](https://github.com/ESA-PhiLab/Major-TOM), ready for ML or downstream analysis.

- **Plugin-based** — every stage (search, read, reproject, process, write) is a plain Python function you can swap.
- **Grid-aligned** — outputs are indexed on the [Major TOM grid](https://github.com/ESA-PhiLab/Major-TOM), so Sentinel-2, VIIRS, Sentinel-3, GOES, and custom sources stack together.
- **One config, multiple runtimes** — the same Hydra config runs in a notebook and serverless with `LambdaExecutor`.

## Install

AerEO's core framework includes built-in search (STAC, NASA Earthaccess, etc.),
read, reproject, and write functions. You can extend it with plugins for other
sensors and formats — by combining search, read, reproject, and write plugins
you can access hundreds of constellations without changing your pipeline.

Here are a few common combinations:

```bash
# STAC catalogs (Sentinel-2, Landsat, etc.)
uv add aereo
# or
pip install aereo

# NASA Earthaccess data (MODIS, VIIRS, Sentinel-3, etc.) with Satpy reading
uv add aereo aereo-read-satpy
# or
pip install aereo aereo-read-satpy

# GOES ABI public S3 data
uv add aereo aereo-search-aws-goes aereo-read-satpy
# or
pip install aereo aereo-search-aws-goes aereo-read-satpy

# GeoTessera tile catalogs
uv add aereo aereo-search-tessera aereo-read-tessera
# or
pip install aereo aereo-search-tessera aereo-read-tessera
```

Install the core framework with `uv add aereo` (or `pip install aereo`).
Sensor-specific search and I/O plugins are separate packages so you only ship
what you need.

## Copy/paste example

Save this as `quickstart.py` and run it with `uv run python quickstart.py`:

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
    artifacts = job.execute(tasks, executor=LocalExecutor(workers=1))
    print(f"Extracted {len(artifacts)} artifact(s)")

    catalog_uri = job.write_catalog(artifacts)
    print(f"\nCatalog written to: {catalog_uri}")


if __name__ == "__main__":
    main()
```

Open `/tmp/aereo_quickstart` — you have GeoTIFFs on the Major TOM grid. The script also calls `job.write_catalog(artifacts)`, so an `artifacts.parquet` catalog is written next to the GeoTIFFs.

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

1. **`ExtractionJob`** — a validated bundle of grid size, output URI, AOI, and reader/writer callables.
2. **Search function** — e.g. `search_stac`. Pass it to `job.search(...)` with kwargs.
3. **Task builder function** — e.g. `build_grouped_tasks`. Groups assets into `ExtractionTask` objects.
4. **`ExtractionTask`** — one unit of work: assets + grid patches + stage pipeline.
5. **Stage functions** — `read_odc_stac`, `reproject_odc`, `ndvi`, `write_geotiff`, etc. Passed directly to `ExtractionJob(read=..., write=...)`.
6. **`LocalExecutor`** — runs tasks locally. Swap for `LambdaExecutor` later without changing the pipeline.

## Docs & Examples

- [Install](https://frandorr.github.io/aereo/install/) — per-sensor install and credentials
- [Your First Pipeline](https://frandorr.github.io/aereo/getting-started/first-pipeline/) — first extraction in 5 minutes
- [Configuration](https://frandorr.github.io/aereo/configuration/config-package/) — Hydra config package and YAML schema
- [Tutorials](https://frandorr.github.io/aereo/examples/) — Sentinel-2, VIIRS, Sentinel-3, Tessera, GOES-19
- [Build a Plugin](https://frandorr.github.io/aereo/plugins/build-a-plugin/) — add a search, reader, or processing step
- [Run on AWS Lambda](https://frandorr.github.io/aereo/serverless/lambda/) — go serverless by changing one line

---

Apache License 2.0
