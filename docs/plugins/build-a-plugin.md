# Build a Plugin

AerEO plugins are plain Python functions with typed signatures. You do not need
to subclass a framework class or learn a custom API.

Every plugin is discovered through the `aereo.plugins` entry-point group. The
entry-point name prefix tells AerEO which pipeline stage the function belongs
to:

| Prefix | Stage |
|---|---|
| `search_` | Search provider |
| `task_builder_` | Task builder |
| `read_` | Reader |
| `reproject_` | Reprojector |
| `process_` | Processor |
| `write_` | Writer |

A stage plugin is responsible for one thing: satisfying the input/output
contract defined by its Protocol. AerEO uses schemas to make sure data moving
between stages has the expected shape.

---

## A simple processor

Here is a processor that scales every band by a constant factor:

```python
import xarray as xr
from pydantic import validate_call


@validate_call
def scale(ds: xr.Dataset, factor: float = 1.0) -> xr.Dataset:
    """Scale all data variables by ``factor``."""
    return ds * factor
```

The `@validate_call` decorator gives you Pydantic validation of arguments for
free.

Register it under the `aereo.plugins` group in your package's `pyproject.toml`:

```toml
[project.entry-points."aereo.plugins"]
process_scale = "my_package.plugins:scale"
```

Use it in a job:

```python
from aereo.pipeline import ExtractionJob
from my_package.plugins import scale

job = ExtractionJob(
    name="scaled",
    grid_dist=10_000,
    output_uri="/tmp/scaled",
    read=read_odc_stac,
    postprocess=scale,
    write=write_geotiff,
    target_aoi=aoi,
)
```

---

## Stage-by-stage reference

The tabs below show the Protocol, example code, entry-point registration, and
schema contract for every stage.

=== "Search provider"

    **Protocol:** `aereo.interfaces.SearchProvider`

    ```python
    from datetime import datetime
    from typing import Any, Mapping, Sequence

    import geopandas as gpd
    from pandera.typing.geopandas import GeoDataFrame
    from pydantic import validate_call
    from shapely.geometry.base import BaseGeometry

    from aereo.schemas import AssetSchema


    @validate_call(config={"arbitrary_types_allowed": True})
    def search_my_catalog(
        collections: Mapping[str, Sequence[str]] | Sequence[str] | None,
        intersects: BaseGeometry | None,
        start_datetime: datetime | None,
        end_datetime: datetime | None,
        **kwargs: Any,
    ) -> GeoDataFrame[AssetSchema]:
        """Return a GeoDataFrame that satisfies AssetSchema."""
        # ... query the catalog ...
        gdf = gpd.GeoDataFrame(..., geometry="geometry")
        return AssetSchema.validate(gdf)
    ```

    **Entry point:**

    ```toml
    [project.entry-points."aereo.plugins"]
    search_my_catalog = "my_package.plugins:search_my_catalog"
    ```

    **Schema contract:** the returned `GeoDataFrame` must satisfy
    [`AssetSchema`](../api/schemas.md). Required columns include `id`,
    `collection`, `geometry`, `start_time`, `end_time`, and `href`.

    **Testing:**

    ```python
    from my_package.plugins import search_my_catalog
    from shapely.geometry import box

    gdf = search_my_catalog(
        collections={"my-collection": ["band1"]},
        intersects=box(-68.9, -39.4, -68.6, -39.2),
        start_datetime=None,
        end_datetime=None,
    )
    assert "geometry" in gdf.columns
    assert len(gdf) > 0
    ```

=== "Reader"

    **Protocol:** `aereo.interfaces.Reader`

    ```python
    from typing import Any

    import xarray as xr
    from pydantic import validate_call

    from aereo.interfaces import ExtractionTask


    @validate_call(config={"arbitrary_types_allowed": True})
    def read_my_format(task: ExtractionTask, **kwargs: Any) -> xr.Dataset:
        """Open the task assets into an xr.Dataset."""
        uris = task.uris
        # ... open files, select bands, return a dataset ...
        return xr.Dataset(...)
    ```

    **Entry point:**

    ```toml
    [project.entry-points."aereo.plugins"]
    read_my_format = "my_package.plugins:read_my_format"
    ```

    **Schema contract:** input is an [`ExtractionTask`](../api/interfaces.md).
    Use `task.uris`, `task.bbox`, `task.stac_items`, or `task.aoi` as needed.
    Output must be an `xr.Dataset`.

    **Testing:**

    ```python
    from my_package.plugins import read_my_format

    ds = read_my_format(dummy_task)
    assert isinstance(ds, xr.Dataset)
    ```

=== "Processor"

    **Protocol:** `aereo.interfaces.Processor`

    ```python
    import xarray as xr
    from pydantic import validate_call


    @validate_call
    def scale(ds: xr.Dataset, factor: float = 1.0) -> xr.Dataset:
        """Scale all data variables by ``factor``."""
        return ds * factor
    ```

    **Entry point:**

    ```toml
    [project.entry-points."aereo.plugins"]
    process_scale = "my_package.plugins:scale"
    ```

    **Schema contract:** input/output is `xr.Dataset`. Processors can be used as
    `preprocess` (before reprojection) or `postprocess` (after reprojection).

    **Testing:**

    ```python
    import xarray as xr
    from my_package.plugins import scale

    ds = xr.Dataset({"red": (["y", "x"], [[1, 2], [3, 4]])})
    out = scale(ds, factor=2.0)
    assert out["red"].values.tolist() == [[2, 4], [6, 8]]
    ```

