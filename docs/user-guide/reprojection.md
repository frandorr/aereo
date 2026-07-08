# Reprojection

AerEO can write data in its native projection or reproject it to a target CRS
and resolution. The choice is controlled by the `reproject` and
`reproject_mode` fields of `ExtractionJob`.

## Reprojection modes

| Mode | What it does | Best for |
|---|---|---|
| `raw` | Reproject the whole dataset once and write one file. | Small AOIs, single-CRS scenes, quick mosaics. |
| `grid` | Reproject each Major TOM cell to its local UTM geobox and write one file per cell. | Multi-sensor stacking, ML patches, large AOIs. |
| omitted | Write in the native projection and still intersect with the grid. | When you want the original sensor geometry. |

## Configuring reprojection

```yaml
name: sentinel2_demo
grid_dist: 10000
output_uri: /tmp/aereo_demo
resolution: 10.0
margin: 0.0
reproject:
  _target_: aereo.builtins.reproject.reproject_odc
  crs: EPSG:32633
  resolution: 10.0
reproject_mode: raw
read:
  _target_: aereo.builtins.read.read_odc_stac
write:
  _target_: aereo.builtins.write.write_geotiff
```

In pure Python:

```python
from aereo.builtins import reproject_odc
from aereo.pipeline import ExtractionJob

job = ExtractionJob(
    name="demo",
    grid_dist=10_000,
    output_uri="/tmp/demo",
    read=read_odc_stac,
    reproject=reproject_odc,
    reproject_mode="grid",
    write=write_geotiff,
    target_aoi=aoi,
)
```

## Resolution and margin

- `resolution` — target pixel size in metres. Used by the grid builder and by
  reprojectors that accept it.
- `margin` / `crop_buffer` — extra buffer around cells or scenes to avoid edge
  effects.
- `grid_cells_margin` — additional margin used when intersecting cells with the
  AOI.

## Swath data

Sensors like VIIRS and Sentinel-3 are often stored as swaths (2-D lat/lon
arrays). For these data you usually need the built-in `reproject_swath` helper,
which uses `pyresample` under the hood. Install it with the `swath` extra:

```bash
uv add aereo[swath]
# or
pip install aereo[swath]
```

See the [VIIRS](../examples/02-viirs.ipynb) and
[Sentinel-3](../examples/03-sentinel3.ipynb) tutorials, and the
[Configuration](../configuration/yaml-schema.md) reference for all
`reproject` and `reproject_mode` fields.
