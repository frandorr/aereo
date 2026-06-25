# Run with Python

The Python API is the most flexible way to run AEREO. It is also what the CLI
and Lambda handler call under the hood.

---

## Recommended: load a Hydra config package

AEREO pipelines are configured as [Hydra](https://hydra.cc/) config packages. A
config package is just a directory of YAML files that compose into an
`ExtractionJob`. The repo ships an example package under `examples/config`.

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
)
```

The loaded `job` contains everything the pipeline needs:

```python
print(job.name)          # "sentinel2_sample"
print(job.output_uri)    # "/tmp/aereo_extraction"
print(job.grid_config)   # GridConfig instance
print(job.patch_config)  # PatchConfig instance
print(job.extract)       # ExtractConfig instance
```

Search providers and task builders are **runtime** arguments, not part of the
job. Load them separately from the config package or instantiate them in code.

You can override any config group at load time:

```python
job = ExtractionJob.load_from_config(
    "examples/config",
    config_name="job_sentinel2",
    overrides=[
        "patch_config=high_res",
        "grid_config=grid_50km",
    ],
)
```

---

## The three-step pipeline

Once you have a job, the pipeline is always the same three calls:

```python
from aereo.builtins import build_grouped_tasks, search_stac
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

# 1. Search
results = job.search(
    search_stac,
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime="2024-01-01T00:00:00Z",
    end_datetime="2024-01-10T23:59:59Z",
)
print(f"Found {len(results)} assets")

# 2. Prepare tasks
tasks = job.build_tasks(results, build_grouped_tasks, cells_per_task=5)
print(f"Prepared {len(tasks)} tasks")

# 3. Execute
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
print(f"Extracted {len(artifacts)} artifacts")

# 4. Write the catalog
job.write_catalog(artifacts)
```

Each step returns a typed GeoDataFrame:

| Step | Method | Input | Output |
|------|--------|-------|--------|
| Search | `job.search(search_fn, ...)` | search function | `GeoDataFrame[AssetSchema]` |
| Prepare | `job.build_tasks(assets, task_builder_fn, ...)` | search results + task builder function | `Sequence[ExtractionTask]` |
| Execute | `job.execute(tasks, executor=...)` | tasks + executor | `GeoDataFrame[ArtifactSchema]` |

---

## Run the full pipeline in one block

Here is a complete, copy-pasteable example using the built-in config package:

```python
from aereo.builtins import build_grouped_tasks, search_stac
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

results = job.search(
    search_stac,
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime="2024-01-01T00:00:00Z",
    end_datetime="2024-01-10T23:59:59Z",
)
tasks = job.build_tasks(results, build_grouped_tasks, cells_per_task=5)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))

print(artifacts[["id", "grid_cell", "uri"]].head())
```

---

## Advanced: build everything in Python

If you need dynamic logic, construct the objects directly instead of loading a
config package.

```python
from datetime import datetime, timezone
from aereo.builtins import (
    build_grouped_tasks,
    read_odc_stac,
    reproject_odc,
    search_stac,
    write_geotiff,
)
from aereo.interfaces import ExtractConfig, GridConfig, PatchConfig
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

assets = search_stac(
    stac_api_url="https://earth-search.aws.element84.com/v1",
    collections={"sentinel-2-l2a": ["red", "nir"]},
    intersects="examples/config/aoi/chocon.geojson",
    start_datetime=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end_datetime=datetime(2024, 1, 10, tzinfo=timezone.utc),
)

extract = ExtractConfig(
    read=read_odc_stac,
    reproject=reproject_odc,
    write=write_geotiff,
)

job = ExtractionJob(
    grid_config=GridConfig(target_grid_dist=10_000),
    patch_config=PatchConfig(resolution=10.0),
    output_uri="/tmp/aereo_python",
    extract=extract,
)

tasks = job.build_tasks(assets, build_grouped_tasks, cells_per_task=50)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))
job.write_catalog(artifacts)
```

---

## Writing the catalog

`job.execute()` returns the artifact GeoDataFrame; writing it is a separate,
optional step. `job.write_catalog()` is a convenience that writes
`artifacts.parquet` under `job.output_uri`:

```python
job.write_catalog(artifacts)
# → <output_uri>/artifacts.parquet
```

You can also write it yourself:

```python
artifacts.to_parquet("/tmp/my_catalog.parquet")
```

---

## Troubleshooting

### `ValueError: ExtractionJob.output_uri must be a non-empty string`

`build_tasks()` receives a complete ``ExtractionJob``. Make sure ``output_uri``
is set, either in your YAML config or when constructing the job in Python.

### `ValueError: GridConfig.target_grid_dist must be an explicit integer`

`build_tasks()` needs a ``GridConfig`` with an explicit ``target_grid_dist``.
Set it in your job config or ``ExtractionJob`` constructor.

### `ValueError: extract must be provided`

``ExtractionJob`` needs an ``ExtractConfig``. When loading from a config package,
make sure the ``extract:`` group is selected in your YAML defaults.

### Empty search results

- Widen the date range.
- Check that the collection name is correct and case-sensitive.
- Verify the AOI intersects the sensor's orbit footprint.

### Empty task list

The grid was generated but no cells matched the asset geometry. Try a less
strict grid filter mode in your config, or a larger AOI.
