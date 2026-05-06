#!/usr/bin/env python
# coding: utf-8

# # Single-Cell Multi-Constellation Comparison
#
# Find a central Buenos Aires grid cell that has valid data across **all 5 constellations**, then render them side-by-side with per-cell averages.
#
# Scoring maximizes VIIRS + Sentinel-2 + Sentinel-3 validity (the limiting sensors).

# ## Setup

# In[ ]:


from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

plt.rcParams["figure.dpi"] = 150
plt.rcParams["font.size"] = 9


# ## Configuration

# In[ ]:


# Notebook is in visualization/; extracted data lives in examples/
BASE_DIR = Path(__file__).resolve().parent.parent

CONSTELLATIONS = [
    {
        "label": "GOES-19 ABI",
        "dir": "extract_buenos_aires_goes",
        "cmap": "viridis",
        "band": "C07",
    },
    {
        "label": "MODIS Terra",
        "dir": "extract_buenos_aires_modis",
        "cmap": "plasma",
        "band": "31",
    },
    {
        "label": "VIIRS NOAA-21",
        "dir": "extract_buenos_aires_viirs",
        "cmap": "magma",
        "band": "I04",
    },
    {
        "label": "Sentinel-3 OLCI",
        "dir": "extract_buenos_aires_sentinel3",
        "cmap": "cividis",
        "band": "Oa04",
    },
]


# ## Find all available cells and their validity scores

# In[ ]:


def list_cells(root_dir):
    """Return set of cell IDs (e.g. 'loc-15D21L') found under root_dir."""
    cells = set()
    if not root_dir.exists():
        return cells
    for loc_dir in root_dir.rglob("loc-*"):
        if loc_dir.is_dir():
            cells.add(loc_dir.name)
    return cells


def cell_validity(root_dir, cell_id, band):
    """
    Return (valid_ratio, avg_value, tiff_path) for a given cell.
    Scans all dates/satellites under the cell directory.
    """
    cell_dirs = list(root_dir.rglob(cell_id))
    if not cell_dirs:
        return 0.0, np.nan, None
    cell_dir = cell_dirs[0]

    tiffs = list(cell_dir.rglob(f"*band-{band}*.tif"))
    if not tiffs:
        return 0.0, np.nan, None

    tiff_path = tiffs[0]
    with rasterio.open(tiff_path) as src:
        data = src.read(1).astype(np.float32)
        invalid = np.isnan(data) | (data == 0)
        if band == "I04":
            invalid |= data == 65535
        valid = ~invalid
        valid_ratio = valid.sum() / valid.size
        avg_value = float(np.nanmean(data[valid])) if valid.any() else np.nan
    return valid_ratio, avg_value, tiff_path


all_cells_by_constellation = {}
for cfg in CONSTELLATIONS:
    root = BASE_DIR / cfg["dir"]
    cells = list_cells(root)
    all_cells_by_constellation[cfg["label"]] = {}
    for cell_id in cells:
        ratio, avg, path = cell_validity(root, cell_id, cfg["band"])
        all_cells_by_constellation[cfg["label"]][cell_id] = (ratio, avg, path)
    valid_count = sum(
        1 for v in all_cells_by_constellation[cfg["label"]].values() if v[0] > 0
    )
    print(f"{cfg['label']}: {len(cells)} cells, {valid_count} with data")

cell_sets = [set(d.keys()) for d in all_cells_by_constellation.values()]
common_cells = set.intersection(*cell_sets) if cell_sets else set()
print(f"\nCommon cells across all constellations: {len(common_cells)}")
print(sorted(common_cells))


# ## Pick the best cell — maximize VIIRS + S2 + S3 validity

# In[ ]:


def score_cell(cell_id):
    """
    Score = sum of valid ratios for VIIRS + S3.
    GOES and MODIS are ignored since they have ~100% coverage everywhere.
    Higher = more valid pixels in the limiting sensors.
    """
    score = 0.0
    for cfg in CONSTELLATIONS:
        if cfg["label"] in ("VIIRS NOAA-21", "Sentinel-3 OLCI"):
            ratio, _, _ = all_cells_by_constellation[cfg["label"]].get(
                cell_id, (0.0, np.nan, None)
            )
            score += ratio
    return score


