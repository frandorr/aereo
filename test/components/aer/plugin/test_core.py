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


def test_project_name():
    """PROJECT_NAME is correctly set."""
    assert core.PROJECT_NAME == "aer"


def test_aerspec_has_all_hooks():
    """AerSpec defines all required hooks."""
    required_hooks = ["search", "prepare_tasks", "extract"]
    for hook_name in required_hooks:
        assert hasattr(core.AerSpec, hook_name), f"AerSpec missing hook: {hook_name}"


def test_all_hooks_are_callable():
    """All AerSpec hooks are callable methods."""
    for attr_name in ["search", "prepare_tasks", "extract"]:
        attr = getattr(core.AerSpec, attr_name)
        assert callable(attr), f"{attr_name} is not callable"
