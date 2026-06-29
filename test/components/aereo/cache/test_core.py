"""Tests for the per-task artifact cache."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import geopandas as gpd
import pandas as pd
from aereo.builtins.read import read_odc_stac
from aereo.builtins.reproject import reproject_odc
from aereo.builtins.write import write_geotiff
from aereo.cache import TaskResultCache
from aereo.interfaces.core import (
    ExtractionTask,
    ExtractConfig,
    GridConfig,
    PatchConfig,
)
from aereo.pipeline import ExtractionJob
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def _make_task(
    output_uri: str = "test-uri",
    task_context: dict[str, Any] | None = None,
    patches: list[Any] | None = None,
    extract: ExtractConfig | None = None,
    overwrite: bool = False,
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing the cache."""
    valid_df = pd.DataFrame(columns=list(AssetSchema.to_schema().columns.keys()))
    valid_df.loc[0] = {col: "test" for col in AssetSchema.to_schema().columns.keys()}
    valid_df["geometry"] = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    valid_df["collection"] = "C1"
    valid_df["id"] = "asset-1"
    valid_df["start_time"] = pd.Timestamp("2024-01-01")
    valid_df["end_time"] = pd.Timestamp("2024-01-02")
    valid_df["href"] = "https://example.com/asset.tif"

    grid_config = GridConfig(target_grid_dist=50_000)
    extract = extract or ExtractConfig(
        read=read_odc_stac,
        reproject=reproject_odc,
        write=write_geotiff,
    )

    job = ExtractionJob(
        grid_config=grid_config,
        patch_config=PatchConfig(resolution=10.0),
        output_uri=output_uri,
        extract=extract,
        overwrite=overwrite,
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], valid_df),
        job=job,
        patches=patches or [],
        task_context=task_context or {},
    )


def _mock_patch(patch_id: str) -> MagicMock:
    """Return a minimal mock patch with the given id."""
    mock = MagicMock()
    mock.id = patch_id
    mock.cell_geometry = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    mock.resolution = 10.0
    mock.margin = 0.0
    mock.padding = 0
    mock.conform_to = None
    return mock


def test_fingerprint_is_stable(tmp_path):
    """Identical tasks produce identical fingerprints."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path), patches=[_mock_patch("c1")])
    assert cache.fingerprint(task) == cache.fingerprint(task)


def test_fingerprint_changes_with_assets(tmp_path):
    """Changing asset identifiers changes the fingerprint."""
    cache = TaskResultCache()
    task1 = _make_task(output_uri=str(tmp_path), patches=[_mock_patch("c1")])

    task2_assets = cast(GeoDataFrame[AssetSchema], task1.assets.copy())
    task2_assets.loc[0, "id"] = "asset-2"
    task2 = cast(
        ExtractionTask,
        task1.__class__(
            assets=task2_assets,
            job=task1.job,
            patches=task1.patches,
            task_context=task1.task_context,
        ),
    )

    assert cache.fingerprint(task1) != cache.fingerprint(task2)


def test_fingerprint_changes_with_extract_config(tmp_path):
    """Changing the extract pipeline changes the fingerprint."""
    from aereo.builtins.processor import normalize

    cache = TaskResultCache()
    task1 = _make_task(output_uri=str(tmp_path), patches=[_mock_patch("c1")])
    task2 = _make_task(
        output_uri=str(tmp_path),
        patches=[_mock_patch("c1")],
        extract=ExtractConfig(
            read=read_odc_stac,
            reproject=reproject_odc,
            write=write_geotiff,
            postprocess=[normalize],
        ),
    )

    assert cache.fingerprint(task1) != cache.fingerprint(task2)


def test_cache_round_trip(tmp_path):
    """Saved artifacts can be loaded back intact."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path), patches=[_mock_patch("c1")])

    geom = Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])
    artifacts = gpd.GeoDataFrame(
        {
            "grid_cell": ["c1"],
            "grid_dist": [50000],
            "cell_geometry": gpd.GeoSeries([geom], crs="EPSG:4326"),
            "cell_utm_crs": ["EPSG:32630"],
            "cell_utm_footprint": gpd.GeoSeries([geom], crs="EPSG:32630"),
            "id": ["artifact-1"],
            "source_ids": ["asset-1"],
            "start_time": [pd.Timestamp("2024-01-01")],
            "end_time": [pd.Timestamp("2024-01-02")],
            "uri": [str(tmp_path / "artifact.tif")],
            "collection": ["C1"],
        },
        geometry=gpd.GeoSeries([geom], crs="EPSG:4326"),
    )

    cache.save(task, cast(GeoDataFrame[ArtifactSchema], artifacts))
    loaded = cache.load(task)

    assert loaded is not None
    assert len(loaded) == 1
    assert loaded.iloc[0]["id"] == "artifact-1"


def test_cache_miss_returns_none(tmp_path):
    """Loading a cache that does not exist returns None."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path), patches=[_mock_patch("c1")])
    assert cache.load(task) is None


def test_cache_path_is_under_output_uri(tmp_path):
    """Cache files are stored under the task output_uri."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path), patches=[_mock_patch("c1")])
    path = cache.path(task)
    assert path.relative_to(tmp_path)
    assert ".aereo_cache" in path.parts
