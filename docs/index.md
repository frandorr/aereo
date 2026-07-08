<div class="hero-banner" markdown>
![AerEO logo](banner.svg)

**Access, extract, reproject for Earth Observation — locally or on AWS Lambda, without reinventing the wheel.**
</div>

# AerEO

AerEO is a plugin-based satellite data extraction framework. It wires together
the catalog, reading, reprojection, and writing tools you already trust (STAC,
Earthaccess, Satpy, `odc-geo`) behind a single pipeline where every step can be
replaced. The result: analysis-ready GeoTIFFs aligned to the [Major TOM
grid](user-guide/grids.md).

---

## Install

AerEO's core framework includes built-in search (STAC, NASA Earthaccess, etc.),
read, reproject, and write functions. You can extend it with plugins for other
sensors and formats — by combining search, read, reproject, and write plugins
you can access hundreds of constellations without changing your pipeline.

=== "STAC (Sentinel-2, Landsat, etc.)"

    ```bash
    uv add aereo
    # or
    pip install aereo
    ```

=== "NASA Earthaccess (MODIS, VIIRS, Sentinel-3, etc.)"

    ```bash
    uv add aereo aereo-read-satpy
    # or
    pip install aereo aereo-read-satpy
    ```

    Configure [earthaccess](https://github.com/nsidc/earthaccess) credentials
    (`.netrc`, environment variables, or `earthaccess.login()`) before searching.

=== "GOES ABI (public S3)"

    ```bash
    uv add aereo aereo-search-aws-goes aereo-read-satpy
    # or
    pip install aereo aereo-search-aws-goes aereo-read-satpy
    ```

    GOES data on AWS is public, so no authentication is required.

=== "GeoTessera"

    ```bash
    uv add aereo aereo-search-tessera aereo-read-tessera
    # or
    pip install aereo aereo-search-tessera aereo-read-tessera
    ```

    GeoTessera data is public, so no authentication is required.

> Install the core framework with `uv add aereo` (or `pip install aereo`).
> Sensor-specific plugins are separate packages so you only ship what you need.
> Optional extras cover serverless (`aereo[serverless]`), swath reprojection
> (`aereo[swath]`), and viz (`aereo[viz]`); use `aereo[all]` to install them all.

---

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

Open `/tmp/aereo_quickstart` — you have GeoTIFFs on the Major TOM grid. The
script also calls `job.write_catalog(artifacts)`, so an `artifacts.parquet`
catalog is written next to the GeoTIFFs.

---

## What you get

These outputs come straight from the tutorial notebooks. Every plot shows
grid-aligned patches on the Major TOM grid, with the target AOI overlaid.

<div class="hero-grid" markdown>

-   ### [Sentinel-2 (nir, red)](examples/01-sentinel2.ipynb)

    ![Sentinel-2 extracted patches](assets/images/01-sentinel2-plot-patches.png)

-   ### [Sentinel-2 NDVI](examples/01b-sentinel2-ndvi.ipynb)

    ![Sentinel-2 NDVI patches](assets/images/01b-sentinel2-ndvi-plot-patches.png)

-   ### [VIIRS](examples/02-viirs.ipynb)

    ![VIIRS extracted patches](assets/images/02-viirs-plot-patches.png)

-   ### [Multiple constellations](examples/06-multiple-constellation.ipynb)

    GOES-19 ABI and VIIRS extracted for the same grid cells:

    ![GOES-19 ABI on the shared grid](assets/images/06-multiple-constellation-f6d7b8aa.png)

    ![VIIRS on the shared grid](assets/images/06-multiple-constellation-7790c104.png)

</div>

See the full gallery in the [Tutorials](examples/index.md) section.

---

## How it works

```mermaid
flowchart LR
    Search["Search provider"] --> Prepare["Prepare tasks\n(grid + grouping)"]
    Prepare --> Execute["Execute\n(local / Lambda)"]
    Execute --> Catalog["Output catalog\n+ GeoTIFFs"]
```

1. **Search** — query a catalog and get a validated `GeoDataFrame[AssetSchema]`.
2. **Prepare** — group assets by time and native CRS into `ExtractionTask`
   objects.
3. **Execute** — run each task through `read → preprocess → reproject →
   postprocess → write`, producing grid-aligned artifacts and a catalog.

Any stage can be replaced by a function you write. Learn how in
[Build a Plugin](plugins/build-a-plugin.md).

---

## Why AerEO?

<div class="hero-grid" markdown>

-   ### Search anything

    One `job.search(...)` call works with STAC, Earthaccess, public S3, and
    custom catalogs. Swap the search function without changing your pipeline.

-   ### Grid aligned

    Outputs are indexed on the [Major TOM grid](user-guide/grids.md), so
    Sentinel-2, VIIRS, Sentinel-3, and GOES scenes stack together out of the
    box.

-   ### One config, multiple runtimes

    The same Hydra config package runs in a notebook and on AWS Lambda.

-   ### Plain Python plugins

    No inheritance, no framework boilerplate. AerEO plugins are
    `@validate_call` functions registered via standard Python entry points.

</div>
