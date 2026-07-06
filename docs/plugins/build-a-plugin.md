# Build a Plugin

AEREO plugins are plain Python functions with typed signatures. You do not need
to subclass a framework class or learn a custom API.

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

## Register the plugin

Add an entry point under the `aereo.plugins` group in your package's
`pyproject.toml`:

```toml
[project.entry-points."aereo.plugins"]
process_scale = "my_package.plugins:scale"
```

The `process_` prefix tells AEREO this is a processor.

## Use it

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

## Plugin protocols

Each stage has a `Protocol` in `aereo.interfaces`:

| Protocol | Signature shape |
|---|---|
| `SearchProvider` | `(collections, intersects, start_datetime, end_datetime, **kwargs) -> GeoDataFrame[AssetSchema]` |
| `Reader` | `(task: ExtractionTask, **kwargs) -> xr.Dataset` |
| `Processor` | `(ds: xr.Dataset, **kwargs) -> xr.Dataset` |
| `Reprojector` | `(ds: xr.Dataset, **kwargs) -> xr.Dataset` |
| `Writer` | `(ds: xr.Dataset, path: str, **kwargs) -> str` |
| `TaskBuilder` | `(assets, job, **kwargs) -> Sequence[ExtractionTask]` |

Because these are protocols, your plugin can be a regular function.

## Testing

Write a unit test that calls the function directly:

```python
import xarray as xr
from my_package.plugins import scale

ds = xr.Dataset({"red": (["y", "x"], [[1, 2], [3, 4]])})
out = scale(ds, factor=2.0)
assert out["red"].values.tolist() == [[2, 4], [6, 8]]
```

For integration tests, pass the plugin to an `ExtractionJob` and run a tiny
AOI with `DRY_RUN=true`.

## Publishing

Once your plugin is registered, install it in the same environment as AEREO:

```bash
pip install -e .
aereo action=plugins
```

Your plugin will appear in the list and can be used in config packages, the
CLI, and Python code.
