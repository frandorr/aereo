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

### Opt-in UTM inference for `reproject_mode="raw"`

When you know the dataset fits comfortably inside a single UTM zone but do not
want to look up the EPSG code yourself, set `crs: "utm"` in the reproject
config:

```yaml
reproject:
  _target_: aereo.builtins.reproject.reproject_odc
  _partial_: true
  crs: "utm"        # infer the UTM zone from the dataset footprint
  resolution: 10.0
reproject_mode: raw
```

The orchestrator derives the footprint from the dataset after it has been read
and preprocessed, picks the UTM zone from the centroid, and passes the concrete
EPSG code to the reprojector. The inferred EPSG is logged at `info`
(`raw_reproject_inferred_crs`) so you can pin it explicitly if desired.

**Why this is opt-in.** A single centroid-picked UTM zone is *wrong* for wide
footprints (e.g. continental mosaics, GOES full disk) and for polar areas, where
it silently distorts data at the edges. For those cases use
`reproject_mode="grid"`, which infers UTM per Major TOM cell. As a guard:

- If the footprint spans more than 6° of longitude, a `warning` is emitted that
the data crosses multiple UTM zones and an explicit CRS or grid mode may give
better results.
- If the footprint is polar or otherwise outside the UTM zone range, inference
raises a `ValueError` telling you to configure an explicit `crs` or use grid
mode.

If `crs` is omitted entirely in raw mode, `ExtractionJob` validation now fails
fast with a clear error pointing to the three options: an explicit CRS,
`crs: "utm"`, or `reproject_mode="grid"`.

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
    grid_resolution=10.0,
    write=write_geotiff,
    target_aoi=aoi,
)
```

## Resolution and margin

- `grid_resolution` — target pixel size in metres of the output grid. Required
  for `reproject_mode="grid"`, where the orchestrator uses it to build each
  cell's GeoBox, and also used for artifact indexing. (The legacy key
  `resolution` is still accepted as an alias.)
- `resolution` inside the `reproject:` block — a keyword argument bound to the
  reprojection plugin, used only in `reproject_mode="raw"` so the plugin can
  build a target GeoBox itself (together with `crs`).
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
