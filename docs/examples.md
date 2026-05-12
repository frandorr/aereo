# Examples

AER comes with a collection of runnable `.py` examples and a Jupyter notebook covering every supported sensor and workflow.

## Tutorial Sequence (`.py` examples)

The four numbered examples in `examples/extraction/` build on each other. Start with **01** and work upward:

| Example | Sensor | Plugins | Auth | Description |
|---------|--------|---------|------|-------------|
| [`01_goes_abi.py`](../examples/extraction/01_goes_abi.py) | GOES-19 ABI | aws-goes + satpy | None | Simplest AER pipeline: search, extract one cell, mosaic and plot |
| [`02_sentinel2_msi.py`](../examples/extraction/02_sentinel2_msi.py) | Sentinel-2 MSI | planetary-computer + odc-stac | None | First STAC-based workflow; true-color RGB composite |
| [`03_multi_constellation.py`](../examples/extraction/03_multi_constellation.py) | VIIRS + GOES + S3 OLCI | earthaccess + satpy / aws-goes + satpy | Earthdata 🔐 | Multi-sensor search, filter to one asset per sensor, side-by-side comparison |
| [`04_conform_to_ml.py`](../examples/extraction/04_conform_to_ml.py) | Sentinel-2 MSI | planetary-computer + odc-stac | None | Fixed-shape ML tensors with `conform_to`, padding, and montage visualization |

Each file uses `# %%` cell markers, so you can open them directly in VS Code, Jupyter, or PyCharm as notebooks.

## Notebook

| Notebook | Topic | Description |
|----------|-------|-------------|
| [`examples/grid/grid_filter_modes_demo.ipynb`](../examples/grid/grid_filter_modes_demo.ipynb) | Grid concepts | Interactive visualization of `intersection`, `within`, and `coverage` filtering modes |

## Full details

For run commands, disk-space estimates, common `AerProfile` errors and fixes, ML-ready `conform_to` formulas, and the complete directory structure, see [`examples/README.md`](../examples/README.md).

## Quick start

If you are new to AER, start with the [Quick Start](quickstart.md) guide for a complete copy-paste example.
