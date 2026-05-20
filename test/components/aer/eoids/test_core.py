import datetime
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from aer.eoids import (
    build_eoids_path,
    load_eoids_tiles,
    mosaic_eoids_tiles,
    parse_eoids_filename,
    scan_eoids_dir,
)
from aer.eoids.core import _matches_filter
from aer.interfaces import AerProfile
from rasterio.crs import CRS
from rasterio.transform import from_bounds

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------


@pytest.fixture()
def dummy_profile():
    return AerProfile(
        name="goes_c01",
        resolution=1000.0,
        collections={"ABI-L1b-RadF": ["C01"]},
    )


# -----------------------------------------------------------------------
# Tests for build_eoids_path
# -----------------------------------------------------------------------


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


def test_build_eoids_path_no_time(dummy_profile):
    path = build_eoids_path(
        local_dir="/tmp/dataset",
        profile=dummy_profile,
        cell_id="36D_61L",
    )

    expected_dir = Path("/tmp/dataset/loc-36D61L/profile-goes_c01")
    expected_filename = (
        "loc-36D61L_profile-goes_c01_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif"
    )

    assert path.parent == expected_dir
    assert path.name == expected_filename


def test_build_eoids_path_with_profile_only():
    profile = AerProfile(name="test_prof", resolution=500.0, collections={})
    path = build_eoids_path("/tmp/ds", profile=profile)

    assert path.parent == Path("/tmp/ds/profile-test_prof")
    assert path.name == "profile-test_prof_res-500m.tif"


def test_build_eoids_path_uses_profile_resolution():
    profile = AerProfile(name="test_prof", resolution=250.0, collections={})
    path = build_eoids_path(
        "/tmp/ds",
        profile=profile,
        cell_id="1U_10L",
    )
    assert "res-250m" in path.name


def test_build_eoids_path_multiple_collections_and_variables():
    profile = AerProfile(
        name="viirs_geo",
        resolution=375.0,
        collections={"IMG202": ["I04"], "IMG203": ["I05"]},
    )
    path = build_eoids_path(
        "/tmp/ds",
        profile=profile,
        cell_id="1U_10L",
        start_time=datetime.datetime(2026, 1, 1, 10, 0, 0),
    )

    assert "collection-IMG202+IMG203" in path.name
    assert "variable-I04+I05" in path.name
    assert path.parent == Path("/tmp/ds/loc-1U10L/date-20260101/profile-viirs_geo")


def test_build_eoids_path_empty_collections():
    profile = AerProfile(name="mask", resolution=500.0, collections={})
    path = build_eoids_path("/tmp/ds", profile=profile, cell_id="1U_10L")

    assert "collection-" not in path.name
    assert "variable-" not in path.name
    assert path.parent == Path("/tmp/ds/loc-1U10L/profile-mask")


def test_build_eoids_path_writes_profile_json(tmp_path):
    profile = AerProfile(
        name="goes_c01", resolution=1000.0, collections={"ABI-L1b-RadF": ["C01"]}
    )
    path = build_eoids_path(tmp_path, profile=profile, cell_id="36D61L")

    profile_json = path.parent / "profile.json"
    assert profile_json.exists()
    data = json.loads(profile_json.read_text())
    assert data["name"] == "goes_c01"
    assert data["resolution"] == 1000.0
    assert "downloader" not in data


def test_build_eoids_path_skips_existing_profile_json(tmp_path):
    profile = AerProfile(
        name="goes_c01", resolution=1000.0, collections={"ABI-L1b-RadF": ["C01"]}
    )
    profile_json = tmp_path / "profile-goes_c01" / "profile.json"
    profile_json.parent.mkdir(parents=True)
    profile_json.write_text('{"custom": true}')

    build_eoids_path(tmp_path, profile=profile, cell_id="36D61L")
    assert profile_json.read_text() == '{"custom": true}'


# -----------------------------------------------------------------------
# Tests for parse_eoids_filename
# -----------------------------------------------------------------------


