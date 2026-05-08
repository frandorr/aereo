#!/usr/bin/env python
# coding: utf-8

# # Single-Cell Multi-Constellation Comparison
#
# Find a central Buenos Aires grid cell that has valid data across **all constellations**
# on a **common date**, then render them side-by-side with per-cell averages.

# ## Setup

from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

plt.rcParams["figure.dpi"] = 150
plt.rcParams["font.size"] = 9


# ## Configuration

# Script is in visualization/; extracted data lives in examples/
BASE_DIR = Path(__file__).resolve().parent.parent

CONSTELLATIONS = [
    {
        "label": "GOES-19 ABI",
        "dir": "extraction/extract_neuquen_goes",
        "cmap": "viridis",
        "band": "C02",
    },
    {
        "label": "MODIS Terra",
        "dir": "extraction/extract_neuquen_modis",
        "cmap": "plasma",
        "band": "1",
    },
    {
        "label": "VIIRS NOAA-21",
        "dir": "extraction/extract_neuquen_viirs",
        "cmap": "magma",
        "band": "I01",
    },
    {
        "label": "Sentinel-3 OLCI",
        "dir": "extraction/extract_neuquen_sentinel3",
        "cmap": "cividis",
        "band": "Oa08",
    },
]

VALIDITY_THRESHOLD = 0.90  # >90% valid pixels required


# ## Helpers


def list_cells(root_dir):
    """Return set of cell IDs (e.g. 'loc-16D21L') found under root_dir."""
    cells = set()
    if not root_dir.exists():
        return cells
    for loc_dir in root_dir.rglob("loc-*"):
        if loc_dir.is_dir():
            cells.add(loc_dir.name)
    return cells


def extract_date_from_tiff(tiff_path):
    """Extract YYYYMMDD date string from a TIFF filename."""
    # Try 'date-YYYYMMDD' pattern first
    m = re.search(r"date-(\d{8})", tiff_path.name)
    if m:
        return m.group(1)
    # Fallback: try 'start-YYYYMMDD' or 'YYYYMMDD' in filename
    m = re.search(r"(?:start-)?(\d{8})T", tiff_path.name)
    if m:
        return m.group(1)
    return None


def get_cell_tiffs_by_date(root_dir, cell_id, band):
    """
    Return dict mapping date_str -> list of (valid_ratio, avg_value, tiff_path)
    for all TIFFs matching the cell and band.
    """
    cell_dirs = list(root_dir.rglob(cell_id))
    if not cell_dirs:
        return {}
    cell_dir = cell_dirs[0]

    tiffs = list(cell_dir.rglob(f"*band-{band}*.tif"))
    result = {}
    for tiff_path in tiffs:
        date = extract_date_from_tiff(tiff_path)
        if date is None:
            continue
        with rasterio.open(tiff_path) as src:
            data = src.read(1).astype(np.float32)
            invalid = np.isnan(data) | (data == 0)
            if band in ("I01", "I04"):
                invalid |= data == 65535
            valid = ~invalid
            valid_ratio = valid.sum() / valid.size
            avg_value = float(np.nanmean(data[valid])) if valid.any() else np.nan
            result.setdefault(date, []).append((valid_ratio, avg_value, tiff_path))
    return result


def get_best_tiff_for_date(root_dir, cell_id, band, date):
    """Return (valid_ratio, avg_value, tiff_path) for the best TIFF on a given date."""
    by_date = get_cell_tiffs_by_date(root_dir, cell_id, band)
    if date not in by_date:
        return 0.0, np.nan, None
    # Pick the one with highest validity
    best = max(by_date[date], key=lambda x: x[0])
    return best


