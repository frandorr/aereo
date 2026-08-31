"""Tests for the per-task artifact cache."""

from __future__ import annotations

from typing import Any, cast

import geopandas as gpd
import pandas as pd
from aereo.builtins.read import read_odc_stac
from aereo.builtins.write import write_geotiff
from aereo.cache import TaskResultCache
from aereo.interfaces.core import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import ArtifactSchema, AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def _make_task(
    output_uri: str = "test-uri",
    task_id: str = "task-0",
    read: Any = read_odc_stac,
    write: Any = write_geotiff,
    overwrite: bool = False,
    postprocess: Any = None,
) -> ExtractionTask:
    """Return a minimal ExtractionTask for testing the cache."""
    valid_df = gpd.GeoDataFrame(
        {
            "id": ["asset-1"],
            "collection": ["C1"],
            "geometry": [Polygon([[0, 0], [1, 0], [1, 1], [0, 1]])],
            "start_time": [pd.Timestamp("2024-01-01")],
            "end_time": [pd.Timestamp("2024-01-02")],
            "href": ["https://example.com/asset.tif"],
        },
        crs="EPSG:4326",
    )

    job = ExtractionJob(
        name="test-job",
        grid_dist=50_000,
        output_uri=output_uri,
        read=read,
        write=write,
        overwrite=overwrite,
        postprocess=postprocess,
    )
    return ExtractionTask(
        id=task_id,
        assets=cast(GeoDataFrame[AssetSchema], valid_df),
        job=job,
    )


def test_fingerprint_is_stable(tmp_path):
    """Identical tasks produce identical fingerprints."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path))
    assert cache.fingerprint(task) == cache.fingerprint(task)


def test_fingerprint_changes_with_assets(tmp_path):
    """Changing asset identifiers changes the fingerprint."""
    cache = TaskResultCache()
    task1 = _make_task(output_uri=str(tmp_path))

    task2_assets = cast(GeoDataFrame[AssetSchema], task1.assets.copy())
    task2_assets.loc[0, "id"] = "asset-2"
    task2 = ExtractionTask(
        id=task1.id,
        assets=task2_assets,
        job=task1.job,
    )

    assert cache.fingerprint(task1) != cache.fingerprint(task2)


def test_fingerprint_changes_with_read_write(tmp_path):
    """Changing the read/write pipeline changes the fingerprint."""
    cache = TaskResultCache()
    task1 = _make_task(output_uri=str(tmp_path))
    task2 = _make_task(
        output_uri=str(tmp_path),
        read=read_odc_stac,
        write=lambda ds, path, **kwargs: path,
    )

    assert cache.fingerprint(task1) != cache.fingerprint(task2)


def test_cache_round_trip(tmp_path):
    """Saved artifacts can be loaded back intact."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path))

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
    task = _make_task(output_uri=str(tmp_path))
    assert cache.load(task) is None


def test_cache_path_is_under_output_uri(tmp_path):
    """Cache files are stored under the task output_uri."""
    cache = TaskResultCache()
    task = _make_task(output_uri=str(tmp_path))
    path = cache.path(task)
    assert path.relative_to(tmp_path)
    assert ".aereo_cache" in path.parts


def _processor(ds, a=0, **kwargs):
    return ds


def _processor_b(ds, a=0, **kwargs):
    return ds


def test_fingerprint_stable_with_callable_kwarg(tmp_path):
    """A function in plugin kwargs must not leak its per-process repr address.

    Regression test: ``json.dumps(default=str)`` on a function embeds its
    memory address, so every process fingerprinted the same task differently
    and the cache never hit (e.g. ``read_odc_stac(patch_url=pc.sign)``).
    """
    from functools import partial

    cache = TaskResultCache()
    task1 = _make_task(
        output_uri=str(tmp_path), read=partial(read_odc_stac, patch_url=_processor)
    )
    task2 = _make_task(
        output_uri=str(tmp_path), read=partial(read_odc_stac, patch_url=_processor)
    )
    assert cache.fingerprint(task1) == cache.fingerprint(task2)


def test_fingerprint_changes_with_callable_kwarg(tmp_path):
    """Swapping the callable kwarg changes the fingerprint."""
    from functools import partial

    cache = TaskResultCache()
    task1 = _make_task(
        output_uri=str(tmp_path), read=partial(read_odc_stac, patch_url=_processor)
    )
    task2 = _make_task(
        output_uri=str(tmp_path), read=partial(read_odc_stac, patch_url=_processor_b)
    )
    assert cache.fingerprint(task1) != cache.fingerprint(task2)


def test_fingerprint_changes_with_postprocess_list_kwargs(tmp_path):
    """postprocess lists are fingerprinted per-processor, not collapsed to 'list'."""
    from functools import partial

    cache = TaskResultCache()
    task1 = _make_task(output_uri=str(tmp_path), postprocess=[partial(_processor, a=1)])
    task2 = _make_task(output_uri=str(tmp_path), postprocess=[partial(_processor, a=2)])
    assert cache.fingerprint(task1) != cache.fingerprint(task2)
