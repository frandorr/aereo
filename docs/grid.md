# Grid System

AER's grid system partitions the Earth into analysis-ready cells.

## GridCell

The fundamental unit of extraction. A `GridCell` represents a geographic area with a known coordinate reference system, resolution, and pixel alignment.

```python
from aer.grid import GridCell
from shapely.geometry import Polygon

cell = GridCell(
    d=10000,  # 10 km resolution
    geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
    cell_id="loc-16D20L",
)
```

## Area Definition

Convert a cell to an `odc.geo.GeoBox` for raster operations:

```python
geobox = cell.area_def(resolution=100, anchor="edge")
```

| Parameter | Description |
|-----------|-------------|
| `resolution` | Target pixel size in CRS units |
| `anchor` | Pixel alignment: `"edge"` (top-left) or `"center"` |
| `tight` | Disable pixel snapping for exact extents |
| `conform_to` | Force uniform `(width, height)` across a batch |

## Conform Mode

When `conform_to=(w, h)` is provided, `tight=True` is enforced internally so every cell in a batch has the exact same pixel dimensions — essential for stacking arrays.