def find_common_dates(cell_id):
    """
    Find all dates where every constellation has at least one file
    for the given cell, and return a list of (date, min_validity, details_dict)
    sorted by min_validity descending.
    """
    all_dates = set()
    per_constellation = {}

    for cfg in CONSTELLATIONS:
        root = BASE_DIR / cfg["dir"]
        by_date = get_cell_tiffs_by_date(root, cell_id, cfg["band"])
        per_constellation[cfg["label"]] = by_date
        all_dates.update(by_date.keys())

    common_dates = []
    for date in sorted(all_dates):
        details = {}
        min_validity = 1.0
        has_all = True
        for cfg in CONSTELLATIONS:
            label = cfg["label"]
            if date not in per_constellation[label]:
                has_all = False
                break
            best = max(per_constellation[label][date], key=lambda x: x[0])
            details[label] = best
            min_validity = min(min_validity, best[0])
        if has_all:
            common_dates.append((date, min_validity, details))

    common_dates.sort(key=lambda x: x[1], reverse=True)
    return common_dates


# ## Find all available cells

all_cells_by_constellation = {}
for cfg in CONSTELLATIONS:
    root = BASE_DIR / cfg["dir"]
    cells = list_cells(root)
    all_cells_by_constellation[cfg["label"]] = cells
    valid_count = len(cells)
    print(f"{cfg['label']}: {valid_count} cells found")

cell_sets = [cells for cells in all_cells_by_constellation.values()]
common_cells = set.intersection(*cell_sets) if cell_sets else set()
print(f"\nCommon cells across all constellations: {len(common_cells)}")
print(sorted(common_cells))


# ## Pick the best cell + date combination

best_candidate = None
best_min_validity = -1.0

for cell_id in common_cells:
    common_dates = find_common_dates(cell_id)
    for date, min_validity, details in common_dates:
        if min_validity >= VALIDITY_THRESHOLD and min_validity > best_min_validity:
            best_min_validity = min_validity
            best_candidate = (cell_id, date, details)

if best_candidate is None:
    # Fallback: pick any common date with the highest min validity
    for cell_id in common_cells:
        common_dates = find_common_dates(cell_id)
        if common_dates:
            date, min_validity, details = common_dates[0]
            if min_validity > best_min_validity:
                best_min_validity = min_validity
                best_candidate = (cell_id, date, details)

if best_candidate is None:
    raise ValueError("No common cell/date found across all constellations!")

BEST_CELL, BEST_DATE, BEST_DETAILS = best_candidate
print(f"\nSelected cell: {BEST_CELL}")
print(f"Selected date: {BEST_DATE}")
print(f"Minimum validity across constellations: {best_min_validity:.1%}")
for cfg in CONSTELLATIONS:
    ratio, avg, path = BEST_DETAILS[cfg["label"]]
    print(f"  {cfg['label']}: {ratio:.1%} valid, avg={avg:.2f}")


# ## Render the constellations for the selected cell and date


def load_cell_tiff_for_date(cfg, cell_id, date):
    """Load the TIFF for a specific cell, constellation, and date."""
    root = BASE_DIR / cfg["dir"]
    ratio, avg, tiff_path = get_best_tiff_for_date(root, cell_id, cfg["band"], date)
    if tiff_path is None:
        return None, None, None
    with rasterio.open(tiff_path) as src:
        data = src.read(1).astype(np.float32)
        invalid = np.isnan(data) | (data == 0)
        if cfg["band"] in ("I01", "I04"):
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
cols = 2
rows = (n + cols - 1) // cols

fig, axes = plt.subplots(rows, cols, figsize=(7 * cols, 6 * rows), squeeze=False)
fig.suptitle(
    f"Buenos Aires — Single Cell Comparison\n{BEST_CELL} | Date: {BEST_DATE}",
    fontsize=16,
    fontweight="bold",
    y=1.02,
)

for ax, cfg in zip(axes.flat, CONSTELLATIONS):
    data, vmin, vmax = load_cell_tiff_for_date(cfg, BEST_CELL, BEST_DATE)
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

summary = []
for cfg in CONSTELLATIONS:
    ratio, avg, path = BEST_DETAILS[cfg["label"]]
    data, _, _ = load_cell_tiff_for_date(cfg, BEST_CELL, BEST_DATE)
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
