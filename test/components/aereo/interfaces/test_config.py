from aereo.pipeline.core import ExtractionJob
from aereo.builtins.read import ReadODCSTAC
from aereo.builtins.reproject import ReprojectODC
from aereo.builtins.write import WriteGeoTIFF
from aereo.interfaces import GridConfig, PatchConfig, ExtractConfig


def test_extraction_job_validation():
    """Verify that ExtractionJob model can be constructed and validated."""
    job = ExtractionJob(
        extract=ExtractConfig(
            read=ReadODCSTAC(),
            reproject=ReprojectODC(),
            write=WriteGeoTIFF(),
        ),
        grid_config=GridConfig(target_grid_dist=50000),
        patch_config=PatchConfig(resolution=10.0),
        output_uri="out",
    )
    assert job.output_uri == "out"
    assert job.extract.read is not None
    assert job.grid_config.target_grid_dist == 50000
