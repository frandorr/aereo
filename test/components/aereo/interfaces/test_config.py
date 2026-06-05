from aereo.pipeline.core import ExtractionJob
from aereo.builtins.search import SearchSTAC
from aereo.builtins.read import ReadODCSTAC
from aereo.builtins.reproject import ReprojectODC
from aereo.builtins.write import WriteGeoTIFF
from aereo.interfaces import GridConfig


def test_extraction_job_validation():
    """Verify that ExtractionJob model can be constructed and validated."""
    job = ExtractionJob(
        search=SearchSTAC(stac_api_url="https://stac", collections=["s2"]),
        pipeline=[ReadODCSTAC(), ReprojectODC(resolution=10.0), WriteGeoTIFF()],
        grid_config=GridConfig(target_grid_dist=50000),
        uri="out",
    )
    assert job.uri == "out"
    assert len(job.pipeline) == 3
    assert job.grid_config.target_grid_dist == 50000
