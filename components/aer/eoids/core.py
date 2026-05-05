import datetime
import re
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from numpy.typing import NDArray
from rasterio.crs import CRS
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling

# Known EOIDS key tokens — order matters for greedy matching
_EOIDS_KEYS = ("loc", "start", "end", "sat", "prod", "band", "res", "desc")
_EOIDS_PATTERN = re.compile(
    r"(" + "|".join(_EOIDS_KEYS) + r")-"
    r"([^_]+(?:_[^-]+)*?)"
    r"(?=_(?:" + "|".join(_EOIDS_KEYS) + r")-|$)"
)


def build_eoids_path(
    local_dir: str | Path,
    cell_id: str | None = None,
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
    satellite: str | None = None,
    product: str | None = None,
    band: str | None = None,
    resolution: str | int | None = None,
    derivative: str | None = None,
    desc: str | None = None,
    suffix: str = "tif",
) -> Path:
    """Build an Earth Observation Imaging Data Structure (EOIDS) compliant file path.

    This follows a BIDS-like approach where metadata is explicitly encoded in
    hierarchical folders and key-value pairs in the filename. It allows omitting
    parameters (e.g. for static masks without time) and supports derived data.

    Args:
        local_dir: Root directory for the dataset.
        cell_id: Geographic cell identifier (e.g., '36D61L').
        start_time: Start time of the observation.
        end_time: End time of the observation.
        satellite: Satellite or platform identifier (e.g., 'goes_east').
        product: Product identifier (e.g., 'RadF').
        band: Band identifier (e.g., 'C01').
        resolution: Spatial resolution (e.g., 1000 or '1000m').
        derivative: Name of the derivative pipeline (places file in derivatives/<name>/).
        desc: Custom descriptor for the file (e.g., 'cloudmask').
        suffix: File extension (default: 'tif').
    """
    parts: list[str] = []

    if cell_id:
        safe_cell = str(cell_id).replace("_", "")
        parts.append(f"loc-{safe_cell}")
    else:
        safe_cell = None

    if start_time:
        parts.append(f"start-{start_time.strftime('%Y%m%dT%H%M%S')}")
    if end_time:
        parts.append(f"end-{end_time.strftime('%Y%m%dT%H%M%S')}")
    if satellite:
        parts.append(f"sat-{satellite}")
    if product:
        parts.append(f"prod-{product}")
    if band:
        parts.append(f"band-{band}")
    if resolution is not None:
        if isinstance(resolution, int) or str(resolution).isdigit():
            res_str = f"{resolution}m"
        else:
            res_str = str(resolution)
        parts.append(f"res-{res_str}")
    if desc:
        parts.append(f"desc-{desc}")

    safe_suffix = suffix.lstrip(".")
    if not parts:
        filename = f"unnamed.{safe_suffix}"
    else:
        filename = "_".join(parts) + f".{safe_suffix}"

    base_dir = Path(local_dir)

    if derivative:
        base_dir = base_dir / "derivatives" / derivative

    if safe_cell:
        base_dir = base_dir / f"loc-{safe_cell}"

    if start_time:
        base_dir = base_dir / f"date-{start_time.strftime('%Y%m%d')}"

    if satellite:
        base_dir = base_dir / f"sat-{satellite}"

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / filename


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_eoids_filename(path: str | Path) -> dict[str, str]:
    """Extract metadata key-value pairs from an EOIDS-compliant filename.

    Values whose keys contain underscores (e.g. ``sat-goes_east``) are handled
    correctly thanks to a greedy regex that stops only at the next recognised
    EOIDS key token.

    Args:
        path: Full path or bare filename following the EOIDS naming convention.

    Returns:
        Dictionary mapping EOIDS keys (``loc``, ``start``, ``end``, ``sat``,
        ``prod``, ``band``, ``res``, ``desc``) to their string values.
        Only keys present in the filename are included.

    Example::

        >>> parse_eoids_filename(
        ...     "loc-0U38L_start-20260101T100022_end-20260101T100953_"
        ...     "sat-goes_east_prod-RadF_band-C01_res-1000m.tif"
        ... )
        {'loc': '0U38L', 'start': '20260101T100022', 'end': '20260101T100953',
         'sat': 'goes_east', 'prod': 'RadF', 'band': 'C01', 'res': '1000m'}
    """
    stem = Path(path).stem
    return dict(_EOIDS_PATTERN.findall(stem))


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def scan_eoids_dir(
    root_dir: str | Path,
    *,
    date: str | None = None,
    satellite: str | None = None,
    band: str | None = None,
    cell_id: str | None = None,
    product: str | None = None,
    suffix: str = "tif",
) -> list[dict[str, Any]]:
    """Recursively discover EOIDS files under *root_dir* with optional filtering.

    The function walks the directory tree, finds files matching ``*.<suffix>``,
    parses each filename, and returns only those entries whose metadata matches
    **all** of the supplied filter arguments.

    Args:
        root_dir: Top-level EOIDS dataset directory.
        date: Filter by date string as it appears in the directory hierarchy
            (e.g. ``"20260101"``).
        satellite: Filter by satellite value (e.g. ``"goes_east"``).
        band: Filter by band value (e.g. ``"C01"``).
        cell_id: Filter by cell identifier (e.g. ``"0U38L"``).
        product: Filter by product identifier (e.g. ``"RadF"``).
        suffix: File extension to search for (default ``"tif"``).

    Returns:
        A list of dicts, each containing all parsed EOIDS key-value pairs
        **plus** ``"path"`` (a :class:`~pathlib.Path` to the file) and
        ``"date"`` (extracted from the directory hierarchy).
    """
    root = Path(root_dir)
    safe_suffix = suffix.lstrip(".")
    results: list[dict[str, Any]] = []

    for filepath in root.rglob(f"*.{safe_suffix}"):
        meta = parse_eoids_filename(filepath.name)
        if not meta:
            continue

        # Extract the date from the directory hierarchy (date-YYYYMMDD)
        file_date: str | None = None
        for parent in filepath.parents:
            if parent.name.startswith("date-"):
                file_date = parent.name[5:]
                break

        entry: dict[str, Any] = {**meta, "path": filepath, "date": file_date}

        # Apply filters — skip if any filter doesn't match
        if date is not None and file_date != date:
            continue
        if satellite is not None and meta.get("sat") != satellite:
            continue
        if band is not None and meta.get("band") != band:
            continue
        if cell_id is not None and meta.get("loc") != cell_id.replace("_", ""):
            continue
        if product is not None and meta.get("prod") != product:
            continue

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_eoids_tiles(
    root_dir: str | Path,
    *,
    date: str | None = None,
    satellite: str | None = None,
    band: str | None = None,
    cell_id: str | None = None,
    product: str | None = None,
    suffix: str = "tif",
) -> list[rasterio.DatasetReader]:
    """Open matching EOIDS tiles as rasterio dataset readers.

    Wraps :func:`scan_eoids_dir` and opens every matched file with
    :func:`rasterio.open`.  The caller is responsible for closing the
    returned datasets (or use them as context managers individually).

    Args:
        root_dir: Top-level EOIDS dataset directory.
        date: Filter by date string (e.g. ``"20260101"``).
        satellite: Filter by satellite (e.g. ``"goes_east"``).
        band: Filter by band (e.g. ``"C01"``).
        cell_id: Filter by cell identifier (e.g. ``"0U38L"``).
        product: Filter by product (e.g. ``"RadF"``).
        suffix: File extension to search for (default ``"tif"``).

    Returns:
        List of open :class:`rasterio.DatasetReader` objects.
    """
    entries = scan_eoids_dir(
        root_dir,
        date=date,
        satellite=satellite,
        band=band,
        cell_id=cell_id,
        product=product,
        suffix=suffix,
    )
    return [rasterio.open(e["path"]) for e in entries]


