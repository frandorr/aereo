import datetime
from pathlib import Path


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
