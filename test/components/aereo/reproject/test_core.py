"""Tests for the built-in reproject pipeline module."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from hamilton import driver

from aereo.reproject import core as reproject_module


def test_supported_collections_is_wildcard() -> None:
    """The reproject module supports any collection."""
    assert reproject_module.supported_collections == ("*",)


@patch("odc.geo.xr.xr_reproject")
def test_reproject_to_grid_defaults(mock_reproject: Any) -> None:
    """reproject_to_grid forwards ds and geobox to odc-geo with nearest default."""
    ds = MagicMock()
    geobox = MagicMock()
    mock_reproject.return_value = "reprojected_ds"

    result = reproject_module.reproject_to_grid(ds, geobox)

    assert result == "reprojected_ds"
    mock_reproject.assert_called_once_with(ds, geobox, resampling="nearest")


@patch("odc.geo.xr.xr_reproject")
def test_reproject_to_grid_custom_resampling(mock_reproject: Any) -> None:
    """reproject_to_grid respects the resampling parameter."""
    ds = MagicMock()
    geobox = MagicMock()
    mock_reproject.return_value = "reprojected_ds"

    result = reproject_module.reproject_to_grid(ds, geobox, resampling="bilinear")

    assert result == "reprojected_ds"
    mock_reproject.assert_called_once_with(ds, geobox, resampling="bilinear")


def test_reproject_pipeline_runs() -> None:
    """reproject.py can be built into a Hamilton driver and executes reproject_to_grid."""
    dr = driver.Builder().with_modules(reproject_module).build()

    ds = MagicMock()
    geobox = MagicMock()

    with patch("odc.geo.xr.xr_reproject") as mock_rep:
        mock_rep.return_value = "reprojected"
        result = dr.execute(
            ["reproject_to_grid"],
            inputs={"ds": ds, "geobox": geobox, "resampling": "average"},
        )
        assert "reproject_to_grid" in result
        assert result["reproject_to_grid"] == "reprojected"
        mock_rep.assert_called_once_with(ds, geobox, resampling="average")
