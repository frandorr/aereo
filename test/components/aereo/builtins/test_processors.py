"""Tests for built-in processor plugins."""

from __future__ import annotations

import numpy as np
import pytest
import rioxarray  # noqa: F401 — registers the ``rio`` accessor on xarray objects
import xarray as xr
from pydantic import ValidationError

from aereo.builtins import (
    composite,
    ndvi,
    ndwi,
    normalize,
    qa_mask,
    select_bands,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataset(data_vars=None, dims=("y", "x"), shape=(4, 4)):
    """Return a minimal xarray.Dataset for testing."""
    coords = {d: range(s) for d, s in zip(dims, shape)}
    if data_vars is None:
        data_vars = {
            "B04": (dims, np.ones(shape) * 0.3),
            "B08": (dims, np.ones(shape) * 0.5),
        }
    ds = xr.Dataset(data_vars, coords=coords)
    return ds


def _make_temporal_dataset():
    """Return a dataset with a time dimension."""
    data = np.random.rand(3, 4, 4)
    ds = xr.Dataset(
        {"B04": (["time", "y", "x"], data)},
        coords={"time": range(3), "y": range(4), "x": range(4)},
    )
    return ds


# ---------------------------------------------------------------------------
# select_bands
# ---------------------------------------------------------------------------


def test_select_bands_keeps_requested_variables():
    ds = _make_dataset()
    result = select_bands(ds, bands=["B04"])

    assert "B04" in result.data_vars
    assert "B08" not in result.data_vars


def test_select_bands_raises_on_missing_band():
    ds = _make_dataset()
    with pytest.raises(ValueError, match="requested bands not found"):
        select_bands(ds, bands=["B99"])


def test_select_bands_raises_when_bands_missing_param():
    with pytest.raises(ValidationError):
        select_bands()  # type: ignore[reportCallIssue]


# ---------------------------------------------------------------------------
# qa_mask
# ---------------------------------------------------------------------------


def test_qa_mask_sets_masked_pixels_to_nan():
    qa = np.array([[0, 1], [2, 3]])
    b04 = np.ones((2, 2)) * 10.0
    ds = xr.Dataset(
        {"B04": (["y", "x"], b04), "QA": (["y", "x"], qa)},
        coords={"y": range(2), "x": range(2)},
    )

    result = qa_mask(ds, qa_band="QA", qa_mask_bits=[0])

    # bit 0 set -> values 1 and 3 should be masked
    assert np.isnan(result["B04"].values[0, 1])
    assert np.isnan(result["B04"].values[1, 1])
    # bit 0 not set -> values 0 and 2 should remain
    assert result["B04"].values[0, 0] == 10.0
    assert result["B04"].values[1, 0] == 10.0
    assert "QA" not in result.data_vars


def test_qa_mask_raises_on_missing_params():
    with pytest.raises(ValidationError):
        qa_mask()  # type: ignore[reportCallIssue]


def test_qa_mask_raises_on_missing_band():
    ds = _make_dataset()
    with pytest.raises(ValueError, match="not found"):
        qa_mask(ds, qa_band="QA", qa_mask_bits=[0])


# ---------------------------------------------------------------------------
# ndvi
# ---------------------------------------------------------------------------


def test_ndvi_computes_correct_values():
    red = np.array([[0.1, 0.2], [0.3, 0.4]])
    nir = np.array([[0.3, 0.4], [0.5, 0.6]])
    ds = xr.Dataset(
        {"B04": (["y", "x"], red), "B08": (["y", "x"], nir)},
        coords={"y": range(2), "x": range(2)},
    )

    result = ndvi(ds, ndvi_nir_band="B08", ndvi_red_band="B04")

    expected = (nir - red) / (nir + red)
    np.testing.assert_array_almost_equal(result["ndvi"].values, expected)
    assert "B04" not in result.data_vars
    assert "B08" not in result.data_vars


def test_ndvi_handles_zero_denominator():
    red = np.zeros((2, 2))
    nir = np.zeros((2, 2))
    ds = xr.Dataset(
        {"B04": (["y", "x"], red), "B08": (["y", "x"], nir)},
        coords={"y": range(2), "x": range(2)},
    )

    result = ndvi(ds, ndvi_nir_band="B08", ndvi_red_band="B04")

    assert np.all(np.isnan(result["ndvi"].values))


def test_ndvi_raises_on_missing_params():
    with pytest.raises(ValidationError):
        ndvi()  # type: ignore[reportCallIssue]


def test_ndvi_raises_on_missing_band():
    ds = _make_dataset()
    with pytest.raises(ValueError, match="not found"):
        ndvi(ds, ndvi_nir_band="B08", ndvi_red_band="B99")


# ---------------------------------------------------------------------------
# ndwi
# ---------------------------------------------------------------------------


def test_ndwi_computes_correct_values():
    green = np.array([[0.1, 0.2], [0.3, 0.4]])
    nir = np.array([[0.3, 0.4], [0.5, 0.6]])
    ds = xr.Dataset(
        {"B03": (["y", "x"], green), "B08": (["y", "x"], nir)},
        coords={"y": range(2), "x": range(2)},
    )

    result = ndwi(ds, ndwi_green_band="B03", ndwi_nir_band="B08")

    expected = (green - nir) / (green + nir)
    np.testing.assert_array_almost_equal(result["ndwi"].values, expected)
    assert "B03" not in result.data_vars
    assert "B08" not in result.data_vars


def test_ndwi_handles_zero_denominator():
    green = np.zeros((2, 2))
    nir = np.zeros((2, 2))
    ds = xr.Dataset(
        {"B03": (["y", "x"], green), "B08": (["y", "x"], nir)},
        coords={"y": range(2), "x": range(2)},
    )

    result = ndwi(ds, ndwi_green_band="B03", ndwi_nir_band="B08")

    assert np.all(np.isnan(result["ndwi"].values))


def test_ndwi_raises_on_missing_params():
    with pytest.raises(ValidationError):
        ndwi()  # type: ignore[reportCallIssue]


def test_ndwi_raises_on_missing_band():
    ds = _make_dataset()
    with pytest.raises(ValueError, match="not found"):
        ndwi(ds, ndwi_green_band="B03", ndwi_nir_band="B99")


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------


def test_normalize_minmax_scales_to_zero_one():
    data = np.array([[1.0, 2.0], [3.0, 4.0]])
    ds = xr.Dataset(
        {"B04": (["y", "x"], data)},
        coords={"y": range(2), "x": range(2)},
    )

    result = normalize(ds, normalize_method="minmax")

    np.testing.assert_array_almost_equal(
        result["B04"].values,
        np.array([[0.0, 1 / 3], [2 / 3, 1.0]]),
    )


def test_normalize_zscore():
    data = np.array([[1.0, 2.0], [3.0, 4.0]])
    ds = xr.Dataset(
        {"B04": (["y", "x"], data)},
        coords={"y": range(2), "x": range(2)},
    )

    result = normalize(ds, normalize_method="zscore")

    mean = data.mean()
    std = data.std(ddof=0)
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        (data - mean) / std,
    )


