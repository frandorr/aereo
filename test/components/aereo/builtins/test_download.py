"""Tests for the built-in downloadAssets downloader plugin."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pandas as pd
from aereo.builtins.download import download_assets
from aereo.interfaces.core import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon


def _make_job(tmp_path: Any) -> ExtractionJob:
    return ExtractionJob(
        grid_dist=1000,
        output_uri=str(tmp_path / "out"),
        read=MagicMock(),
        write=MagicMock(),
    )


def _make_task(job: ExtractionJob) -> ExtractionTask:
    assets = gpd.GeoDataFrame(
        {
            "id": ["asset-1", "asset-2"],
            "collection": ["C1", "C1"],
            "start_time": [pd.Timestamp("2023-01-01")] * 2,
            "end_time": [pd.Timestamp("2023-01-02")] * 2,
            "href": ["s3://bucket/a.tif", "s3://bucket/b.tif"],
            "geometry": [
                Polygon([[0, 0], [1, 0], [1, 1], [0, 1]]),
                Polygon([[1, 1], [2, 1], [2, 2], [1, 2]]),
            ],
        },
        crs="EPSG:4326",
    )
    return ExtractionTask(
        id="task-1",
        assets=cast(GeoDataFrame[AssetSchema], assets),
        job=job,
    )


def test_download_assets_updates_href(tmp_path: Any) -> None:
    """The downloader updates assets['href'] to the returned local paths."""
    task = _make_task(_make_job(tmp_path))

    with patch(
        "aereo.builtins.download.download_task_assets",
        return_value=["/local/a.tif", "/local/b.tif"],
    ) as mock_download:
        downloaded_task = download_assets(task)

    mock_download.assert_called_once_with(
        task,
        downloader=None,
        download_workers=None,
    )
    assert downloaded_task is not task
    assert downloaded_task.assets["href"].tolist() == ["/local/a.tif", "/local/b.tif"]


def test_download_assets_forwards_downloader_and_workers(tmp_path: Any) -> None:
    """Custom downloader and worker count are forwarded to download_task_assets."""
    task = _make_task(_make_job(tmp_path))
    custom_downloader = MagicMock()

    with patch(
        "aereo.builtins.download.download_task_assets",
        return_value=["/local/a.tif", "/local/b.tif"],
    ) as mock_download:
        download_assets(task, downloader=custom_downloader, download_workers=4)

    mock_download.assert_called_once_with(
        task,
        downloader=custom_downloader,
        download_workers=4,
    )


def test_download_assets_preserves_other_columns(tmp_path: Any) -> None:
    """Non-href asset columns are preserved."""
    task = _make_task(_make_job(tmp_path))

    with patch(
        "aereo.builtins.download.download_task_assets",
        return_value=["/local/a.tif", "/local/b.tif"],
    ):
        downloaded_task = download_assets(task)

    assert downloaded_task.assets["id"].tolist() == ["asset-1", "asset-2"]
    assert downloaded_task.assets["collection"].tolist() == ["C1", "C1"]


def test_download_assets_keeps_input_task_unchanged(tmp_path: Any) -> None:
    """Because ExtractionTask is frozen, the input task must not be mutated."""
    task = _make_task(_make_job(tmp_path))
    original_hrefs = task.assets["href"].tolist()

    with patch(
        "aereo.builtins.download.download_task_assets",
        return_value=["/local/a.tif", "/local/b.tif"],
    ):
        download_assets(task)

    assert task.assets["href"].tolist() == original_hrefs
