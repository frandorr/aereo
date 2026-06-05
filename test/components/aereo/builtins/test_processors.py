"""Tests for built-in processor plugins."""

from __future__ import annotations

import numpy as np
import pytest
import rioxarray  # noqa: F401 — registers the ``rio`` accessor on xarray objects
import xarray as xr
from pydantic import ValidationError

from aereo.builtins import (
    Composite,
    NDVI,
    Normalize,
    QAMask,
    SelectBands,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataset(data_vars=None, dims=("y", "x"), shape=(4, 4)):
    """Return a minimal AereoDataset for testing."""
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
# SelectBands
# ---------------------------------------------------------------------------


def test_select_bands_keeps_requested_variables():
    ds = _make_dataset()
    proc = SelectBands(bands=["B04"])
    result = proc(ds)

    assert "B04" in result.data_vars
    assert "B08" not in result.data_vars


def test_select_bands_raises_on_missing_band():
    ds = _make_dataset()
    proc = SelectBands(bands=["B99"])

    with pytest.raises(ValueError, match="requested bands not found"):
        proc(ds)


def test_select_bands_raises_when_bands_missing_param():
    with pytest.raises(ValidationError):
        SelectBands()  # type: ignore[reportCallIssue]


# ---------------------------------------------------------------------------
# QAMask
# ---------------------------------------------------------------------------


def test_qa_mask_sets_masked_pixels_to_nan():
    qa = np.array([[0, 1], [2, 3]])
    b04 = np.ones((2, 2)) * 10.0
    ds = xr.Dataset(
        {"B04": (["y", "x"], b04), "QA": (["y", "x"], qa)},
        coords={"y": range(2), "x": range(2)},
    )

    proc = QAMask(qa_band="QA", qa_mask_bits=[0])
    result = proc(ds)

    # bit 0 set -> values 1 and 3 should be masked
    assert np.isnan(result["B04"].values[0, 1])
    assert np.isnan(result["B04"].values[1, 1])
    # bit 0 not set -> values 0 and 2 should remain
    assert result["B04"].values[0, 0] == 10.0
    assert result["B04"].values[1, 0] == 10.0
    assert "QA" not in result.data_vars


def test_qa_mask_raises_on_missing_params():
    with pytest.raises(ValidationError):
        QAMask()  # type: ignore[reportCallIssue]


def test_qa_mask_raises_on_missing_band():
    ds = _make_dataset()
    proc = QAMask(qa_band="QA", qa_mask_bits=[0])

    with pytest.raises(ValueError, match="not found"):
        proc(ds)


# ---------------------------------------------------------------------------
# NDVI
# ---------------------------------------------------------------------------


def test_ndvi_computes_correct_values():
    red = np.array([[0.1, 0.2], [0.3, 0.4]])
    nir = np.array([[0.3, 0.4], [0.5, 0.6]])
    ds = xr.Dataset(
        {"B04": (["y", "x"], red), "B08": (["y", "x"], nir)},
        coords={"y": range(2), "x": range(2)},
    )

    proc = NDVI(ndvi_nir_band="B08", ndvi_red_band="B04")
    result = proc(ds)

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

    proc = NDVI(ndvi_nir_band="B08", ndvi_red_band="B04")
    result = proc(ds)

    assert np.all(np.isnan(result["ndvi"].values))


def test_ndvi_raises_on_missing_params():
    with pytest.raises(ValidationError):
        NDVI()  # type: ignore[reportCallIssue]


def test_ndvi_raises_on_missing_band():
    ds = _make_dataset()
    proc = NDVI(ndvi_nir_band="B08", ndvi_red_band="B99")

    with pytest.raises(ValueError, match="not found"):
        proc(ds)


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def test_normalize_minmax_scales_to_zero_one():
    data = np.array([[1.0, 2.0], [3.0, 4.0]])
    ds = xr.Dataset(
        {"B04": (["y", "x"], data)},
        coords={"y": range(2), "x": range(2)},
    )

    proc = Normalize(normalize_method="minmax")
    result = proc(ds)

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

    proc = Normalize(normalize_method="zscore")
    result = proc(ds)

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

    proc = Normalize(normalize_method="minmax")
    result = proc(ds)

    np.testing.assert_array_almost_equal(result["B04"].values, np.zeros((2, 2)))


def test_normalize_raises_on_unknown_method():
    ds = _make_dataset()
    proc = Normalize(normalize_method="foo")

    with pytest.raises(ValueError, match="unknown method"):
        proc(ds)


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def test_composite_median_reduces_time():
    ds = _make_temporal_dataset()
    proc = Composite(composite_method="median")
    result = proc(ds)

    assert "time" not in result.dims
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        ds["B04"].median(dim="time").values,
    )


def test_composite_mean():
    ds = _make_temporal_dataset()
    proc = Composite(composite_method="mean")
    result = proc(ds)

    assert "time" not in result.dims
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        ds["B04"].mean(dim="time").values,
    )


def test_composite_max():
    ds = _make_temporal_dataset()
    proc = Composite(composite_method="max")
    result = proc(ds)

    assert "time" not in result.dims
    np.testing.assert_array_almost_equal(
        result["B04"].values,
        ds["B04"].max(dim="time").values,
    )


def test_composite_raises_on_missing_time():
    ds = _make_dataset()
    proc = Composite(composite_method="median")

    with pytest.raises(ValueError, match="time"):
        proc(ds)


def test_composite_raises_on_unknown_method():
    ds = _make_temporal_dataset()
    proc = Composite(composite_method="foo")

    with pytest.raises(ValueError, match="unknown method"):
        proc(ds)