=== "Reprojector"

    **Protocol:** `aereo.interfaces.Reprojector`

    ```python
    from typing import Any

    import xarray as xr
    from pydantic import validate_call


    @validate_call(config={"arbitrary_types_allowed": True})
    def reproject_my_format(ds: xr.Dataset, **kwargs: Any) -> xr.Dataset:
        """Reproject/resample a dataset to the target definition."""
        # kwargs may include geobox, crs, resolution, etc.
        # ... warp/resample ...
        return ds
    ```

    **Entry point:**

    ```toml
    [project.entry-points."aereo.plugins"]
    reproject_my_format = "my_package.plugins:reproject_my_format"
    ```

    **Schema contract:** input/output is `xr.Dataset`. When
    `ExtractionJob.reproject_mode` is `"grid"`, AerEO injects a `geobox` kwarg
    for each Major TOM cell. For `"raw"` mode, provide `crs` and `resolution`
    via kwargs or `functools.partial`.

    **Testing:**

    ```python
    from my_package.plugins import reproject_my_format

    out = reproject_my_format(ds, crs="EPSG:32633", resolution=10.0)
    assert out.rio.crs.to_epsg() == 32633
    ```

=== "Writer"

    **Protocol:** `aereo.interfaces.Writer`

    ```python
    from pathlib import Path
    from typing import Any

    import xarray as xr
    from pydantic import validate_call


    @validate_call(config={"arbitrary_types_allowed": True})
    def write_my_format(ds: xr.Dataset, path: str, **kwargs: Any) -> str:
        """Write a dataset to ``path`` and return the written path."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # ... write ...
        return path
    ```

    **Entry point:**

    ```toml
    [project.entry-points."aereo.plugins"]
    write_my_format = "my_package.plugins:write_my_format"
    ```

    **Schema contract:** input is a single time-slice `xr.Dataset` and a target
    path. Output must be the path/URI that was written. AerEO collects these
    paths into the `ArtifactSchema` catalog.

    **Testing:**

    ```python
    from my_package.plugins import write_my_format

    path = write_my_format(ds, "/tmp/test.tif")
    assert Path(path).exists()
    ```

=== "Task builder"

    **Protocol:** `aereo.interfaces.TaskBuilder`

    ```python
    from typing import Any, Sequence

    from pandera.typing.geopandas import GeoDataFrame
    from pydantic import validate_call

    from aereo.interfaces import ExtractionTask
    from aereo.pipeline import ExtractionJob
    from aereo.schemas import AssetSchema


    @validate_call(config={"arbitrary_types_allowed": True})
    def build_my_tasks(
        search_results: GeoDataFrame[AssetSchema],
        job: ExtractionJob,
        **kwargs: Any,
    ) -> Sequence[ExtractionTask]:
        """Turn search results into ExtractionTask objects."""
        # ... group, chunk, build tasks ...
        return [...]
    ```

    **Entry point:**

    ```toml
    [project.entry-points."aereo.plugins"]
    task_builder_my = "my_package.plugins:build_my_tasks"
    ```

    **Schema contract:** input is a `GeoDataFrame[AssetSchema]` plus the parent
    `ExtractionJob`. Output is a sequence of
    [`ExtractionTask`](../api/interfaces.md) objects. AerEO's built-in
    `build_grouped_tasks` groups assets by time and native CRS; you can follow
    the same pattern or build a custom grouping strategy.

    **Testing:**

    ```python
    from my_package.plugins import build_my_tasks

    tasks = build_my_tasks(assets, job)
    assert len(tasks) > 0
    assert all(isinstance(t, ExtractionTask) for t in tasks)
    ```

---

## Publishing and discovering

Once your plugin is registered, install it in the same environment as AerEO:

```bash
pip install -e .
```

Your plugin will appear in the registry and can be used in config packages and
Python code:

```python
from aereo.registry import AereoRegistry

registry = AereoRegistry()
print("search_my_catalog" in registry.list_all_params())
print(registry.get_plugin_params("search_my_catalog"))
```

---

## Integration testing

For integration tests, pass the plugin to an `ExtractionJob` and run a tiny AOI
with `DRY_RUN=true` to validate config loading, or run a real extraction on a
small geometry:

```python
from aereo.executors import LocalExecutor
from aereo.pipeline import ExtractionJob
from my_package.plugins import scale

job = ExtractionJob(
    name="test",
    grid_dist=10_000,
    output_uri="/tmp/test",
    read=read_odc_stac,
    postprocess=scale,
    write=write_geotiff,
    target_aoi=small_aoi,
)

assets = job.search(search_stac, ...)
tasks = job.build_tasks(assets, build_grouped_tasks)
artifacts = job.execute(tasks, executor=LocalExecutor(workers=1))
```

---

## Next steps

- [Plugin System Overview](overview.md) — how AerEO discovers and loads plugins.
- [API: Interfaces](../api/interfaces.md) — full Protocol definitions.
- [API: Schemas](../api/schemas.md) — `AssetSchema`, `GridSchema`, `ArtifactSchema`.
