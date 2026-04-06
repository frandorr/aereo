"""Tests for the plugin core module.

Verifies that the pluggy-based hookspec system is correctly configured.
"""

from aer.plugin import core


def test_core_exports():
    """Core module exports required pluggy components."""
    assert hasattr(core, "PROJECT_NAME")
    assert hasattr(core, "hookspec")
    assert hasattr(core, "hookimpl")
    assert hasattr(core, "AerSpec")
