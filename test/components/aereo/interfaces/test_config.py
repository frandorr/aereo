from aereo.builtins.read import read_odc_stac
from aereo.builtins.write import write_geotiff
from aereo.pipeline.core import ExtractionJob


def test_extraction_job_validation():
    """Verify that ExtractionJob model can be constructed and validated."""
    job = ExtractionJob(
        read=read_odc_stac,
        write=write_geotiff,
        grid_dist=50000,
        output_uri="out",
    )
    assert job.output_uri == "out"
    assert job.read is not None
    assert job.write is not None
    assert job.grid_dist == 50000
