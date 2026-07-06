# Plugin System Overview

AEREO is built around plain Python functions. Search providers, readers,
processors, reprojectors, writers, and task builders are all plugins.

## How plugins are discovered

AEREO scans the `aereo.plugins` Python entry-point group at runtime. The
prefix of the entry-point name tells AEREO which stage the plugin belongs to:

| Prefix | Stage | Example |
|---|---|---|
| `search_` | Search provider | `search_stac` |
| `task_builder_` | Task builder | `build_grouped_tasks` |
| `read_` | Reader | `read_odc_stac` |
| `reproject_` | Reprojector | `reproject_odc` |
| `process_` | Processor | `ndvi`, `qa_mask` |
| `write_` | Writer | `write_geotiff` |

## Built-in plugins

The `aereo.builtins` package ships with common plugins:

- **Search:** `search_stac`, `search_earthaccess`
- **Task builder:** `build_grouped_tasks`
- **Reader:** `read_odc_stac`
- **Reprojectors:** `reproject_odc`, `reproject_swath`, `reproject_pyresample`
- **Processors:** `select_bands`, `qa_mask`, `ndvi`, `ndwi`, `normalize`, `composite`
- **Writer:** `write_geotiff`

External plugins include `search_aws_goes`, `read_satpy`, `reproject_satpy`,
`search_tessera`, and `read_tessera`.

## Using plugins

Plugins are passed directly to `ExtractionJob` or `job.search()` / `job.build_tasks()`:

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

```bash
aereo action=plugins
aereo action=plugin_params plugin=search_stac
```

## Next steps

- [Build a Plugin](build-a-plugin.md) — write and register your first plugin.
- [Choosing a Sensor](../user-guide/choosing-a-sensor.md) — pick the right
  plugins for your dataset.
