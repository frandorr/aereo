"""Public API entry-point for the Aereo client.

This module re-exports the core client classes that consumers interact with:

- :class:`AereoClient`: The main orchestrator for search and extraction pipelines.
- :class:`FailureMode`: Enum controlling pipeline behavior on plugin failures.
"""

from aereo.client.core import (
    AereoClient,
    FailureMode,
)

__all__ = [
    "AereoClient",
    "FailureMode",
]
