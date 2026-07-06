# Grids

AEREO uses the [Major TOM grid](https://github.com/majortom-eg) to turn any AOI
into a set of equal-area, globally consistent cells. Outputs are indexed by
cell ID, so scenes from different sensors line up without manual reprojection.

## Major TOM grid basics

The grid divides the world into fixed cells. When you set `grid_dist`, AEREO
selects the cells that intersect your AOI and uses them as the extraction
framework.

```python
from aereo.pipeline import ExtractionJob

job = ExtractionJob(
    name="demo",
    grid_dist=10_000,  # 10 km cells
    output_uri="/tmp/demo",
    target_aoi=aoi,
    read=read_odc_stac,
    write=write_geotiff,
)
```

## Grid cell size

| `grid_dist` | Use case |
|---|---|
| `1_000` | Very high resolution, small-area ML patches. |
| `10_000` | Common default for Sentinel-2 regional extractions. |
| `50_000` | Large-area composites and quick overviews. |

Smaller cells mean more tasks and smaller files; larger cells mean fewer tasks
and larger files.

## How cells become tasks

```mermaid
flowchart LR
    AOI["AOI polygon"] --> Grid["Major TOM grid"]
    Grid --> Cells["Intersecting cells"]
    Cells --> Group["Group by time + native CRS"]
    Group --> Tasks["ExtractionTask list"]
```

`build_grouped_tasks` intersects the AOI with the grid, then groups the
resulting cells by acquisition time and native CRS. Each group becomes one or
more `ExtractionTask` objects, depending on `cells_per_task`.

## Reprojecting to a cell's local UTM geobox

When `reproject_mode` is `"grid"`, AEREO reprojects each cell to its local UTM
zone before writing. This keeps pixels square and avoids warping a whole scene
to a single CRS when it spans multiple UTM zones.

See [Reprojection](reprojection.md) for details.

## Grid helpers

```python
from aereo.grid import build_grid_cells, intersect_cells

cells = build_grid_cells(aoi, grid_dist=10_000)
selected = intersect_cells(cells, aoi)
```

These helpers are useful when you want to inspect the grid before running an
extraction.
