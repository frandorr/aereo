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
from aereo.builtins import GroupedTaskBuilder, SearchSTAC
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

# 1. Search
provider = SearchSTAC(...)  # or load from config
results = job.search(provider)
print(f"Found {len(results)} assets")

# 2. Prepare tasks
task_builder = GroupedTaskBuilder()
tasks = job.build_tasks(results, task_builder)
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
| Search | `job.search(provider, ...)` | `SearchProvider` | `GeoDataFrame[AssetSchema]` |
| Prepare | `job.build_tasks(assets, task_builder, ...)` | search results + task builder | `Sequence[ExtractionTask]` |
| Execute | `job.execute(tasks, executor=...)` | tasks + executor | `GeoDataFrame[ArtifactSchema]` |

---

## Run the full pipeline in one block

Here is a complete, copy-pasteable example using the built-in config package:

```python
from aereo.builtins import GroupedTaskBuilder, SearchSTAC
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")

provider = SearchSTAC(...)
task_builder = GroupedTaskBuilder()

results = job.search(provider)
tasks = job.build_tasks(results, task_builder)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=2))

print(artifacts[["id", "grid_cell", "uri"]].head())
```

---

## Advanced: build everything in Python

If you need dynamic logic, construct the objects directly instead of loading a
config package.

```python
from datetime import datetime
from aereo.builtins import GroupedTaskBuilder, SearchSTAC, ReadODCSTAC, ReprojectODC, WriteGeoTIFF
from aereo.grid import GridConfig
from aereo.interfaces import PatchConfig, ExtractConfig
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob

search = SearchSTAC(
    stac_api_url="https://planetarycomputer.microsoft.com/api/stac/v1",
    collections={"sentinel-2-l2a": ["B04", "B08"]},
    intersects="config/aoi/chocon.geojson",
    start_datetime=datetime(2024, 1, 1),
    end_datetime=datetime(2024, 1, 10),
)

extract = ExtractConfig(
    read=ReadODCSTAC(),
    reproject=ReprojectODC(resampling="nearest"),
    write=WriteGeoTIFF(),
)

job = ExtractionJob(
    grid_config=GridConfig(target_grid_dist=10_000),
    patch_config=PatchConfig(resolution=10.0),
    output_uri="/tmp/aereo_python",
    extract=extract,
)

results = job.search(search)
tasks = job.build_tasks(results, GroupedTaskBuilder(), cells_per_task=50)
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
