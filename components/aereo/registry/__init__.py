"""AEREO plugin registry.

Acts as the central nervous system of aereo, dynamically discovering plugins
installed in the environment, validating them against interface contracts, and
routing user requests to the correct implementations.
"""

from aereo.discovery import (
    StagePlugins,
    discover_plugins,
    resolve_plugin,
)
from aereo.registry.core import AereoRegistry

__all__ = [
    "AereoRegistry",
    "StagePlugins",
    "discover_plugins",
    "resolve_plugin",
]
