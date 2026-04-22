import datetime
from pathlib import Path

from aer.eoids import build_eoids_path


def test_build_eoids_path_basic():
    st = datetime.datetime(2026, 1, 1, 10, 0, 22)
    et = datetime.datetime(2026, 1, 1, 10, 9, 32)

    path = build_eoids_path(
        local_dir="/tmp/dataset",
        cell_id="36D_61L",
        start_time=st,
        end_time=et,
        satellite="goes_east",
        product="RadF",
        band="C01",
        resolution=1000,
    )

    expected_dir = Path("/tmp/dataset/loc-36D61L/date-20260101/sat-goes_east")
    expected_filename = "loc-36D61L_start-20260101T100022_end-20260101T100932_sat-goes_east_prod-RadF_band-C01_res-1000m.tif"

    assert path.parent == expected_dir
    assert path.name == expected_filename


def test_build_eoids_path_derivatives():
    st = datetime.datetime(2026, 1, 1, 10, 0, 22)

    path = build_eoids_path(
        local_dir="/tmp/dataset",
        cell_id="36D_61L",
        start_time=st,
        derivative="cloud_mask",
        desc="cloudprob",
        suffix="nc",
    )

    expected_dir = Path("/tmp/dataset/derivatives/cloud_mask/loc-36D61L/date-20260101")
    expected_filename = "loc-36D61L_start-20260101T100022_desc-cloudprob.nc"

    assert path.parent == expected_dir
    assert path.name == expected_filename


def test_build_eoids_path_no_time():
    path = build_eoids_path(
        local_dir="/tmp/dataset", cell_id="36D_61L", product="StaticMask"
    )

    expected_dir = Path("/tmp/dataset/loc-36D61L")
    expected_filename = "loc-36D61L_prod-StaticMask.tif"

    assert path.parent == expected_dir
    assert path.name == expected_filename
