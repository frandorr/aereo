# Plugin System Overview

AerEO is built around plain Python functions. Search providers, readers,
processors, reprojectors, writers, and task builders are all plugins.

## How plugins are discovered

AerEO scans the `aereo.plugins` Python entry-point group at runtime. The
prefix of the entry-point name tells AerEO which stage the plugin belongs to,
and each stage has a typed Protocol that defines the input/output contract:

| Prefix | Stage | Example | Input → Output |
|---|---|---|---|
| `search_` | Search provider | `search_stac` | catalog query → `GeoDataFrame[AssetSchema]` |
| `task_builder_` | Task builder | `build_grouped_tasks` | assets + job → `Sequence[ExtractionTask]` |
| `read_` | Reader | `read_odc_stac` | `ExtractionTask` → `xr.Dataset` |
| `reproject_` | Reprojector | `reproject_odc` | `xr.Dataset` → `xr.Dataset` |
| `process_` | Processor | `ndvi`, `qa_mask` | `xr.Dataset` → `xr.Dataset` |
| `write_` | Writer | `write_geotiff` | `xr.Dataset` → artifact path/URI |

A plugin is a plain Python function. You do not need to subclass anything, but
you must satisfy the Protocol and schema of the stage you are implementing.

## Built-in plugins

These ship with `aereo` itself — no extra install needed:

| Plugin | Type | Description |
|---|---|---|
| `search_stac` | Search | Query any STAC API and return `GeoDataFrame[AssetSchema]` |
| `build_grouped_tasks` | Task builder | Group assets by time and native CRS into grid-aligned `ExtractionTask` objects |
| `read_odc_stac` | Reader | Load STAC assets via `odc.stac` into an `xarray.Dataset` |
| `reproject_odc` | Reprojector | Reproject/resample a dataset to a target geobox with `odc-geo` |
| `reproject_swath` | Reprojector | Resample swath data (e.g. VIIRS, OLCI) to a target grid with `pyresample` |
| `process_select_bands` | Processor | Subset a dataset to a list of bands |
| `process_qa_mask` | Processor | Apply a QA bit-mask band to the data |
| `process_ndvi` | Processor | Compute NDVI from NIR and red bands |
| `process_ndwi` | Processor | Compute NDWI from green and NIR bands |
| `process_normalize` | Processor | Normalize pixel values per band (min-max, z-score) |
| `process_composite` | Processor | Create a temporal composite (median, mean, ...) |
| `write_geotiff` | Writer | Write a dataset to GeoTIFF |

## Community plugins

External plugins are independent packages; installing one registers its entry
points automatically:

| Plugin | Type | Description | Install |
|---|---|---|---|
| `aereo-search-aws-goes` | Search | Discover GOES-R series data (GOES-16 through GOES-19) on public NOAA AWS S3 buckets | [PyPI](https://pypi.org/project/aereo-search-aws-goes/) · [Repo](https://github.com/frandorr/aereo-search-aws-goes) |
| `aereo-search-tessera` | Search | Search [GeoTessera](https://geotessera.io) satellite embedding tiles | [PyPI](https://pypi.org/project/aereo-search-tessera/) · [Repo](https://github.com/frandorr/aereo-search-tessera) |
| `aereo-herbie` | Search + Reader | Discover and read NWP model data (HRRR, GFS, ECMWF, GEFS) via [Herbie](https://herbie.readthedocs.io/) GRIB2 inventories | [Repo](https://github.com/frandorr/aereo-herbie) |
| `aereo-read-satpy` | Reader | Load satellite data from many EO formats via [Satpy](https://satpy.readthedocs.io/) into `xarray.Dataset` | [PyPI](https://pypi.org/project/aereo-read-satpy/) · [Repo](https://github.com/frandorr/aereo-read-satpy) |
| `aereo-read-tessera` | Reader | Read GeoTessera satellite embedding tiles | [PyPI](https://pypi.org/project/aereo-read-tessera/) · [Repo](https://github.com/frandorr/aereo-read-tessera) |

To build your own, start from the
[aereo-plugin-template](https://github.com/frandorr/aereo-plugin-template) and
follow [Build a Plugin](build-a-plugin.md).

## Using plugins

Plugins are passed directly to `ExtractionJob` or `job.search()` /
`job.build_tasks()`:

```python
from aereo.builtins import search_stac, build_grouped_tasks, read_odc_stac, write_geotiff
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob(
    name="demo",
    grid_dist=10_000,
    output_uri="/tmp/demo",
    read=read_odc_stac,
    write=write_geotiff,
    target_aoi=aoi,
)

assets = job.search(search_stac, ...)
tasks = job.build_tasks(assets, build_grouped_tasks)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
```

## Listing installed plugins

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()
print(registry.list_supported_collections())
print(list(registry.list_all_params()))
```

## Next steps

- [Build a Plugin](build-a-plugin.md) — write and register your first plugin.
- [Choosing a Sensor](../user-guide/choosing-a-sensor.md) — pick the right
  plugins for your dataset.
