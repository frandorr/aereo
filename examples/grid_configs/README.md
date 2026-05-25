# Example Grid Configurations

These JSON files are reference `GridConfig` instances that match the grid settings used in the numbered extraction examples.

They demonstrate the principle that **grid parameters are a user concern**: the framework never silently chooses a cell size, and every profile in a run shares the same grid.

## Usage

```python
from aereo.interfaces import GridConfig

grid = GridConfig.from_json("grid_configs/sentinel2_50km.json")

tasks = client.prepare_for_extraction(
    results,
    grid_config=grid,
    profiles=profiles,
    cells_per_chunk=5,
)
```

## Files

| File | `target_grid_dist` | `target_grid_margin` | Used in example |
|------|-------------------:|---------------------:|:----------------|
| `goes_512km.json` | 512 000 m | 0.0 % | [`01_minimal_goes.py`](../extraction/01_minimal_goes.py), [`02_goes_mosaic_plot.py`](../extraction/02_goes_mosaic_plot.py) |
| `goes_256km.json` | 256 000 m | 0.0 % | [`04_multi_constellation.py`](../extraction/04_multi_constellation.py), legacy examples |
| `sentinel2_50km.json` | 50 000 m | 6.8 % | [`03_sentinel2_msi.py`](../extraction/03_sentinel2_msi.py) |
| `ml_patch_2_56km.json` | 2 560 m | 0.0 % | [`05_conform_to_ml.py`](../extraction/05_conform_to_ml.py) |