class TestParseEoidsFilename:
    def test_full_filename(self):
        meta = parse_eoids_filename(
            "loc-0U38L_start-20260101T100022_end-20260101T100953_"
            "profile-goes_c01_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif"
        )
        assert meta == {
            "loc": "0U38L",
            "start": "20260101T100022",
            "end": "20260101T100953",
            "profile": "goes_c01",
            "collection": "ABI-L1b-RadF",
            "variable": "C01",
            "res": "1000m",
        }

    def test_with_full_path(self):
        meta = parse_eoids_filename(
            "/data/loc-5D40L/date-20260101/profile-goes_c01/"
            "loc-5D40L_start-20260101T100022_end-20260101T100953_"
            "profile-goes_c01_collection-ABI-L1b-RadF_variable-C01_res-1000m.tif"
        )
        assert meta["loc"] == "5D40L"
        assert meta["profile"] == "goes_c01"

    def test_minimal_filename(self):
        meta = parse_eoids_filename("loc-36D61L_collection-StaticMask_res-1000m.tif")
        assert meta == {"loc": "36D61L", "collection": "StaticMask", "res": "1000m"}

    def test_with_desc(self):
        meta = parse_eoids_filename("loc-36D61L_desc-cloudprob.nc")
        assert meta == {"loc": "36D61L", "desc": "cloudprob"}

    def test_empty_filename(self):
        meta = parse_eoids_filename("random_file.tif")
        assert meta == {}

    def test_path_object(self):
        meta = parse_eoids_filename(Path("/some/dir/loc-1U2L_variable-C02.tif"))
        assert meta == {"loc": "1U2L", "variable": "C02"}

    def test_parse_eoids_filename_with_plus_concatenation(self):
        meta = parse_eoids_filename(
            "loc-0U38L_profile-viirs_geo_collection-IMG202+IMG203_variable-I04+I05_res-375m.tif"
        )
        assert meta["collection"] == "IMG202+IMG203"
        assert meta["variable"] == "I04+I05"


# -----------------------------------------------------------------------
# Fixtures for scan / load / mosaic tests
# -----------------------------------------------------------------------


