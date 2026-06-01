"""Tests that sf-hamilton is importable and functional."""

from __future__ import annotations


def test_hamilton_importable() -> None:
    """Hamilton driver.Builder must be available after installation."""
    from hamilton import driver

    assert driver.Builder is not None
