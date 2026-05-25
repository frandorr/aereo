import datetime
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from aereo.interfaces import AerProfile
from numpy.typing import NDArray
from rasterio.crs import CRS
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling

# Known EOIDS key tokens — order matters for greedy matching
_EOIDS_KEYS = (
    "loc",
    "start",
    "end",
    "profile",
    "collection",
    "variable",
    "res",
    "desc",
)
_EOIDS_PATTERN = re.compile(
    r"(" + "|".join(_EOIDS_KEYS) + r")-"
    r"([^_]+(?:_[^-]+)*?)"
    r"(?=_(?:" + "|".join(_EOIDS_KEYS) + r")-|$)"
)


def build_eoids_path(
    local_dir: str | Path,
    profile: AerProfile,
    *,
    cell_id: str | None = None,
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
    derivative: str | None = None,
    desc: str | None = None,
    suffix: str = "tif",
    write_profile_meta: bool = True,
    **_kwargs: Any,
) -> Path:
    """Build an Earth Observation Imaging Data Structure (EOIDS) compliant file path.

    ``collection`` and ``variable`` are automatically derived from
    ``profile.collections`` and encoded in the filename (joined by ``+`` when
    multiple values exist).  The ``variable`` segment names the *set* of bands
    that will be stored as separate raster bands inside the single file — it
    does **not** cause the variables to be split into separate files.
    The directory hierarchy is flattened — there are no
    ``collection-<name>/`` or ``variable-<name>/`` subdirectories.

    On the first call for a given profile, a ``profile.json`` sidecar is written
    next to the data file so the full profile metadata can be recovered from disk.

    Args:
        local_dir: Root directory for the dataset.
        profile: The AerProfile used for extraction. Provides the profile name,
            default resolution, and collection/variable mapping.
        cell_id: Geographic cell identifier (e.g., '36D61L').
        start_time: Start time of the observation.
        end_time: End time of the observation.
        derivative: Name of the derivative pipeline (places file in derivatives/<name>/).
        desc: Custom descriptor for the file (e.g., 'cloudmask').
        suffix: File extension (default: 'tif').
        write_profile_meta: When *True* (the default), serialize the full
            ``AerProfile`` to ``profile.json`` in the profile directory on the
            first call.
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
    parts.append(f"profile-{profile.name}")

    # Derive collection and variable from profile.collections
    if profile.collections:
        collections = list(profile.collections.keys())
        variables = [v for vars_list in profile.collections.values() for v in vars_list]
        if collections:
            parts.append(f"collection-{('+').join(collections)}")
        if variables:
            parts.append(f"variable-{('+').join(variables)}")

    res_str = f"{int(profile.resolution)}m"
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

    base_dir = base_dir / f"profile-{profile.name}"

    base_dir.mkdir(parents=True, exist_ok=True)

    if write_profile_meta:
        profile_path = base_dir / "profile.json"
        if not profile_path.exists():
            profile_path.write_text(
                profile.model_dump_json(exclude={"downloader"}, indent=2),
                encoding="utf-8",
            )

    return base_dir / filename


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_eoids_filename(path: str | Path) -> dict[str, str]:
    """Extract metadata key-value pairs from an EOIDS-compliant filename.

    Values whose keys contain underscores (e.g. ``profile-goes_c01``) are handled
    correctly thanks to a greedy regex that stops only at the next recognised
    EOIDS key token.

    Args:
        path: Full path or bare filename following the EOIDS naming convention.

    Returns:
        Dictionary mapping EOIDS keys (``loc``, ``start``, ``end``, ``profile``,
        ``collection``, ``variable``, ``res``, ``desc``) to their string values.
        Only keys present in the filename are included.

    Example::

        >>> parse_eoids_filename(
        ...     "loc-0U38L_start-20260101T100022_end-20260101T100953_"
        ...     "profile-goes_east_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif"
        ... )
        {'loc': '0U38L', 'start': '20260101T100022', 'end': '20260101T100953',
         'profile': 'goes_east', 'collection': 'ABI-L1b-RadF',
         'variable': 'C01', 'res': '1000m'}
    """
    stem = Path(path).stem
    return dict(_EOIDS_PATTERN.findall(stem))


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _matches_filter(filter_value: str | None, file_value: str | None) -> bool:
    """Return *True* if *filter_value* overlaps with *file_value*.

    Both sides may use ``+`` concatenation (e.g. ``"C01+C02"``).  The filter
    matches when at least one component appears on both sides.
    """
    if filter_value is None:
        return True
    if file_value is None:
        return False
    filter_parts = set(filter_value.split("+"))
    file_parts = set(file_value.split("+"))
    return bool(filter_parts & file_parts)


def scan_eoids_dir(
    root_dir: str | Path,
    *,
    date: str | None = None,
    profile: str | None = None,
    collection: str | None = None,
    variable: str | None = None,
    cell_id: str | None = None,
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
        profile: Filter by profile name (e.g. ``"goes_c01"``).
        collection: Filter by collection value (e.g. ``"ABI-L1b-RadF"``).
        variable: Filter by variable value (e.g. ``"C01"``).
        cell_id: Filter by cell identifier (e.g. ``"0U38L"``).
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
        if profile is not None and meta.get("profile") != profile:
            continue
        if not _matches_filter(collection, meta.get("collection")):
            continue
        if not _matches_filter(variable, meta.get("variable")):
            continue
        if cell_id is not None and meta.get("loc") != cell_id.replace("_", ""):
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
    profile: str | None = None,
    collection: str | None = None,
    variable: str | None = None,
    cell_id: str | None = None,
    suffix: str = "tif",
) -> list[rasterio.DatasetReader]:
    """Open matching EOIDS tiles as rasterio dataset readers.

    Wraps :func:`scan_eoids_dir` and opens every matched file with
    :func:`rasterio.open`.  The caller is responsible for closing the
    returned datasets (or use them as context managers individually).

    Args:
        root_dir: Top-level EOIDS dataset directory.
        date: Filter by date string (e.g. ``"20260101"``).
        profile: Filter by profile name (e.g. ``"goes_c01"``).
        collection: Filter by collection (e.g. ``"ABI-L1b-RadF"``).
        variable: Filter by variable (e.g. ``"C01"``).
        cell_id: Filter by cell identifier (e.g. ``"0U38L"``).
        suffix: File extension to search for (default ``"tif"``).

    Returns:
        List of open :class:`rasterio.DatasetReader` objects.
    """
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


# ---------------------------------------------------------------------------
# Mosaicking
# ---------------------------------------------------------------------------


def mosaic_eoids_tiles(
    root_dir: str | Path,
    *,
    date: str | None = None,
    profile: str | None = None,
    collection: str | None = None,
    variable: str | None = None,
    cell_id: str | None = None,
    suffix: str = "tif",
    target_crs: str | CRS = "EPSG:4326",
    resampling: Resampling = Resampling.nearest,
    nodata: float | None = None,
    sort_by_coverage: bool = True,
    target_resolution: float | None = None,
) -> tuple[NDArray[np.floating[Any]], Affine, CRS]:
    """Load and mosaic EOIDS tiles into a single array in a common CRS.

    Grid cells produced by the extraction pipeline may live in different UTM
    zones.  This function reprojects every tile to *target_crs* on-the-fly
    using rasterio VRT warping, then merges them with
    :func:`rasterio.merge.merge`.

    Args:
        root_dir: Top-level EOIDS dataset directory.
        date: Filter by date string (e.g. ``"20260101"``).
        profile: Filter by profile name (e.g. ``"goes_c01"``).
        collection: Filter by collection (e.g. ``"ABI-L1b-RadF"``).
        variable: Filter by variable (e.g. ``"C01"``).
        cell_id: Filter by cell identifier (e.g. ``"0U38L"``).
        suffix: File extension to search for (default ``"tif"``).
        target_crs: The CRS to reproject all tiles into before merging.
            Defaults to ``"EPSG:4326"``.
        resampling: Resampling method for warping (default: nearest).
        nodata: Value to treat as nodata.  When *None*, the value embedded in
            each GeoTIFF is used (if available).
        sort_by_coverage: When ``True`` (default), tiles are ordered by
            descending valid-pixel count so that tiles with the most coverage
            are processed first by ``merge(method='first')``.  This prevents
            sparse tiles from blocking valid data in overlapping areas, but
            requires reading every tile into memory and can be very slow for
            large numbers of dense tiles.  Set to ``False`` to skip this step
            when all tiles are known to be fully valid (e.g. Sentinel-2).
        target_resolution: If provided, the mosaic is built at this output
            resolution (in the units of *target_crs*).  For example, ``100``
            builds a 100 m mosaic from 10 m source tiles.  This dramatically
            reduces memory use and compute time when you only need a coarse
            preview.  If *None* (default), the native source resolution is used.

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
        # Sort by descending valid-pixel count so that tiles with the most
        # coverage are processed first by merge(method='first').  This prevents
        # sparse tiles (which may contain NaN outside the actual swath) from
        # blocking valid data in overlapping areas.
        def _valid_count(entry: dict[str, Any]) -> int:
            with rasterio.open(entry["path"]) as src:
                data = src.read(1)
                return int(np.sum(~np.isnan(data) & (data != 0)))

        # Parallelise the reads — they are I/O-bound so threads work well.
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