def test_normalize_handles_constant_band():
    data = np.ones((2, 2)) * 5.0
    ds = xr.Dataset(
        {"B04": (["y", "x"], data)},
        coords={"y": range(2), "x": range(2)},
    )

    result = normalize(ds, normalize_method="minmax")

    np.testing.assert_array_almost_equal(result["B04"].values, np.zeros((2, 2)))


def test_normalize_raises_on_unknown_method():
    ds = _make_dataset()
    with pytest.raises(ValueError, match="unknown method"):
        normalize(ds, normalize_method="foo")


# ---------------------------------------------------------------------------
# composite
# ---------------------------------------------------------------------------


def test_composite_median_reduces_time():
    ds = _make_temporal_dataset()
    result = composite(ds, composite_method="median")

    assert "time" not in result.dims
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        ds["B04"].median(dim="time").values,
    )


def test_composite_mean():
    ds = _make_temporal_dataset()
    result = composite(ds, composite_method="mean")

    assert "time" not in result.dims
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        ds["B04"].mean(dim="time").values,
    )


def test_composite_max():
    ds = _make_temporal_dataset()
    result = composite(ds, composite_method="max")

    assert "time" not in result.dims
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        ds["B04"].max(dim="time").values,
    )


def test_composite_raises_on_missing_time():
    ds = _make_dataset()
    with pytest.raises(ValueError, match="time"):
        composite(ds, composite_method="median")


def test_composite_raises_on_unknown_method():
    ds = _make_temporal_dataset()
    with pytest.raises(ValueError, match="unknown method"):
        composite(ds, composite_method="foo")