scored = [(cell_id, score_cell(cell_id)) for cell_id in common_cells]
scored.sort(key=lambda x: x[1], reverse=True)

print("Top 10 common cells by VIIRS+S3 validity sum:")
for cell_id, score in scored[:10]:
    print(f"  {cell_id}: sum_valid={score:.1%}")
    for cfg in CONSTELLATIONS:
        ratio, avg, _ = all_cells_by_constellation[cfg["label"]][cell_id]
        print(f"    {cfg['label']}: {ratio:.1%} valid, avg={avg:.2f}")

if scored:
    BEST_CELL = scored[0][0]
    print(f"\nSelected cell: {BEST_CELL}")
else:
    raise ValueError("No common cell found across all constellations!")


# ## Render the 5 constellations for the selected cell

# In[ ]:


def load_cell_tiff(cfg, cell_id):
    """Load the TIFF for a specific cell and constellation."""
    root = BASE_DIR / cfg["dir"]
    _, _, tiff_path = cell_validity(root, cell_id, cfg["band"])
    if tiff_path is None:
        return None, None, None
    with rasterio.open(tiff_path) as src:
        data = src.read(1).astype(np.float32)
        invalid = np.isnan(data) | (data == 0)
        if cfg["band"] == "I04":
            invalid |= data == 65535
        data = np.where(invalid, np.nan, data)
        valid = data[~np.isnan(data)]
        if len(valid) == 0:
            vmin, vmax = 0, 1
        else:
            vmin, vmax = np.percentile(valid, [1, 99])
            if vmin == vmax:
                vmin, vmax = valid.min(), valid.max()
        return data, float(vmin), float(vmax)


n = len(CONSTELLATIONS)
cols = 3
rows = (n + cols - 1) // cols

fig, axes = plt.subplots(rows, cols, figsize=(7 * cols, 6 * rows), squeeze=False)
fig.suptitle(
    f"Buenos Aires — Single Cell Comparison\n{BEST_CELL}",
    fontsize=16,
    fontweight="bold",
    y=1.02,
)

for ax, cfg in zip(axes.flat, CONSTELLATIONS):
    data, vmin, vmax = load_cell_tiff(cfg, BEST_CELL)
    if data is None:
        ax.set_title(f"{cfg['label']}\n(not found)")
        ax.axis("off")
        continue

    valid = data[~np.isnan(data)]
    avg = float(np.mean(valid)) if len(valid) > 0 else np.nan
    valid_pct = len(valid) / data.size * 100

    im = ax.imshow(
        data,
        cmap=cfg["cmap"],
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
    )
    ax.set_title(
        f"{cfg['label']}\nBand {cfg['band']} | Avg={avg:.2f} | {valid_pct:.0f}% valid",
        fontsize=11,
        fontweight="bold",
    )
    ax.set_xlabel("Column")
    ax.set_ylabel("Row")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

for ax in axes.flat[n:]:
    ax.axis("off")

plt.tight_layout()
plt.savefig(
    "single_cell_comparison.png", dpi=200, bbox_inches="tight", facecolor="white"
)
plt.show()

print("Saved: single_cell_comparison.png")


# ## Summary table

# In[ ]:


summary = []
for cfg in CONSTELLATIONS:
    ratio, avg, path = all_cells_by_constellation[cfg["label"]][BEST_CELL]
    data, _, _ = load_cell_tiff(cfg, BEST_CELL)
    valid_count = (~np.isnan(data)).sum() if data is not None else 0
    total_count = data.size if data is not None else 0
    summary.append(
        {
            "Constellation": cfg["label"],
            "Band": cfg["band"],
            "Valid %": f"{ratio * 100:.1f}%",
            "Valid Pixels": f"{valid_count:,} / {total_count:,}",
            "Cell Average": f"{avg:.3f}" if not np.isnan(avg) else "N/A",
        }
    )

df = pd.DataFrame(summary)
print(df.to_string(index=False))
