# Grid System

AEREO partitions the Earth into analysis-ready cells using the ESA Major TOM
grid conventions. Every extraction task is tied to an `ExtractionPatch`, and the
set of patches that cover an AOI is produced by a `GridDefinition` plus a
`PatchConfig`.

---

## GridDefinition

A `GridDefinition` creates the raw cells that intersect any polygon. It is the
first thing built during `build_tasks` (unless the extractor provides its own
defaults).

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

### `grid_dist` vs. `patch_config.resolution`

These two parameters are independent and easy to confuse:

| Parameter | Units | What it controls | Example |
|-----------|-------|------------------|---------|
| `grid_dist` | metres | Size of each **grid cell** | `256000` → 256 km square cell |
| `patch_config.resolution` | metres | Size of each **output pixel** inside the cell | `10` → 10 m pixel |

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

## ExtractionPatch

The fundamental unit of extraction. An `ExtractionPatch` represents a geographic
cell with a known coordinate reference system, resolution, and pixel alignment.
It is created from a `GridDefinition` and a `PatchConfig`:

```python
from aereo.grid import GridDefinition, generate_extraction_patches
from aereo.interfaces import PatchConfig
from shapely.geometry import box

grid_def = GridDefinition(d=10000)
patch_config = PatchConfig(resolution=10.0, margin=10.0)
patches = generate_extraction_patches(box(-63.5, -41.0, -57.0, -34.0), grid_def, patch_config)
print(f"Generated {len(patches)} patches")
```

---

## Area definition

Convert a patch to an `odc.geo.GeoBox` for raster operations:

```python
geobox = patch.geobox
```

The `geobox` is computed lazily from the patch's UTM footprint, resolution,
margin, padding, and optional `conform_to` shape.

---

## Conform mode

When `patch_config.conform_to=(w, h)` is provided, `tight=True` is enforced
internally so every patch in a batch has the exact same pixel dimensions —
essential for stacking arrays.

---

## Grid filtering modes

During `build_tasks`, AEREO intersects the generated grid with the **asset
geometry** (the actual satellite swath footprint, not the AOI). Any cell that
touches the asset geometry is kept.

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
`patch_config.resolution` controls the **pixel** size in metres. A 256 km cell at
500 m resolution is roughly a 512 × 512 pixel tile.

### CRS mismatch between adjacent cells

Each grid cell is naturally projected to its local UTM zone. Adjacent cells may
have different CRSs. When you mosaic them, AEREO reprojects everything to a
common CRS, but if you open individual cells manually, expect varying CRS
values.

### `conform_to` vs natural shapes

By default, each cell's output matches its natural UTM footprint, so adjacent
cells tile edge-to-edge with no gaps.

When you set `conform_to=(W, H)`, every cell is padded to the same pixel
dimensions with `NaN` fill. This is essential for ML pipelines but creates
padding borders that do not exist in natural-shape mode.

| Mode | Use case | Edge behaviour |
|------|----------|----------------|
| Natural (default) | Visualization, mosaics | Seamless tiling |
| `conform_to` | ML training, fixed tensors | `NaN` padding where data is missing |

Remember: `conform_to` is `(width, height)`, matching rasterio's
`(bands, height, width)` convention.
