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
print(job.search)        # SearchProvider instance
print(job.grid_config)   # GridConfig instance
print(job.patch_config)  # PatchConfig instance
print(job.extract)       # ExtractConfig instance
```

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
from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend

client = AereoClient()

# 1. Search
results = client.search(job.search)
print(f"Found {len(results)} assets")

# 2. Prepare tasks
tasks = client.build_tasks(results, job=job)
print(f"Prepared {len(tasks)} tasks")

# 3. Execute
backend = LocalProcessBackend(max_workers=2)
artifacts = client.execute_tasks(tasks, backend=backend)
print(f"Extracted {len(artifacts)} artifacts")
```

Each step returns a typed GeoDataFrame:

| Step | Method | Input | Output |
|------|--------|-------|--------|
| Search | `client.search(search_provider)` | `SearchProvider` | `GeoDataFrame[AssetSchema]` |
| Prepare | `client.build_tasks(search_results, job=job)` | search results + job | `Sequence[ExtractionTask]` |
| Execute | `client.execute_tasks(tasks, backend=backend)` | tasks + backend | `GeoDataFrame[ArtifactSchema]` |

---

## Run the full pipeline in one block

Here is a complete, copy-pasteable example using the built-in config package:

```python
from aereo.pipeline import ExtractionJob
from aereo.client import AereoClient
from aereo.backends import LocalProcessBackend

job = ExtractionJob.load_from_config("examples/config", config_name="job_sentinel2")
client = AereoClient()

results = client.search(job.search)
tasks = client.build_tasks(results, job=job)
artifacts = client.execute_tasks(tasks, backend=LocalProcessBackend(max_workers=2))

print(artifacts[["id", "grid_cell", "uri"]].head())
```

---

## Advanced: build everything in Python

If you need dynamic logic, construct the objects directly instead of loading a
config package.

```python
from datetime import datetime
from aereo.client import AereoClient
from aereo.builtins import SearchSTAC, ReadODCSTAC, ReprojectODC, WriteGeoTIFF
from aereo.grid import GridConfig
from aereo.interfaces import PatchConfig, ExtractConfig
from aereo.pipeline import ExtractionJob
from aereo.builtins import GroupedTaskBuilder

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
    search=search,
    task_builder=GroupedTaskBuilder(cells_per_task=50),
    grid_config=GridConfig(target_grid_dist=10_000),
    patch_config=PatchConfig(resolution=10.0),
    output_uri="/tmp/aereo_python",
    extract=extract,
)

client = AereoClient()
results = client.search(job.search)
tasks = client.build_tasks(results, job=job)
artifacts = client.execute_tasks(tasks, job=job)
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
