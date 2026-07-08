# Processing

Processors are plain Python functions that transform an `xr.Dataset`. They can
run before reprojection (`preprocess`) or after reprojection (`postprocess`).

## Built-in processors

| Function | Stage | What it does |
|---|---|---|
| `select_bands` | preprocess | Keep only the bands you need. |
| `qa_mask` | preprocess | Apply a quality-assessment mask. |
| `ndvi` | postprocess | Compute the Normalized Difference Vegetation Index. |
| `ndwi` | postprocess | Compute the Normalized Difference Water Index. |
| `normalize` | postprocess | Scale values to a fixed range. |
| `composite` | postprocess | Build a temporal or band composite. |

## Preprocessing vs postprocessing

```mermaid
flowchart LR
    read["read"] --> preprocess["preprocess"]
    preprocess --> reproject["reproject"]
    reproject --> postprocess["postprocess"]
    postprocess --> write["write"]
```

- **Preprocess** runs on the native-resolution dataset before warping. Use it
  for band selection, QA masking, and other operations that are cheaper in the
  native projection.
- **Postprocess** runs after reprojection, when all pixels share the same CRS
  and resolution. Use it for indices, normalization, and composites.

## Example: NDVI

```python
from aereo.builtins import ndvi
from aereo.pipeline import ExtractionJob

job = ExtractionJob(
    name="ndvi_demo",
    grid_dist=10_000,
    output_uri="/tmp/ndvi",
    read=read_odc_stac,
    postprocess=ndvi,
    write=write_geotiff,
    target_aoi=aoi,
)
```

The [Sentinel-2 NDVI](../examples/01b-sentinel2-ndvi.ipynb) tutorial shows a
full pipeline.

## Writing a custom processor

A processor is a function `(ds: xr.Dataset, **kwargs) -> xr.Dataset`. For
example:

```python
import xarray as xr

def scale(ds: xr.Dataset, factor: float = 1.0) -> xr.Dataset:
    return ds * factor
```

For production use, decorate it with `@validate_call` and register it under the
`aereo.plugins` entry-point group with a `process_` prefix. See
[Build a Plugin](../plugins/build-a-plugin.md) for the Processor Protocol,
schema contract, and a complete stage-by-stage reference.
