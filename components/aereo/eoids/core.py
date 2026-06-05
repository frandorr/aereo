"""Core implementation of EOIDS file naming, path generation, scanning, and loading utilities.

Handles the naming structure of Earth Observation Image Datasets (EOIDS) and integrates
them with Major TOM format parquet files.
"""

import datetime
import re
from pathlib import Path
from typing import Any, Sequence

import geopandas as gpd
import pandas as pd

# Removed AereoProfile import

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

_EOIDS_DT_FMT = "%Y%m%dT%H%M%S"
_EOIDS_DATE_FMT = "%Y%m%d"


def _sanitize_cell(cell_id: str) -> str:
    return str(cell_id).replace("_", "")


def _normalize_suffix(suffix: str) -> str:
    return suffix.lstrip(".")


def _write_profile_meta(
    base_dir: Path, profile_name: str, meta: dict[str, Any] | None = None
) -> None:
    profile_path = base_dir / "profile.json"
    if not profile_path.exists() and meta is not None:
        import json

        profile_path.write_text(
            json.dumps(meta, indent=2),
            encoding="utf-8",
        )


def build_eoids_path(
    local_dir: str | Path,
    profile_name: str,
    resolution: float,
    *,
    collections: Sequence[str] | None = None,
    variables: Sequence[str] | None = None,
    cell_id: str | None = None,
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
    derivative: str | None = None,
    desc: str | None = None,
    suffix: str = "tif",
    write_profile_meta: bool = True,
    meta_dict: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> Path:
    """Build an Earth Observation Imaging Data Structure (EOIDS) compliant file path.

    ``collection`` and ``variable`` are encoded in the filename (joined by ``+`` when
    multiple values exist).  The ``variable`` segment names the *set* of bands
    that will be stored as separate raster bands inside the single file — it
    does **not** cause the variables to be split into separate files.
    The directory hierarchy is flattened — there are no
    ``collection-<name>/`` or ``variable-<name>/`` subdirectories.

    On the first call for a given profile, a ``profile.json`` sidecar is written
    next to the data file so the full profile metadata can be recovered from disk.

    Args:
        local_dir: Root directory for the dataset.
        profile_name: The name of the profile.
        resolution: Target resolution.
        collections: Sequence of collection identifiers.
        variables: Sequence of variables/bands.
        cell_id: Geographic cell identifier (e.g., '36D61L').
        start_time: Start time of the observation.
        end_time: End time of the observation.
        derivative: Name of the derivative pipeline (places file in derivatives/<name>/).
        desc: Custom descriptor for the file (e.g., 'cloudmask').
        suffix: File extension (default: 'tif').
        write_profile_meta: When *True* (the default), serialize the full
            metadata to ``profile.json`` in the profile directory on the
            first call.
        meta_dict: Optional metadata dictionary to save as profile.json.
    """
    parts: list[str] = []

    safe_cell = _sanitize_cell(cell_id) if cell_id else None
    if safe_cell:
        parts.append(f"loc-{safe_cell}")

    if start_time:
        parts.append(f"start-{start_time.strftime(_EOIDS_DT_FMT)}")
    if end_time:
        parts.append(f"end-{end_time.strftime(_EOIDS_DT_FMT)}")
    parts.append(f"profile-{profile_name}")

    if collections:
        parts.append(f"collection-{('+').join(collections)}")
    if variables:
        parts.append(f"variable-{('+').join(variables)}")

    res_str = f"{int(resolution)}m"
    parts.append(f"res-{res_str}")
    if desc:
        parts.append(f"desc-{desc}")

    safe_suffix = _normalize_suffix(suffix)
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
        base_dir = base_dir / f"date-{start_time.strftime(_EOIDS_DATE_FMT)}"

    base_dir = base_dir / f"profile-{profile_name}"

    base_dir.mkdir(parents=True, exist_ok=True)

    if write_profile_meta:
        _write_profile_meta(base_dir, profile_name, meta_dict)

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

    Args:
        filter_value: The filter pattern, or *None* to match all.
        file_value: The file's value to test, or *None*.

    Returns:
        *True* when at least one ``+``-separated component exists in both
        strings, or when *filter_value* is *None*.
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
    safe_suffix = _normalize_suffix(suffix)
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
        if cell_id is not None and meta.get("loc") != _sanitize_cell(cell_id):
            continue

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# EOIDSLoader — Major TOM dataset integration
# ---------------------------------------------------------------------------


class EOIDSLoader:
    """Load and manage Major TOM-format EOIDS datasets from parquet files."""

    def __init__(self, dataset_path: str | Path) -> None:
        """Initialise loader with a path to a Major TOM parquet dataset.

        Args:
            dataset_path: Path to the parquet file or directory containing
                the Major TOM dataset.
        """
        self.dataset_path = Path(dataset_path)

    @classmethod
    def from_parquet(cls, path: str | Path) -> "EOIDSLoader":
        """Create an EOIDSLoader from a parquet file.

        Args:
            path: Path to the parquet file.

        Returns:
            An EOIDSLoader instance.
        """
        return cls(path)

    def load(self) -> gpd.GeoDataFrame:
        """Load the dataset as a GeoDataFrame.

        Returns:
            GeoDataFrame containing the Major TOM dataset.
        """
        return gpd.read_parquet(self.dataset_path)

    def merge_with_extraction(
        self,
        existing_dataset: gpd.GeoDataFrame,
        new_artifacts: gpd.GeoDataFrame,
        dedup_by: tuple[str, ...] = ("grid_cell", "collection", "start_time"),
    ) -> gpd.GeoDataFrame:
        """Merge new extraction artifacts into an existing Major TOM dataset.

        Duplicates are identified by the *dedup_by* columns. When a conflict
        is found, the new artifact takes precedence.

        Args:
            existing_dataset: Existing Major TOM dataset loaded from parquet.
            new_artifacts: New artifacts produced by an extraction run.
            dedup_by: Columns used to identify duplicate rows.

        Returns:
            Merged GeoDataFrame with duplicates removed.
        """
        combined = pd.concat([existing_dataset, new_artifacts], ignore_index=True)

        # Determine which columns are available for deduplication
        available_cols = [c for c in dedup_by if c in combined.columns]
        if available_cols:
            combined = combined.drop_duplicates(subset=available_cols, keep="last")

        return gpd.GeoDataFrame(combined, crs=existing_dataset.crs)
