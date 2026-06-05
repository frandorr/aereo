import datetime
from pathlib import Path


from aereo.eoids import build_eoids_path, parse_eoids_filename
from aereo.eoids.core import _matches_filter


def test_build_eoids_path_basic():
    st = datetime.datetime(2026, 1, 1, 10, 0, 22)
    et = datetime.datetime(2026, 1, 1, 10, 9, 32)

    path = build_eoids_path(
        local_dir="/tmp/dataset",
        profile_name="goes_c01",
        resolution=1000.0,
        collections=["ABI-L1b-RadF"],
        variables=["C01"],
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


def test_build_eoids_path_derivatives():
    st = datetime.datetime(2026, 1, 1, 10, 0, 22)

    path = build_eoids_path(
        local_dir="/tmp/dataset",
        profile_name="goes_c01",
        resolution=1000.0,
        collections=["ABI-L1b-RadF"],
        variables=["C01"],
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


def test_eoids_loader_merge_with_extraction():
    """Test EOIDSLoader.merge_with_extraction deduplicates correctly."""
    import geopandas as gpd
    from shapely.geometry import Point

    from aereo.eoids import EOIDSLoader

    existing = gpd.GeoDataFrame(
        {
            "grid_cell": ["cell1", "cell2"],
            "collection": ["s2", "s2"],
            "start_time": ["2024-01-01", "2024-01-02"],
            "value": [1, 2],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:4326",
    )

    new_artifacts = gpd.GeoDataFrame(
        {
            "grid_cell": ["cell1", "cell3"],
            "collection": ["s2", "s2"],
            "start_time": ["2024-01-01", "2024-01-03"],
            "value": [10, 30],
        },
        geometry=[Point(0, 0), Point(2, 2)],
        crs="EPSG:4326",
    )

    loader = EOIDSLoader("/tmp/dummy.parquet")
    merged = loader.merge_with_extraction(existing, new_artifacts)

    # Should have 3 rows (cell1, cell2, cell3)
    assert len(merged) == 3

    # cell1 should have the new value (10) because keep="last"
    cell1_rows = merged[merged["grid_cell"] == "cell1"]
    assert len(cell1_rows) == 1
    assert cell1_rows.iloc[0]["value"] == 10


def test_eoids_loader_merge_no_dedup_cols():
    """Test merge when dedup columns don't exist."""
    import geopandas as gpd
    from shapely.geometry import Point

    from aereo.eoids import EOIDSLoader

    existing = gpd.GeoDataFrame(
        {"value": [1]},
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )

    new_artifacts = gpd.GeoDataFrame(
        {"value": [2]},
        geometry=[Point(1, 1)],
        crs="EPSG:4326",
    )

    loader = EOIDSLoader("/tmp/dummy.parquet")
    merged = loader.merge_with_extraction(existing, new_artifacts)

    # No dedup columns available, so both rows should be kept
    assert len(merged) == 2
