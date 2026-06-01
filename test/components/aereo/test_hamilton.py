"""Tests for Hamilton dependency availability."""


def test_hamilton_importable():
    """sf-hamilton must be installed and its Builder API available."""
    from hamilton import driver

    assert driver.Builder is not None
