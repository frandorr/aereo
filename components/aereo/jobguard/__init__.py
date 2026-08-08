"""Job configuration snapshot guard for EOIDS outputs.

Persists a canonical YAML snapshot of a job's output-defining configuration
and validates subsequent runs against it, preventing silent output
overwrites when a job name is reused with a different configuration.
"""

from .core import (
    JobConfigMismatchError,
    canonicalize_job,
    check_job_snapshot,
    snapshot_uri_for,
)

__all__ = [
    "JobConfigMismatchError",
    "canonicalize_job",
    "check_job_snapshot",
    "snapshot_uri_for",
]
