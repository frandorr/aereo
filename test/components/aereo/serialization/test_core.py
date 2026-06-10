from datetime import datetime
from typing import Any, cast

import geopandas as gpd
from aereo.grid import ExtractionPatch
from aereo.interfaces import ExtractConfig, ExtractionTask, GridConfig, PatchConfig
from aereo.schemas import AssetSchema
from aereo.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon

from aereo.builtins.read import ReadODCSTAC
from aereo.builtins.reproject import ReprojectODC
from aereo.builtins.write import WriteGeoTIFF


def _make_task(
    *,
    cell_id: str = "0U_0R",
    aoi: Polygon | None = None,
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

    extract = ExtractConfig(
        read=ReadODCSTAC(),
        reproject=ReprojectODC(resolution=100.0),
        write=WriteGeoTIFF(),
    )
    grid_config = GridConfig(target_grid_dist=50_000)
    patch_config = PatchConfig(resolution=100.0, margin=10.0, padding=2)
    patch = ExtractionPatch(
        id=cell_id,
        d=50_000,
        cell_geometry=Polygon([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]),
        resolution=100.0,
        margin=10.0,
        padding=2,
    )

    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        extract=extract,
        uri="test_uri",
        patches=[patch],
        grid_config=grid_config,
        patch_config=patch_config,
        aoi=aoi,
        task_context=task_context or {},
    )


def test_round_trip_basic(tmp_path: Any) -> None:
    """Serialize and deserialize a basic task; assert equality."""
    serializer = TaskSerializer()
    original = _make_task()

    dest = tmp_path / "task_dir"
    serializer.serialize(original, dest)

    reconstructed = serializer.deserialize(dest)

    # Assets
    assert len(reconstructed.assets) == len(original.assets)
    assert list(reconstructed.assets["id"]) == ["asset_1"]
    assert list(reconstructed.assets["collection"]) == ["GOES"]

    # Extract
    assert type(reconstructed.extract.read) is type(original.extract.read)
    assert type(reconstructed.extract.reproject) is type(original.extract.reproject)
    assert type(reconstructed.extract.write) is type(original.extract.write)

    # Grid config
    assert reconstructed.grid_config == original.grid_config

    # Patch config
    assert reconstructed.patch_config == original.patch_config

    # URI
    assert reconstructed.uri == original.uri

    # Patches
    assert len(reconstructed.patches) == 1
    assert reconstructed.patches[0].id == original.patches[0].id
    assert reconstructed.patches[0].d == original.patches[0].d
    assert reconstructed.patches[0].resolution == original.patches[0].resolution
    assert reconstructed.patches[0].margin == original.patches[0].margin
    assert reconstructed.patches[0].padding == original.patches[0].padding
    assert reconstructed.patches[0].conform_to == original.patches[0].conform_to
    assert reconstructed.patches[0].cell_geometry.equals_exact(
        original.patches[0].cell_geometry, tolerance=1e-9
    )

    # AOI
    assert reconstructed.aoi is None

    # Task context
    assert reconstructed.task_context == original.task_context


def test_round_trip_with_aoi(tmp_path: Any) -> None:
    """AOI geometry survives round-trip via WKT."""
    serializer = TaskSerializer()
    aoi = Polygon([[-1, -1], [2, -1], [2, 2], [-1, 2]])
    original = _make_task(aoi=aoi)

    dest = tmp_path / "task_aoi"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.aoi is not None
    assert reconstructed.aoi.equals_exact(aoi, tolerance=1e-9)


def test_round_trip_task_context(tmp_path: Any) -> None:
    """Arbitrary task_context metadata is preserved."""
    serializer = TaskSerializer()
    ctx = {"chunk_id": 7, "total_chunks": 42, "extractor_hint": "aereo-extract-dummy"}
    original = _make_task(task_context=ctx)

    dest = tmp_path / "task_ctx"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.task_context == ctx


def test_round_trip_multiple_grid_cells(tmp_path: Any) -> None:
    """Tasks with several patches reconstruct every patch faithfully."""
    serializer = TaskSerializer()

    df = gpd.GeoDataFrame(
        {
            "id": ["a", "b"],
            "collection": ["S2", "S2"],
            "start_time": [datetime(2023, 6, 1), datetime(2023, 6, 1)],
            "end_time": [datetime(2023, 6, 1, 0, 15), datetime(2023, 6, 1, 0, 15)],
            "href": ["http://a", "http://b"],
        },
        geometry=[
            Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
            Polygon([[1, 1], [2, 1], [2, 2], [1, 2]]),
        ],
        crs="EPSG:4326",
    )

    patches = [
        ExtractionPatch(
            id="1U_1R",
            d=10_000,
            cell_geometry=Polygon([[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]]),
            resolution=10.0,
            margin=5.0,
            padding=0,
        ),
        ExtractionPatch(
            id="1U_1R_OV",
            d=10_000,
            cell_geometry=Polygon([[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]),
            resolution=10.0,
            margin=5.0,
            padding=0,
        ),
    ]

    extract = ExtractConfig(
        read=ReadODCSTAC(),
        reproject=ReprojectODC(resolution=10.0),
        write=WriteGeoTIFF(),
    )
    original = ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        extract=extract,
        uri="out",
        patches=patches,
        grid_config=GridConfig(target_grid_dist=10_000),
        patch_config=PatchConfig(resolution=10.0, margin=5.0, padding=0),
    )

    dest = tmp_path / "task_multi"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert len(reconstructed.patches) == 2
    for orig, recon in zip(patches, reconstructed.patches):
        assert recon.id == orig.id
        assert recon.d == orig.d
        assert recon.resolution == orig.resolution
        assert recon.margin == orig.margin
        assert recon.cell_geometry.equals_exact(orig.cell_geometry, tolerance=1e-9)


def test_assets_crs_preserved(tmp_path: Any) -> None:
    """The assets GeoDataFrame CRS is preserved through GeoParquet round-trip."""
    serializer = TaskSerializer()
    original = _make_task()

    dest = tmp_path / "task_crs"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.assets.crs is not None
    assert reconstructed.assets.crs.to_epsg() == 4326
