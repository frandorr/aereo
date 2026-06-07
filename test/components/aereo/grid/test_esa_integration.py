"""Integration test: verify Aereo grid cells exist in ESA MajorTOM global grid.

Requires the ESA Major-TOM repo cloned at ``/tmp/Major-TOM`` (see
``examples/compare_grid_esa_major_tom.py`` for manual setup).

"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from aereo.grid import GridDefinition
from shapely.geometry import Polygon, box

_ESA_GRID_PATH = Path("/tmp/Major-TOM/MajorTOM/grid.py")


# Dynamically import ESA's Grid class to avoid a hard import-time dependency.
def _load_esa_grid():
    import importlib.util

    spec = importlib.util.spec_from_file_location("MajorTOM.grid", str(_ESA_GRID_PATH))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.Grid


@pytest.mark.skipif(
    not _ESA_GRID_PATH.exists(),
    reason="ESA Major-TOM repo not found at /tmp/Major-TOM (run: git clone --depth 1 https://github.com/ESA-PhiLab/Major-TOM.git /tmp/Major-TOM)",
)
class TestESACompatibility:
    """Verify that on-the-fly Aereo cells exist in ESA's global grid."""

    @pytest.fixture(scope="class")
    def EsaGrid(self):
        return _load_esa_grid()

    @staticmethod
    def _esa_cells_for_aoi(esa_grid, polygon: Polygon) -> list[Polygon]:
        """Return ESA grid-cell footprints that intersect *polygon*."""
        cells: list[Polygon] = []
        for _, point in esa_grid.points.iterrows():
            footprint = esa_grid.get_bounded_footprint(point, buffer_ratio=0)
            if footprint.intersects(polygon):
                cells.append(footprint)
        return cells

    @staticmethod
    def _bounds_diff(a: Polygon, b: Polygon) -> float:
        return max(abs(x - y) for x, y in zip(a.bounds, b.bounds))

    def _assert_aereo_in_esa(self, aereo_polys, esa_polys, tol: float = 1e-10) -> None:
        """Assert every Aereo cell exists in the ESA grid within *tol*."""
        assert aereo_polys, "Aereo produced no cells"
        assert esa_polys, "ESA produced no cells"

        aereo_sorted = sorted(aereo_polys, key=lambda p: p.bounds)
        esa_sorted = sorted(esa_polys, key=lambda p: p.bounds)

        missing = 0
        max_diff = 0.0
        for ap in aereo_sorted:
            found = False
            for ep in esa_sorted:
                diff = self._bounds_diff(ap, ep)
                if diff < tol:
                    found = True
                    max_diff = max(max_diff, diff)
                    break
            if not found:
                missing += 1

        assert missing == 0, (
            f"{missing}/{len(aereo_polys)} Aereo cells not found in ESA grid "
            f"(max diff: {max_diff:.2e}°)"
        )

    @pytest.mark.parametrize(
        "aoi_bounds,d",
        [
            ((10.0, 45.0, 12.0, 47.0), 10_000),  # even row_count
            ((-1.0, -1.0, 1.0, 1.0), 10_000),  # even row_count
            ((-1.0, -1.0, 1.0, 1.0), 32_000),  # odd row_count
            ((0.0, 0.0, 1.0, 1.0), 32_000),  # odd row_count, asymmetric
            ((10.0, 45.0, 12.0, 47.0), 5_000),  # even row_count
        ],
    )
    def test_aereo_cells_exist_in_esa_grid(self, EsaGrid, aoi_bounds, d):
        """All Aereo cells for an AOI must exist in ESA's global grid."""
        aoi = box(*aoi_bounds)

        aereo_grid = GridDefinition(d=d, overlap=False)
        aereo_polys = [
            c.geom for c in aereo_grid.generate_grid_cells(aoi) if c.is_primary
        ]

        # ESA's range filtering can exclude boundary cells; use a buffer.
        minx, miny, maxx, maxy = aoi.bounds
        rc = math.ceil(math.pi * 6378.137 / (d / 1000))
        buf_lat = max(2, int(180 / rc) + 1)
        buf_lon = max(2, int(360 / rc) + 1)
        esa_grid = EsaGrid(
            dist=d / 1000.0,
            latitude_range=(math.floor(miny) - buf_lat, math.ceil(maxy) + buf_lat),
            longitude_range=(math.floor(minx) - buf_lon, math.ceil(maxx) + buf_lon),
        )
        esa_polys = self._esa_cells_for_aoi(esa_grid, aoi)

        self._assert_aereo_in_esa(aereo_polys, esa_polys)
