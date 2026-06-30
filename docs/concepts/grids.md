# Grid System

AEREO partitions the Earth into analysis-ready cells using the ESA Major TOM
grid conventions. Grid cells are an indexing concern of the orchestrator: they
are used to build artifact catalogs and to drive `reproject_mode="grid"`, but
they are no longer attached to individual `ExtractionTask` objects.

---

## GridDefinition

A `GridDefinition` creates the raw cells that intersect any polygon. It is used
internally when the orchestrator builds the grid over the effective AOI.

```python
from aereo.grid import GridDefinition
from shapely.geometry import box

# Create a grid with 256 km cells and no overlap
grid_def = GridDefinition(d=256000, overlap=False)

# Build raw cells over an AOI
aoi = box(-63.5, -41.0, -57.0, -34.0)
raw_cells = list(grid_def.generate_raw_cells(aoi))
print(f"Generated {len(raw_cells)} cells")
```

| Parameter | Description |
|-----------|-------------|
| `d` | Cell size in **metres** (e.g., `256000` for 256 km). |
| `overlap` | Whether to generate additional overlapping cells shifted by half a cell. Useful for mosaicking to avoid seams. |

Each cell receives a Major TOM-style ID such as `922U_249R`. Overlapping cells
append `_OV` (e.g., `922U_249R_OV`).

### `grid_dist` vs. `resolution`

These two parameters are independent and easy to confuse:

| Parameter | Units | What it controls | Example |
|-----------|-------|------------------|---------|
| `grid_dist` | metres | Size of each **grid cell** | `256000` → 256 km square cell |
| `resolution` | metres | Size of each **output pixel** | `10` → 10 m pixel |

A 256 km cell at 500 m resolution is roughly a 512 × 512 pixel tile. If you set
`grid_dist=500` by mistake, every cell collapses to a single pixel.

### Overlapping cells

Set `overlap=True` when you want neighbouring cells to share a 50 % border:

```python
grid_def = GridDefinition(d=128000, overlap=True)
raw_cells = list(grid_def.generate_raw_cells(aoi))
primary = [c for c in raw_cells if c[2]]
overlap = [c for c in raw_cells if not c[2]]
```

Overlapping cells are generated **in addition to** primary cells. They are
offset by half the cell size in both latitude and longitude. This is helpful for
algorithms that need continuous coverage without edge artifacts.

---

## GridCell

`GridCell` is the orchestrator's view of a geographic cell: a WGS84 polygon,
a target pixel resolution, and helpers for UTM projection and `odc-geo`
`GeoBox` creation.

```python
from aereo.grid import build_grid_cells
from shapely.geometry import box

cells = build_grid_cells(
    aoi=box(-63.5, -41.0, -57.0, -34.0),
    grid_dist=10000,
    resolution=10.0,
    margin=0.0,
)
print(f"Generated {len(cells)} cells")
```

| Attribute | Description |
|-----------|-------------|
| `id` | Major TOM-style cell identifier. |
| `d` | Cell size in metres (`grid_dist`). |
| `cell_geometry` | Cell polygon in WGS84. |
| `resolution` | Target pixel resolution in metres. |
| `margin` | Optional buffer applied when the cell was built. |
| `padding` | Optional pixel padding for tensor alignment. |
| `conform_to` | Optional fixed output shape `(height, width)`. |

---

## Area definition

Convert a cell to an `odc.geo.GeoBox` for raster operations:

```python
geobox = cell.geobox
```

The `geobox` is computed lazily from the cell's UTM footprint, resolution,
margin, padding, and optional `conform_to` shape. In `reproject_mode="grid"`,
the orchestrator passes this geobox to the reprojector for each cell.

---

## Conform mode

When `conform_to=(height, width)` is provided, every cell in a batch is padded
to the same pixel dimensions — essential for stacking arrays in ML pipelines.

---

## Grid filtering modes

During execution, AEREO intersects the generated grid with the **written file
footprint** (or with the asset geometry when building the grid for
`reproject_mode="grid"`). Any cell that touches the footprint is kept, producing
one artifact row per cell.

---

## Troubleshooting

### Grid cell size looks wrong

`grid_dist` is a required integer cell size in metres. If your AOI is a small
city, a 256 km cell will include a lot of surrounding area.

**Fix:** Use a smaller cell size:

```python
grid_dist = 50_000  # 50 km cells
```

Remember: `grid_dist` controls the **cell** size in metres, while
`resolution` controls the **pixel** size in metres. A 256 km cell at
500 m resolution is roughly a 512 × 512 pixel tile.

### CRS mismatch between adjacent cells

Each grid cell is naturally projected to its local UTM zone. Adjacent cells may
have different CRSs. When you mosaic them, AEREO reprojects everything to a
common CRS, but if you open individual cells manually, expect varying CRS
values.

### `conform_to` vs natural shapes

By default, each cell's output matches its natural UTM footprint, so adjacent
cells tile edge-to-edge with no gaps.

When you set `conform_to=(H, W)`, every cell is padded to the same pixel
dimensions with `NaN` fill. This is essential for ML pipelines but creates
padding borders that do not exist in natural-shape mode.

| Mode | Use case | Edge behaviour |
|------|----------|----------------|
| Natural (default) | Visualization, mosaics | Seamless tiling |
| `conform_to` | ML training, fixed tensors | `NaN` padding where data is missing |

Remember: `conform_to` is `(height, width)`, matching rasterio's
`(bands, height, width)` convention.