# ---------------------------------------------------------------------------
# Mosaicking
# ---------------------------------------------------------------------------


def mosaic_eoids_tiles(
    root_dir: str | Path,
    *,
    date: str | None = None,
    satellite: str | None = None,
    band: str | None = None,
    cell_id: str | None = None,
    product: str | None = None,
    suffix: str = "tif",
    target_crs: str | CRS = "EPSG:4326",
    resampling: Resampling = Resampling.nearest,
    nodata: float | None = None,
) -> tuple[NDArray[np.floating[Any]], Affine, CRS]:
    """Load and mosaic EOIDS tiles into a single array in a common CRS.

    Grid cells produced by the extraction pipeline may live in different UTM
    zones.  This function reprojects every tile to *target_crs* on-the-fly
    using rasterio VRT warping, then merges them with
    :func:`rasterio.merge.merge`.

    Args:
        root_dir: Top-level EOIDS dataset directory.
        date: Filter by date string (e.g. ``"20260101"``).
        satellite: Filter by satellite (e.g. ``"goes_east"``).
        band: Filter by band (e.g. ``"C01"``).
        cell_id: Filter by cell identifier (e.g. ``"0U38L"``).
        product: Filter by product (e.g. ``"RadF"``).
        suffix: File extension to search for (default ``"tif"``).
        target_crs: The CRS to reproject all tiles into before merging.
            Defaults to ``"EPSG:4326"``.
        resampling: Resampling method for warping (default: nearest).
        nodata: Value to treat as nodata.  When *None*, the value embedded in
            each GeoTIFF is used (if available).

    Returns:
        A 3-tuple of ``(mosaic, transform, crs)`` where *mosaic* is a
        ``(bands, height, width)`` numpy array, *transform* is the
        :class:`~rasterio.transform.Affine` geotransform for the mosaic, and
        *crs* is the output :class:`~rasterio.crs.CRS`.

    Raises:
        FileNotFoundError: If no tiles match the given filters.
    """
    entries = scan_eoids_dir(
        root_dir,
        date=date,
        satellite=satellite,
        band=band,
        cell_id=cell_id,
        product=product,
        suffix=suffix,
    )
    if not entries:
        raise FileNotFoundError(
            f"No EOIDS tiles found in '{root_dir}' matching the given filters."
        )

    dst_crs = CRS.from_user_input(target_crs)

    # Sort by descending valid-pixel count so that tiles with the most
    # coverage are processed first by merge(method='first').  This prevents
    # sparse tiles (which may contain NaN outside the actual swath) from
    # blocking valid data in overlapping areas.
    def _valid_count(entry: dict[str, Any]) -> int:
        with rasterio.open(entry["path"]) as src:
            data = src.read(1)
            return int(np.sum(~np.isnan(data) & (data != 0)))

    entries.sort(key=_valid_count, reverse=True)

    datasets: list[WarpedVRT | rasterio.DatasetReader] = []
    opened: list[rasterio.DatasetReader] = []
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

        mosaic, out_transform = merge(datasets, nodata=nodata)
    finally:
        for ds in datasets:
            if isinstance(ds, WarpedVRT):
                ds.close()
        for ds in opened:
            ds.close()

    return mosaic, out_transform, dst_crs
