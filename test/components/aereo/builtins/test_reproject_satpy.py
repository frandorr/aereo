"""Integration tests for the reproject_satpy plugin."""

from __future__ import annotations


def test_reproject_satpy_registry():
    """Verify ReprojectSatpy can be loaded via the plugin registry."""
    from aereo.interfaces import Reprojector
    from aereo.registry import AereoRegistry

    reg = AereoRegistry()
    plugin = reg.get("reprojector", "reproject_satpy", resolution=10.0)
    assert isinstance(plugin, Reprojector)
