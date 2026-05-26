from datetime import datetime
from typing import Any, cast

import geopandas as gpd
from aereo.grid import GridCell
from aereo.interfaces import AereoProfile, ExtractionTask, GridConfig
from aereo.schemas import AssetSchema
from aereo.serialization import TaskSerializer
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def _make_task(
    *,
    cell_id: str = "0U_0R",
    is_primary: bool = True,
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

    profile = AereoProfile(name="test_profile", resolution=100.0)
    grid_config = GridConfig(target_grid_dist=50_000)
    grid_cell = GridCell(
        d=50_000,
        geom=Polygon([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]),
        is_primary=is_primary,
        cell_id=cell_id,
    )

    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        profile=profile,
        uri="test_uri",
        grid_cells=[grid_cell],
        grid_config=grid_config,
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

    # Profile
    assert reconstructed.profile.name == original.profile.name
    assert reconstructed.profile.resolution == original.profile.resolution

    # Grid config
    assert reconstructed.grid_config == original.grid_config

    # URI
    assert reconstructed.uri == original.uri

    # Grid cells
    assert len(reconstructed.grid_cells) == 1
    assert reconstructed.grid_cells[0].id() == original.grid_cells[0].id()
    assert reconstructed.grid_cells[0].D == original.grid_cells[0].D
    assert reconstructed.grid_cells[0].is_primary == original.grid_cells[0].is_primary
    assert reconstructed.grid_cells[0].geom.equals_exact(
        original.grid_cells[0].geom, tolerance=1e-9
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
    """Tasks with several grid cells reconstruct every cell faithfully."""
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

    cells = [
        GridCell(
            d=10_000,
            geom=Polygon([[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]]),
            is_primary=True,
            cell_id="1U_1R",
        ),
        GridCell(
            d=10_000,
            geom=Polygon([[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]),
            is_primary=False,
            cell_id="1U_1R_OV",
        ),
    ]

    original = ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        profile=AereoProfile(name="multi", resolution=10.0),
        uri="out",
        grid_cells=cells,
        grid_config=GridConfig(target_grid_dist=10_000),
    )

    dest = tmp_path / "task_multi"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert len(reconstructed.grid_cells) == 2
    for orig, recon in zip(cells, reconstructed.grid_cells):
        assert recon.id() == orig.id()
        assert recon.D == orig.D
        assert recon.is_primary == orig.is_primary
        assert recon.geom.equals_exact(orig.geom, tolerance=1e-9)


def test_assets_crs_preserved(tmp_path: Any) -> None:
    """The assets GeoDataFrame CRS is preserved through GeoParquet round-trip."""
    serializer = TaskSerializer()
    original = _make_task()

    dest = tmp_path / "task_crs"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.assets.crs is not None
    assert reconstructed.assets.crs.to_epsg() == 4326


def test_profile_reconstruction_matches_original(tmp_path: Any) -> None:
    """Complex profiles with collections and params reconstruct identically."""
    serializer = TaskSerializer()
    profile = AereoProfile(
        name="complex",
        resolution=500.0,
        collections={"ABI-L1b-RadC": ["C01", "C02"]},
        padding=4,
        conform_to=(256, 256),
        plugin_hints={"extract": "aereo-extract-aws-goes"},
        search_params={"version": "061"},
        extract_params={"calibration": "reflectance"},
    )

    df = gpd.GeoDataFrame(
        {
            "id": ["x"],
            "collection": ["ABI-L1b-RadC"],
            "start_time": [datetime(2023, 1, 1)],
            "end_time": [datetime(2023, 1, 1)],
            "href": ["s3://x"],
        },
        geometry=[Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
        crs="EPSG:4326",
    )

    original = ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        profile=profile,
        uri="complex_uri",
        grid_cells=[
            GridCell(
                d=100_000,
                geom=Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
                is_primary=True,
                cell_id="0U_0R",
            )
        ],
        grid_config=GridConfig(target_grid_dist=100_000, target_grid_margin=6.8),
    )

    dest = tmp_path / "task_complex"
    serializer.serialize(original, dest)
    reconstructed = serializer.deserialize(dest)

    assert reconstructed.profile == profile
    assert reconstructed.grid_config.target_grid_margin == 6.8
