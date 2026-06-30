from datetime import datetime
from typing import Any, cast

import geopandas as gpd
from aereo.builtins.read import read_odc_stac
from aereo.builtins.write import write_geotiff
from aereo.interfaces import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from aereo.executors._serialization import _TaskSerializer
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry


def _make_task(
    *,
    aoi: Polygon | None = None,
    job_target_aoi: Polygon | None = None,
    task_context: dict[str, Any] | None = None,
) -> ExtractionTask:
    """Build a minimal but realistic ExtractionTask for serializer tests."""
    df = gpd.GeoDataFrame(
        {
            "id": ["asset_1"],
            "collection": ["GOES"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
            "end_time": [datetime(2023, 1, 1, 12, 30)],
            "href": ["s3://bucket/key.tif"],
        },
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
        crs="EPSG:4326",
    )

    job = ExtractionJob(
        name="test-job",
        grid_dist=50_000,
        output_uri="test_uri",
        read=read_odc_stac,
        write=write_geotiff,
        target_aoi=job_target_aoi,
    )

    return ExtractionTask(
        id="task-1",
        assets=cast(GeoDataFrame[AssetSchema], df),
        job=job,
        aoi=aoi,
        task_context=task_context or {},
    )


def test_round_trip_basic(tmp_path: Any) -> None:
    """Serialize and deserialize a basic task; assert equality."""
    serializer = _TaskSerializer()
    original = _make_task()

    dest = tmp_path / "task_dir"
    serializer.serialize(original, dest)

    reconstructed = serializer.deserialize(dest)

    # Task id
    assert reconstructed.id == original.id

    # Assets
    assert len(reconstructed.assets) == len(original.assets)
    assert list(reconstructed.assets["id"]) == ["asset_1"]
    assert list(reconstructed.assets["collection"]) == ["GOES"]

    # Reader / writer
    assert type(reconstructed.read) is type(original.read)
    assert type(reconstructed.write) is type(original.write)

    # Grid config
    assert reconstructed.grid_dist == original.grid_dist

    # output URI
    assert reconstructed.output_uri == original.output_uri

    # Task context
    assert reconstructed.task_context == original.task_context


def test_round_trip_with_task_aoi(tmp_path: Any) -> None:
    """Task-level AOI geometry survives round-trip via WKT."""
    serializer = _TaskSerializer()
    aoi = Polygon([[-1, -1], [2, -1], [2, 2], [-1, 2]])
    original = _make_task(aoi=aoi)

    dest = tmp_path / "task_aoi"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert isinstance(reconstructed.aoi, BaseGeometry)
    assert reconstructed.aoi.equals_exact(aoi, tolerance=1e-9)


def test_round_trip_with_job_aoi(tmp_path: Any) -> None:
    """Job-level target AOI geometry survives round-trip via WKT stored on the job."""
    serializer = _TaskSerializer()
    aoi = Polygon([[-1, -1], [2, -1], [2, 2], [-1, 2]])
    original = _make_task(job_target_aoi=aoi)

    dest = tmp_path / "job_aoi"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert isinstance(reconstructed.job.target_aoi, BaseGeometry)
    assert reconstructed.job.target_aoi.equals_exact(aoi, tolerance=1e-9)


def test_round_trip_task_context(tmp_path: Any) -> None:
    """Arbitrary task_context metadata is preserved."""
    serializer = _TaskSerializer()
    ctx = {"chunk_id": 7, "total_chunks": 42, "extractor_hint": "aereo-extract-dummy"}
    original = _make_task(task_context=ctx)

    dest = tmp_path / "task_ctx"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.task_context == ctx


def test_assets_crs_preserved(tmp_path: Any) -> None:
    """The assets GeoDataFrame CRS is preserved through GeoParquet round-trip."""
    serializer = _TaskSerializer()
    original = _make_task()

    dest = tmp_path / "task_crs"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.assets.crs is not None
    assert reconstructed.assets.crs.to_epsg() == 4326


def test_serialize_to_bytes_round_trip() -> None:
    """Task round-trips through a zip byte payload."""
    serializer = _TaskSerializer()
    original = _make_task()

    payload = serializer.serialize_to_bytes(original)
    reconstructed = serializer.deserialize_from_bytes(payload)

    assert reconstructed.id == original.id
    assert len(reconstructed.assets) == len(original.assets)
    assert type(reconstructed.read) is type(original.read)
    assert reconstructed.grid_dist == original.grid_dist
    assert reconstructed.task_context == original.task_context


def test_serialize_to_bytes_preserved_crs() -> None:
    """Assets CRS survives byte payload round-trip."""
    serializer = _TaskSerializer()
    original = _make_task()

    payload = serializer.serialize_to_bytes(original)
    reconstructed = serializer.deserialize_from_bytes(payload)

    assert reconstructed.assets.crs is not None
    assert reconstructed.assets.crs.to_epsg() == 4326
