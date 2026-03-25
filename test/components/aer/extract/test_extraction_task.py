from datetime import datetime
from pathlib import Path
from aer.extract.core import ExtractionTask
from aer.search.core import SearchResult
from aer.spatial import GridRow
from shapely.geometry import Polygon


def test_extraction_task_creation() -> None:
    """Test that an ExtractionTask can be created with legitimate values."""
    # Create a GridRow with grid cell data
    grid_row = GridRow(
        name="10U_20R",
        row="10U",
        col="20R",
        utm_zone="31N",
        epsg="EPSG:32615",
        dist=100,
        geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
        cell_bounds=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
    )

    # Create a SearchResult with grid data
    search_result = SearchResult(
        unique_id="U1",
        product_id="test_product",
        granule_id="granule_1",
        start_time=datetime(2025, 1, 1),
        end_time=datetime(2025, 1, 2),
        overlap_mode="contains",
        grid=grid_row,
    )

    task = ExtractionTask(
        search_result=search_result,
        output_dir=Path("/tmp/output"),
        extraction_params={"res": 1000},
    )

    # Access grid_cell via the search_result property
    assert task.search_result.grid_cell == grid_row.grid_cell
    assert task.search_result == search_result
    assert task.output_dir == Path("/tmp/output")
    assert task.extraction_params["res"] == 1000
