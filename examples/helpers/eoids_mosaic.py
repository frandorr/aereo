"""EOIDS tile loading and mosaicking helpers (non-core, for examples only)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from aereo.eoids import scan_eoids_dir
from numpy.typing import NDArray


def load_eoids_tiles(
    root_dir: str | Path,
    *,
    date: str | None = None,
    profile: str | None = None,
    collection: str | None = None,
    variable: str | None = None,
    cell_id: str | None = None,
    suffix: str = "tif",
) -> list:
    """Open matching EOIDS tiles as rasterio dataset readers.

    Wraps :func:`scan_eoids_dir` and opens every matched file with
    :func:`rasterio.open`.  The caller is responsible for closing the
    returned datasets (or use them as context managers individually).
    """
    import rasterio

    entries = scan_eoids_dir(
        root_dir,
        date=date,
        profile=profile,
        collection=collection,
        variable=variable,
        cell_id=cell_id,
        suffix=suffix,
    )
    return [rasterio.open(e["path"]) for e in entries]


def mosaic_eoids_tiles(
    root_dir: str | Path,
    *,
    date: str | None = None,
    profile: str | None = None,
    collection: str | None = None,
    variable: str | None = None,
    cell_id: str | None = None,
    suffix: str = "tif",
    target_crs: str = "EPSG:4326",
    resampling=None,
    nodata: float | None = None,
    sort_by_coverage: bool = True,
    target_resolution: float | None = None,
) -> tuple[NDArray[np.floating[Any]], Any, Any]:
    """Load and mosaic EOIDS tiles into a single array in a common CRS.

    Grid cells produced by the extraction pipeline may live in different UTM
    zones.  This function reprojects every tile to *target_crs* on-the-fly
    using rasterio VRT warping, then merges them with
    :func:`rasterio.merge.merge`.
    """
    import rasterio
    from rasterio.crs import CRS
    from rasterio.merge import merge
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import Resampling

    if resampling is None:
        resampling = Resampling.nearest

    entries = scan_eoids_dir(
        root_dir,
        date=date,
        profile=profile,
        collection=collection,
        variable=variable,
        cell_id=cell_id,
        suffix=suffix,
    )
    if not entries:
        raise FileNotFoundError(
            f"No EOIDS tiles found in '{root_dir}' matching the given filters."
        )

    dst_crs = CRS.from_user_input(target_crs)

    if sort_by_coverage:

        def _valid_count(entry: dict[str, Any]) -> int:
            with rasterio.open(entry["path"]) as src:
                data = src.read(1)
                return int(np.sum(~np.isnan(data) & (data != 0)))

        if len(entries) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(entries))) as ex:
                counts = list(ex.map(_valid_count, entries))
            entries = [
                e
                for _, e in sorted(
                    zip(counts, entries), key=lambda ce: ce[0], reverse=True
                )
            ]
        else:
            entries.sort(key=_valid_count, reverse=True)

    datasets: list = []
    opened: list = []
    try:
        for entry in entries:
            src = rasterio.open(entry["path"])
            opened.append(src)

            nd = nodata if nodata is not None else src.nodata

            if src.crs == dst_crs:
                datasets.append(src)
            else:
                vrt = WarpedVRT(
                    src,
                    crs=dst_crs,
                    resampling=resampling,
                    nodata=nd,
                )
                datasets.append(vrt)

        merge_kwargs: dict[str, Any] = {"nodata": nodata}
        if target_resolution is not None:
            merge_kwargs["res"] = target_resolution
        mosaic, out_transform = merge(datasets, **merge_kwargs)
    finally:
        for ds in datasets:
            if isinstance(ds, WarpedVRT):
                ds.close()
        for ds in opened:
            ds.close()

    return mosaic, out_transform, dst_crs
