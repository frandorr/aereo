import datetime
from pathlib import Path

import pytest

from aereo.eoids import build_eoids_path, parse_eoids_filename
from aereo.eoids.core import _matches_filter
from aereo.interfaces import AereoProfile


@pytest.fixture()
def dummy_profile():
    return AereoProfile(
        name="goes_c01",
        resolution=1000.0,
        collections={"ABI-L1b-RadF": ["C01"]},
    )


def test_build_eoids_path_basic(dummy_profile):
    st = datetime.datetime(2026, 1, 1, 10, 0, 22)
    et = datetime.datetime(2026, 1, 1, 10, 9, 32)

    path = build_eoids_path(
        local_dir="/tmp/dataset",
        profile=dummy_profile,
        cell_id="36D_61L",
        start_time=st,
        end_time=et,
    )

    expected_dir = Path("/tmp/dataset/loc-36D61L/date-20260101/profile-goes_c01")
    expected_filename = (
        "loc-36D61L_start-20260101T100022_end-20260101T100932_"
        "profile-goes_c01_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif"
    )

    assert path.parent == expected_dir
    assert path.name == expected_filename


def test_build_eoids_path_derivatives(dummy_profile):
    st = datetime.datetime(2026, 1, 1, 10, 0, 22)

    path = build_eoids_path(
        local_dir="/tmp/dataset",
        profile=dummy_profile,
        cell_id="36D_61L",
        start_time=st,
        derivative="cloud_mask",
        desc="cloudprob",
        suffix="nc",
    )

    expected_dir = Path(
        "/tmp/dataset/derivatives/cloud_mask/loc-36D61L/date-20260101/profile-goes_c01"
    )
    expected_filename = (
        "loc-36D61L_start-20260101T100022_profile-goes_c01_"
        "collection-ABI-L1b-RadF_variable-C01_res-1000m_desc-cloudprob.nc"
    )

    assert path.parent == expected_dir
    assert path.name == expected_filename


def test_parse_eoids_filename():
    fname = (
        "loc-36D61L_start-20260101T100022_end-20260101T100932_"
        "profile-goes_c01_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif"
    )
    parsed = parse_eoids_filename(fname)
    assert parsed["loc"] == "36D61L"
    assert parsed["start"] == "20260101T100022"
    assert parsed["end"] == "20260101T100932"
    assert parsed["profile"] == "goes_c01"
    assert parsed["collection"] == "ABI-L1b-RadF"
    assert parsed["variable"] == "C01"
    assert parsed["res"] == "1000m"


def test_matches_filter():
    assert _matches_filter("goes_c01", "goes_c01") is True
    assert _matches_filter(None, "goes_c01") is True
    assert _matches_filter("goes_c01", "s2_rgb") is False
