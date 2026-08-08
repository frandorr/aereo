"""Core implementation of the job configuration snapshot guard.

Writes a canonical YAML snapshot of an :class:`~aereo.pipeline.ExtractionJob`'s
output-defining configuration to ``{output_uri}/job-<name>/job.yaml`` on first
run and validates subsequent runs against it, raising
:class:`JobConfigMismatchError` when the same job name is reused with a
different configuration.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING, Any

import fsspec
import yaml
from aereo.eoids import sanitize_job_name
from shapely.geometry.base import BaseGeometry
from structlog import get_logger

if TYPE_CHECKING:
    from aereo.pipeline import ExtractionJob

logger = get_logger()

SNAPSHOT_FILENAME = "job.yaml"

# Job scalar fields that define how output data is produced. ``name`` (the
# lookup key), ``output_uri`` (where, not what), ``overwrite`` (runtime
# behaviour), and ``target_aoi`` (extent) are deliberately excluded.
_SCALAR_FIELDS = (
    "grid_dist",
    "grid_resolution",
    "margin",
    "crop_buffer",
    "grid_cells_margin",
    "alignment_resolution",
    "reproject_mode",
)

_CALLABLE_FIELDS = (
    "read",
    "write",
    "preprocess",
    "postprocess",
    "reproject",
    "search_provider",
    "task_builder",
)

# Keyword names that select *which* scenes/cells are produced rather than how
# data is transformed. Excluded recursively so that extending a dataset's time
# range or AOI does not trip the guard.
_EXTENT_KEYS = frozenset(
    {"intersects", "aoi", "target_aoi", "start_datetime", "end_datetime", "datetime"}
)


class JobConfigMismatchError(ValueError):
    """Raised when an existing job snapshot conflicts with the current job.

    Attributes:
        job_name: Name of the conflicting job.
        snapshot_uri: URI of the existing snapshot file.
        diffs: Human-readable lines describing each differing value.
    """

    def __init__(self, job_name: str, snapshot_uri: str, diffs: list[str]) -> None:
        """Initialise the error with the conflicting job details."""
        self.job_name = job_name
        self.snapshot_uri = snapshot_uri
        self.diffs = diffs
        diff_block = "\n".join(f"  {line}" for line in diffs)
        super().__init__(
            f"Job {job_name!r} already exists at {snapshot_uri} with a "
            f"different configuration:\n{diff_block}\n"
            "Rename the job or delete the existing job directory to proceed."
        )


def _callable_target(fn: Any) -> str:
    """Return a stable ``module.qualname`` identifier for a callable."""
    module = getattr(fn, "__module__", None)
    qualname = getattr(fn, "__qualname__", None)
    if module and qualname:
        return f"{module}.{qualname}"
    return type(fn).__qualname__


def _canonicalize_value(value: Any) -> Any:
    """Recursively convert *value* into YAML-safe, comparable primitives.

    Dicts are sorted and stripped of extent keys; tuples become lists;
    geometries become WKT; callables become ``{_target_: ...}`` mappings;
    anything else falls back to ``repr`` (deterministic per process).
    """
    if isinstance(value, functools.partial) or callable(value):
        return _canonicalize_callable(value)
    if isinstance(value, BaseGeometry):
        return value.wkt
    if isinstance(value, dict):
        return {
            str(k): _canonicalize_value(v)
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
            if str(k) not in _EXTENT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _canonicalize_callable(fn: Any) -> dict[str, Any]:
    """Unwrap a (possibly partial) callable into a canonical mapping."""
    keywords: dict[str, Any] = {}
    target = fn
    while isinstance(target, functools.partial):
        keywords = {**target.keywords, **keywords}
        target = target.func
    canonical: dict[str, Any] = {"_target_": _callable_target(target)}
    for key, value in sorted(keywords.items(), key=lambda item: str(item[0])):
        if str(key) in _EXTENT_KEYS:
            continue
        canonical[str(key)] = _canonicalize_value(value)
    return canonical


def canonicalize_job(job: ExtractionJob) -> dict[str, Any]:
    """Build the canonical, comparable snapshot dict for *job*.

    Only output-defining fields are included; extent and runtime fields are
    excluded so that identical jobs built from YAML or in code compare equal.

    Args:
        job: The extraction job to snapshot.

    Returns:
        A YAML-safe dictionary representing the job's output identity.
    """
    snapshot: dict[str, Any] = {}
    for field in _SCALAR_FIELDS:
        value = getattr(job, field)
        if value is not None:
            snapshot[field] = value
    for field in _CALLABLE_FIELDS:
        value = getattr(job, field)
        if value is None:
            continue
        if isinstance(value, list):
            snapshot[field] = [_canonicalize_callable(fn) for fn in value]
        else:
            snapshot[field] = _canonicalize_callable(value)
    return snapshot


def _diff(existing: Any, incoming: Any, path: str = "") -> list[str]:
    """Return human-readable lines describing differences between two values."""
    if isinstance(existing, dict) and isinstance(incoming, dict):
        lines: list[str] = []
        for key in sorted(set(existing) | set(incoming)):
            sub = f"{path}.{key}" if path else str(key)
            if key not in existing:
                lines.append(
                    f"{sub}: <missing> (existing) != {incoming[key]!r} (requested)"
                )
            elif key not in incoming:
                lines.append(
                    f"{sub}: {existing[key]!r} (existing) != <missing> (requested)"
                )
            else:
                lines.extend(_diff(existing[key], incoming[key], sub))
        return lines
    if existing != incoming:
        label = path or "<root>"
        return [f"{label}: {existing!r} (existing) != {incoming!r} (requested)"]
    return []


def snapshot_uri_for(output_uri: str, job_name: str) -> str:
    """Return the snapshot URI for a job name under *output_uri*."""
    safe_job = sanitize_job_name(job_name)
    base = output_uri.rstrip("/")
    return f"{base}/job-{safe_job}/{SNAPSHOT_FILENAME}"


def check_job_snapshot(job: ExtractionJob) -> str | None:
    """Validate *job* against its on-disk snapshot, writing it on first run.

    Args:
        job: The extraction job about to run.

    Returns:
        The snapshot URI, or *None* when the guard could not access the
        output filesystem (e.g. missing object-store dependencies).

    Raises:
        JobConfigMismatchError: If a snapshot already exists and its
            configuration differs from *job*.
    """
    canonical = canonicalize_job(job)
    uri = snapshot_uri_for(job.output_uri, job.name)
    try:
        fs, path = fsspec.core.url_to_fs(uri)
    except Exception as exc:  # e.g. s3:// without s3fs installed
        logger.warning("job_snapshot_skipped", uri=uri, reason=str(exc))
        return None

    if fs.exists(path):
        with fs.open(path, "rt") as handle:
            existing = yaml.safe_load(handle) or {}
        if existing != canonical:
            raise JobConfigMismatchError(job.name, uri, _diff(existing, canonical))
        logger.info("job_snapshot_validated", uri=uri)
        return uri

    parent = path.rsplit("/", 1)[0]
    fs.makedirs(parent, exist_ok=True)
    with fs.open(path, "wt") as handle:
        yaml.safe_dump(canonical, handle, sort_keys=True)
    logger.info("job_snapshot_written", uri=uri)
    return uri
