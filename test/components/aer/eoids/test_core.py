import datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from aer.eoids import (
    build_eoids_path,
    load_eoids_tiles,
    mosaic_eoids_tiles,
    parse_eoids_filename,
    scan_eoids_dir,
)


# -----------------------------------------------------------------------
# Existing tests for build_eoids_path (preserved)
# -----------------------------------------------------------------------


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


# -----------------------------------------------------------------------
# Tests for parse_eoids_filename
# -----------------------------------------------------------------------


class TestParseEoidsFilename:
    def test_full_filename(self):
        meta = parse_eoids_filename(
            "loc-0U38L_start-20260101T100022_end-20260101T100953_"
            "sat-goes_east_prod-RadF_band-C01_res-1000m.tif"
        )
        assert meta == {
            "loc": "0U38L",
            "start": "20260101T100022",
            "end": "20260101T100953",
            "sat": "goes_east",
            "prod": "RadF",
            "band": "C01",
            "res": "1000m",
        }

    def test_with_full_path(self):
        meta = parse_eoids_filename(
            "/data/loc-5D40L/date-20260101/sat-goes_east/"
            "loc-5D40L_start-20260101T100022_end-20260101T100953_"
            "sat-goes_east_prod-RadF_band-C01_res-1000m.tif"
        )
        assert meta["loc"] == "5D40L"
        assert meta["sat"] == "goes_east"

    def test_minimal_filename(self):
        meta = parse_eoids_filename("loc-36D61L_prod-StaticMask.tif")
        assert meta == {"loc": "36D61L", "prod": "StaticMask"}

    def test_with_desc(self):
        meta = parse_eoids_filename("loc-36D61L_desc-cloudprob.nc")
        assert meta == {"loc": "36D61L", "desc": "cloudprob"}

    def test_empty_filename(self):
        meta = parse_eoids_filename("random_file.tif")
        assert meta == {}

    def test_path_object(self):
        meta = parse_eoids_filename(Path("/some/dir/loc-1U2L_band-C02.tif"))
        assert meta == {"loc": "1U2L", "band": "C02"}


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

    # Cell A — UTM zone 20S
    cell_a_dir = root / "loc-5D40L" / "date-20260101" / "sat-goes_east"
    _create_test_tif(
        cell_a_dir
        / "loc-5D40L_start-20260101T100022_end-20260101T100953_sat-goes_east_prod-RadF_band-C01_res-1000m.tif",
        crs="EPSG:32720",
        bounds=(200000, 9400000, 300000, 9500000),
        value=10.0,
    )

    # Cell B — UTM zone 21S
    cell_b_dir = root / "loc-5D41L" / "date-20260101" / "sat-goes_east"
    _create_test_tif(
        cell_b_dir
        / "loc-5D41L_start-20260101T100022_end-20260101T100953_sat-goes_east_prod-RadF_band-C01_res-1000m.tif",
        crs="EPSG:32721",
        bounds=(200000, 9400000, 300000, 9500000),
        value=20.0,
    )

    # Cell C — different date
    cell_c_dir = root / "loc-5D42L" / "date-20260102" / "sat-goes_east"
    _create_test_tif(
        cell_c_dir
        / "loc-5D42L_start-20260102T100022_end-20260102T100953_sat-goes_east_prod-RadF_band-C02_res-1000m.tif",
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

    def test_filter_by_satellite(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, satellite="goes_east")
        assert len(results) == 3

    def test_filter_no_match(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, satellite="goes_west")
        assert len(results) == 0

    def test_filter_by_band(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, band="C02")
        assert len(results) == 1
        assert results[0]["band"] == "C02"

    def test_filter_by_cell_id(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, cell_id="5D40L")
        assert len(results) == 1
        assert results[0]["loc"] == "5D40L"

    def test_filter_by_cell_id_with_underscore(self, eoids_tree):
        """Cell IDs with underscores should be normalized before matching."""
        results = scan_eoids_dir(eoids_tree, cell_id="5D_40L")
        assert len(results) == 1

    def test_filter_by_product(self, eoids_tree):
        results = scan_eoids_dir(eoids_tree, product="RadF")
        assert len(results) == 3

    def test_combined_filters(self, eoids_tree):
        results = scan_eoids_dir(
            eoids_tree, date="20260101", band="C01", satellite="goes_east"
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
        tiles = load_eoids_tiles(eoids_tree, satellite="nonexistent")
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
            mosaic_eoids_tiles(eoids_tree, satellite="nonexistent")

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

        # Write two tiles via build_eoids_path
        for cell, lon_offset in [("1U_10L", 0), ("1U_11L", 1)]:
            path = build_eoids_path(
                local_dir=root,
                cell_id=cell,
                start_time=st,
                end_time=et,
                satellite="goes_east",
                product="RadF",
                band="C01",
                resolution=1000,
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