def _create_test_tif(
    path: Path,
    crs: str = "EPSG:4326",
    bounds: tuple[float, float, float, float] = (-65.0, -32.0, -64.0, -31.0),
    shape: tuple[int, int] = (10, 10),
    value: float = 1.0,
) -> Path:
    """Write a minimal single-band GeoTIFF for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(*bounds, shape[1], shape[0])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(np.full(shape, value, dtype=np.float32), 1)
    return path


@pytest.fixture()
def eoids_tree(tmp_path):
    """Build a small EOIDS directory tree with tiles in two different UTM zones."""
    root = tmp_path / "extract_test"
    profile_name = "goes_c01"
    collection = "ABI-L1b-RadF"

    # Cell A — UTM zone 20S
    cell_a_dir = root / "loc-5D40L" / "date-20260101" / f"profile-{profile_name}"
    _create_test_tif(
        cell_a_dir
        / (
            "loc-5D40L_start-20260101T100022_end-20260101T100953_"
            f"profile-{profile_name}_collection-{collection}_variable-C01_res-1000m.tif"
        ),
        crs="EPSG:32720",
        bounds=(200000, 9400000, 300000, 9500000),
        value=10.0,
    )

    # Cell B — UTM zone 21S
    cell_b_dir = root / "loc-5D41L" / "date-20260101" / f"profile-{profile_name}"
    _create_test_tif(
        cell_b_dir
        / (
            "loc-5D41L_start-20260101T100022_end-20260101T100953_"
            f"profile-{profile_name}_collection-{collection}_variable-C01_res-1000m.tif"
        ),
        crs="EPSG:32721",
        bounds=(200000, 9400000, 300000, 9500000),
        value=20.0,
    )

    # Cell C — different date
    cell_c_dir = root / "loc-5D42L" / "date-20260102" / f"profile-{profile_name}"
    _create_test_tif(
        cell_c_dir
        / (
            "loc-5D42L_start-20260102T100022_end-20260102T100953_"
            f"profile-{profile_name}_collection-{collection}_variable-C02_res-1000m.tif"
        ),
        crs="EPSG:32720",
        bounds=(300000, 9400000, 400000, 9500000),
        value=30.0,
    )

    return root


# -----------------------------------------------------------------------
# Tests for scan_eoids_dir
# -----------------------------------------------------------------------


class TestScanEoidsDir:
    def test_scan_all(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree)
        assert len(results) == 3

    def test_filter_by_date(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, date="20260101")
        assert len(results) == 2
        for entry in results:
            assert entry["date"] == "20260101"

    def test_filter_by_profile(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, profile="goes_c01")
        assert len(results) == 3

    def test_filter_no_match(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, profile="nonexistent")
        assert len(results) == 0

    def test_filter_by_variable(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, variable="C02")
        assert len(results) == 1
        assert results[0]["variable"] == "C02"

    def test_filter_by_cell_id(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, cell_id="5D40L")
        assert len(results) == 1
        assert results[0]["loc"] == "5D40L"

    def test_filter_by_cell_id_with_underscore(self, eoids_tree):
        """Cell IDs with underscores should be normalized before matching."""
        results = scan_eoids_dir(eoids_tree, cell_id="5D_40L")
        assert len(results) == 1

    def test_filter_by_collection(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, collection="ABI-L1b-RadF")
        assert len(results) == 3

    def test_matches_filter_single_to_concatenated(self):
        """Filtering 'A' against file value 'A+B' should match."""
        assert _matches_filter("A", "A+B") is True

    def test_matches_filter_concatenated_to_concatenated(self):
        """Filtering 'A+B' against file value 'A+B' should match."""
        assert _matches_filter("A+B", "A+B") is True

    def test_matches_filter_concatenated_to_single(self):
        """Filtering 'A+B' against file value 'A' should match."""
        assert _matches_filter("A+B", "A") is True

    def test_matches_filter_no_overlap(self):
        """Filtering 'A' against file value 'B+C' should not match."""
        assert _matches_filter("A", "B+C") is False

    def test_matches_filter_none_filter(self):
        """None filter should always match."""
        assert _matches_filter(None, "A+B") is True

    def test_matches_filter_none_file(self):
        """None file value should never match a non-None filter."""
        assert _matches_filter("A", None) is False

    def test_combined_filters(self, eoids_tree):
        results = scan_eoids_dir(
            eoids_tree, date="20260101", variable="C01", profile="goes_c01"
        )
        assert len(results) == 2

    def test_entries_have_path(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree)
        for entry in results:
            assert "path" in entry
            assert entry["path"].exists()

    def test_entries_have_date(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree)
        for entry in results:
            assert "date" in entry
            assert entry["date"] is not None

    def test_scan_eoids_dir_filter_with_plus_concatenation(self, tmp_path):
        profile = AerProfile(
            name="rgb",
            resolution=1000.0,
            collections={"ABI-L1b-RadF": ["C01", "C02", "C03"]},
        )
        path = build_eoids_path(tmp_path, profile=profile, cell_id="36D61L")
        # Create the file so scan_eoids_dir can discover it
        path.write_text("")

        results = scan_eoids_dir(tmp_path, variable="C02")
        assert len(results) == 1

        results = scan_eoids_dir(tmp_path, variable="C99")
        assert len(results) == 0


# -----------------------------------------------------------------------
# Tests for load_eoids_tiles
# -----------------------------------------------------------------------


class TestLoadEoidsTiles:
    def test_load_basic(self, eoids_tree):
        tiles = load_eoids_tiles(eoids_tree, date="20260101")
        try:
            assert len(tiles) == 2
            for t in tiles:
                assert not t.closed
        finally:
            for t in tiles:
                t.close()

    def test_load_empty(self, eoids_tree):
        tiles = load_eoids_tiles(eoids_tree, profile="nonexistent")
        assert tiles == []


# -----------------------------------------------------------------------
# Tests for mosaic_eoids_tiles
# -----------------------------------------------------------------------


class TestMosaicEoidsTiles:
    def test_mosaic_basic(self, eoids_tree):
        """Mosaic two tiles from different UTM zones into EPSG:4326."""
        mosaic, transform, crs = mosaic_eoids_tiles(
            eoids_tree, date="20260101", target_crs="EPSG:4326"
        )
        assert isinstance(mosaic, np.ndarray)
        assert mosaic.ndim == 3  # (bands, height, width)
        assert mosaic.shape[0] == 1  # single band
        assert crs == CRS.from_epsg(4326)

    def test_mosaic_single_tile(self, eoids_tree):
        """Mosaicking a single tile should still work."""
        mosaic, transform, crs = mosaic_eoids_tiles(
            eoids_tree, cell_id="5D40L", target_crs="EPSG:4326"
        )
        assert mosaic.shape[0] == 1

    def test_mosaic_no_match_raises(self, eoids_tree):
        with pytest.raises(FileNotFoundError, match="No EOIDS tiles found"):
            mosaic_eoids_tiles(eoids_tree, profile="nonexistent")

    def test_mosaic_same_crs_no_reproject(self, eoids_tree):
        """When target CRS matches the tile CRS, no VRT warping is needed."""
        mosaic, transform, crs = mosaic_eoids_tiles(
            eoids_tree, cell_id="5D40L", target_crs="EPSG:32720"
        )
        assert crs == CRS.from_epsg(32720)

    def test_mosaic_has_data(self, eoids_tree):
        """The mosaic should contain non-zero data from the input tiles."""
        mosaic, _, _ = mosaic_eoids_tiles(
            eoids_tree, date="20260101", target_crs="EPSG:4326"
        )
        assert np.nanmax(mosaic) > 0

    def test_roundtrip_build_and_mosaic(self, tmp_path):
        """Build EOIDS paths, write tiles, then mosaic them."""
        root = tmp_path / "roundtrip"
        st = datetime.datetime(2026, 6, 15, 12, 0, 0)
        et = datetime.datetime(2026, 6, 15, 12, 10, 0)
        profile = AerProfile(
            name="goes_c01",
            resolution=1000.0,
            collections={"ABI-L1b-RadF": ["C01"]},
        )

        # Write two tiles via build_eoids_path
        for cell, lon_offset in [("1U_10L", 0), ("1U_11L", 1)]:
            path = build_eoids_path(
                local_dir=root,
                profile=profile,
                cell_id=cell,
                start_time=st,
                end_time=et,
            )
            _create_test_tif(
                path,
                crs="EPSG:4326",
                bounds=(-60.0 + lon_offset, 0.0, -59.0 + lon_offset, 1.0),
                value=42.0,
            )

        mosaic, transform, crs = mosaic_eoids_tiles(
            root, date="20260615", target_crs="EPSG:4326"
        )
        assert mosaic.shape[0] == 1
        assert np.any(mosaic == 42.0)

    def test_mosaic_sort_by_coverage_false(self, eoids_tree):
        """Skipping coverage sort should still produce a valid mosaic."""
        mosaic, transform, crs = mosaic_eoids_tiles(
            eoids_tree,
            date="20260101",
            target_crs="EPSG:4326",
            sort_by_coverage=False,
        )
        assert isinstance(mosaic, np.ndarray)
        assert mosaic.ndim == 3
        assert crs == CRS.from_epsg(4326)

    def test_mosaic_target_resolution(self, eoids_tree):
        """Downsampling via target_resolution should shrink the output."""
        mosaic_full, _, _ = mosaic_eoids_tiles(
            eoids_tree,
            date="20260101",
            target_crs="EPSG:4326",
            sort_by_coverage=False,
        )
        mosaic_down, _, _ = mosaic_eoids_tiles(
            eoids_tree,
            date="20260101",
            target_crs="EPSG:4326",
            sort_by_coverage=False,
            target_resolution=1.0,
        )
        # A 1-degree resolution mosaic must be smaller than the native one.
        assert mosaic_down.shape[1] < mosaic_full.shape[1]
        assert mosaic_down.shape[2] < mosaic_full.shape[2]
