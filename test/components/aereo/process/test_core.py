"""Tests for built-in processor functions."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from aereo.process.core import (
    composite,
    compute_ndvi,
    compute_ndwi,
    mask_clouds,
    normalize,
    select_bands,
    supported_collections,
)


def _make_dataset(data_vars: dict[str, xr.DataArray]) -> xr.Dataset:
    """Helper to build a minimal xr.Dataset for testing."""
    return xr.Dataset(data_vars)


# ---------------------------------------------------------------------------
# supported_collections
# ---------------------------------------------------------------------------


def test_supported_collections_is_wildcard() -> None:
    assert supported_collections == ("*",)


# ---------------------------------------------------------------------------
# select_bands
# ---------------------------------------------------------------------------


def test_select_bands_keeps_requested() -> None:
    ds = _make_dataset(
        {
            "red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x")),
            "green": xr.DataArray(np.ones((2, 2)), dims=("y", "x")),
            "blue": xr.DataArray(np.full((2, 2), 2), dims=("y", "x")),
        }
    )
    result = select_bands(ds, bands=["red", "green"])
    assert list(result.data_vars) == ["red", "green"]


def test_select_bands_none_returns_unchanged() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    result = select_bands(ds, bands=None)
    assert list(result.data_vars) == ["red"]


def test_select_bands_empty_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="non-empty list"):
        select_bands(ds, bands=[])


def test_select_bands_missing_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="not found"):
        select_bands(ds, bands=["nir"])


# ---------------------------------------------------------------------------
# mask_clouds
# ---------------------------------------------------------------------------


def test_mask_clouds_masks_pixels() -> None:
    qa = xr.DataArray(
        np.array([[0b0001, 0b0010], [0b0000, 0b0011]]),
        dims=("y", "x"),
        name="QA",
    )
    red = xr.DataArray(
        np.array([[1.0, 2.0], [3.0, 4.0]]),
        dims=("y", "x"),
        name="red",
    )
    ds = _make_dataset({"red": red, "QA": qa})

    result = mask_clouds(ds, qa_band="QA", qa_mask_bits=[0])

    assert "QA" not in result.data_vars
    assert np.isnan(result["red"].values[0, 0])
    assert result["red"].values[0, 1] == 2.0
    assert result["red"].values[1, 0] == 3.0
    assert np.isnan(result["red"].values[1, 1])


def test_mask_clouds_missing_params_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="requires"):
        mask_clouds(ds)


def test_mask_clouds_missing_band_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="not found"):
        mask_clouds(ds, qa_band="QA", qa_mask_bits=[0])


# ---------------------------------------------------------------------------
# compute_ndvi
# ---------------------------------------------------------------------------


def test_compute_ndvi_returns_ndvi() -> None:
    nir = xr.DataArray(np.array([[8.0, 4.0], [2.0, 0.0]]), dims=("y", "x"), name="nir")
    red = xr.DataArray(np.array([[2.0, 4.0], [2.0, 0.0]]), dims=("y", "x"), name="red")
    ds = _make_dataset({"nir": nir, "red": red})

    result = compute_ndvi(ds)

    assert "ndvi" in result.data_vars
    assert "nir" not in result.data_vars
    assert "red" not in result.data_vars
    expected = np.array([[0.6, 0.0], [0.0, np.nan]])
    np.testing.assert_array_almost_equal(result["ndvi"].values, expected, decimal=6)


def test_compute_ndvi_custom_bands() -> None:
    b5 = xr.DataArray(np.array([[8.0, 4.0]]), dims=("y", "x"), name="B5")
    b4 = xr.DataArray(np.array([[2.0, 4.0]]), dims=("y", "x"), name="B4")
    ds = _make_dataset({"B5": b5, "B4": b4})

    result = compute_ndvi(ds, nir_band="B5", red_band="B4")

    assert "ndvi" in result.data_vars


def test_compute_ndvi_missing_band_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="NIR band"):
        compute_ndvi(ds)


# ---------------------------------------------------------------------------
# compute_ndwi
# ---------------------------------------------------------------------------


def test_compute_ndwi_returns_ndwi() -> None:
    nir = xr.DataArray(np.array([[8.0, 4.0], [2.0, 0.0]]), dims=("y", "x"), name="nir")
    swir = xr.DataArray(
        np.array([[2.0, 4.0], [2.0, 0.0]]), dims=("y", "x"), name="swir"
    )
    ds = _make_dataset({"nir": nir, "swir": swir})

    result = compute_ndwi(ds)

    assert "ndwi" in result.data_vars
    assert "nir" not in result.data_vars
    assert "swir" not in result.data_vars
    expected = np.array([[0.6, 0.0], [0.0, np.nan]])
    np.testing.assert_array_almost_equal(result["ndwi"].values, expected, decimal=6)


def test_compute_ndwi_missing_band_raises() -> None:
    ds = _make_dataset({"nir": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="SWIR band"):
        compute_ndwi(ds)


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_minmax() -> None:
    da = xr.DataArray(np.array([[0.0, 2.0], [4.0, 6.0]]), dims=("y", "x"), name="red")
    ds = _make_dataset({"red": da})

    result = normalize(ds, method="minmax")

    expected = np.array([[0.0, 1 / 3], [2 / 3, 1.0]])
    np.testing.assert_array_almost_equal(result["red"].values, expected, decimal=6)


def test_normalize_zscore() -> None:
    da = xr.DataArray(np.array([[0.0, 2.0], [4.0, 6.0]]), dims=("y", "x"), name="red")
    ds = _make_dataset({"red": da})

    result = normalize(ds, method="zscore")

    mean = 3.0
    std = np.std([0.0, 2.0, 4.0, 6.0], ddof=0)
    expected = (np.array([[0.0, 2.0], [4.0, 6.0]]) - mean) / std
    np.testing.assert_array_almost_equal(result["red"].values, expected, decimal=6)


def test_normalize_unknown_method_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="unknown method"):
        normalize(ds, method="unknown")


# ---------------------------------------------------------------------------
# composite
# ---------------------------------------------------------------------------


def test_composite_median() -> None:
    da = xr.DataArray(
        np.arange(24).reshape(2, 3, 4),
        dims=("time", "y", "x"),
        coords={"time": [0, 1]},
        name="red",
    )
    ds = _make_dataset({"red": da})

    result = composite(ds, method="median")

    assert "time" not in result.dims
    expected = np.median(np.arange(24).reshape(2, 3, 4), axis=0)
    np.testing.assert_array_equal(result["red"].values, expected)


def test_composite_mean() -> None:
    da = xr.DataArray(
        np.ones((2, 3, 4)),
        dims=("time", "y", "x"),
        coords={"time": [0, 1]},
        name="red",
    )
    ds = _make_dataset({"red": da})

    result = composite(ds, method="mean")

    assert "time" not in result.dims
    np.testing.assert_array_equal(result["red"].values, np.ones((3, 4)))


def test_composite_missing_time_raises() -> None:
    ds = _make_dataset({"red": xr.DataArray(np.zeros((2, 2)), dims=("y", "x"))})
    with pytest.raises(ValueError, match="time"):
        composite(ds)


def test_composite_unknown_method_raises() -> None:
    da = xr.DataArray(
        np.ones((2, 2, 2)),
        dims=("time", "y", "x"),
        coords={"time": [0, 1]},
        name="red",
    )
    ds = _make_dataset({"red": da})
    with pytest.raises(ValueError, match="unknown method"):
        composite(ds, method="mode")
