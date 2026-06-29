from aereo.builtins.read import read_odc_stac
from aereo.pipeline.core import ExtractionJob


def test_extraction_job_validation():
    """Verify that ExtractionJob model can be constructed and validated."""
    job = ExtractionJob(
        read=read_odc_stac,
        grid_dist=50000,
        output_uri="out",
    )
    assert job.output_uri == "out"
    assert job.read is not None
    assert job.grid_dist == 50000
