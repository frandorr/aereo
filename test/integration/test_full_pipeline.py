"""Integration tests for the full search → prepare → extract Hamilton pipeline.

These tests exercise :class:`aereo.driver.AereoDriver` end-to-end with
self-contained mock plugins so that no external I/O (HTTP, S3, STAC APIs)
is required.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from types import ModuleType

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from aereo.discovery import StagePlugins
from aereo.driver import AereoDriver
from aereo.interfaces import GridConfig, PipelineProfile
from aereo.schemas import AssetSchema
from pandera.typing.geopandas import GeoDataFrame
from typing import Any, cast, Sequence


# ---------------------------------------------------------------------------
# Helpers — dynamic mock modules
# ---------------------------------------------------------------------------


def _make_mock_module(name: str, code: str) -> ModuleType:
    """Create a dynamic module from *code* and register it in ``sys.modules``."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    compiled = compile(code, name, "exec")
    exec(compiled, mod.__dict__)  # noqa: S102
    sys.modules[name] = mod
    return mod


def _make_mock_search_module(name: str = "mock_search") -> ModuleType:
    """Return a mock ``aereo.search`` plugin module."""
    return _make_mock_module(
        name,
        """
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from typing import Any

supported_collections = ("*",)

def search_results(
    aoi: BaseGeometry | None,
    start_datetime: str | None,
    end_datetime: str | None,
    collections: list[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> GeoDataFrame:
    df = pd.DataFrame({
        "id": ["asset-1"],
        "collection": ["TEST"],
        "start_time": pd.to_datetime(["2024-01-01 10:00:00"]),
        "end_time": pd.to_datetime(["2024-01-01 11:00:00"]),
        "href": ["https://example.com/asset.tif"],
        "geometry": [Point(0, 0)],
    })
    return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
""",
    )


def _make_mock_download_module(name: str = "mock_download") -> ModuleType:
    """Return a mock ``aereo.download`` plugin module."""
    return _make_mock_module(
        name,
        """
from __future__ import annotations

from typing import Any

supported_collections = ("*",)

def download_assets(task: Any) -> dict[str, str]:
    return {"asset-1": "/tmp/mock.tif"}

def extracted_assets(download_assets: dict[str, str]) -> dict[str, str]:
    return download_assets
""",
    )


def _make_mock_read_module(name: str = "mock_read") -> ModuleType:
    """Return a mock ``aereo.read`` plugin module."""
    return _make_mock_module(
        name,
        """
from __future__ import annotations

import numpy as np
import xarray as xr
from typing import Any

supported_collections = ("*",)

def read_scenes(extracted_assets: dict[str, str]) -> xr.Dataset:
    return xr.Dataset({
        "band": (["y", "x"], np.ones((4, 4), dtype=np.float32)),
    }, coords={"y": range(4), "x": range(4)})
""",
    )


def _make_mock_reproject_module(name: str = "mock_reproject") -> ModuleType:
    """Return a mock ``aereo.reproject`` plugin module."""
    return _make_mock_module(
        name,
        """
from __future__ import annotations

import xarray as xr
from typing import Any

supported_collections = ("*",)

def reproject_to_grid(
    read_scenes: xr.Dataset, geobox: Any = None, resampling: str = "nearest"
) -> xr.Dataset:
    return read_scenes
""",
    )


def _make_mock_write_module(name: str = "mock_write") -> ModuleType:
    """Return a mock ``aereo.write`` plugin module."""
    return _make_mock_module(
        name,
        """
from __future__ import annotations

import geopandas as gpd
import pandas as pd
import xarray as xr
from shapely.geometry import Point
from typing import Any

supported_collections = ("*",)

def write_cogs(
    reproject_to_grid: xr.Dataset, task: Any, compress: str = "deflate", zlevel: int = 1
) -> gpd.GeoDataFrame:
    df = pd.DataFrame({
        "grid_cell": ["cell-1"],
        "grid_dist": [100.0],
        "cell_geometry": [Point(0, 0).wkt],
        "cell_utm_crs": ["EPSG:32633"],
        "cell_utm_footprint": [Point(0, 0).wkt],
        "id": ["artifact-1"],
        "source_ids": ["asset-1"],
        "start_time": pd.to_datetime(["2024-01-01 10:00:00"]),
        "end_time": pd.to_datetime(["2024-01-01 11:00:00"]),
        "uri": ["file:///tmp/out.tif"],
        "geometry": [Point(0, 0)],
        "collection": ["TEST"],
    })
    return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
""",
    )


def _patch_driver_with_mocks(driver: AereoDriver) -> None:
    """Replace all stage plugins on *driver* with mock modules."""
    search_mod = _make_mock_search_module("mock_search_integration")
    download_mod = _make_mock_download_module("mock_download_integration")
    read_mod = _make_mock_read_module("mock_read_integration")
    reproject_mod = _make_mock_reproject_module("mock_reproject_integration")
    write_mod = _make_mock_write_module("mock_write_integration")

    for stage, mod in (
        ("search", search_mod),
        ("download", download_mod),
        ("read", read_mod),
        ("reproject", reproject_mod),
        ("write", write_mod),
    ):
        sp = StagePlugins()
        sp.register("mock", mod)
        setattr(driver, f"_{stage}_plugins", sp)

    # Process plugins — empty, no processors needed for basic flow.
    driver._process_plugins = StagePlugins()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_full_search_prepare_extract_flow(monkeypatch) -> None:
    """End-to-end: search returns assets, prepare returns tasks, extract returns artifacts."""
    drv = AereoDriver()
    _patch_driver_with_mocks(drv)

    profile = PipelineProfile(
        name="integration_test",
        resolution=100.0,
        collections={"TEST": ["band"]},
        plugin_hints={
            "search": "mock",
            "download": "mock",
            "read": "mock",
            "reproject": "mock",
            "write": "mock",
        },
    )

    # 1. Search
    result_gdf = drv.search(
        profile,
        aoi=None,
        start_datetime="2024-01-01",
        end_datetime="2024-01-02",
    )
    assert isinstance(result_gdf, gpd.GeoDataFrame)
    assert len(result_gdf) == 1
    assert result_gdf.iloc[0]["collection"] == "TEST"

    # 2. Prepare
    grid_config = GridConfig(target_grid_dist=50_000)
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks = drv.prepare(
            assets=result_gdf,
            profile=profile,
            grid_config=grid_config,
            aoi=None,
            uri=tmpdir,
            cells_per_task=10,
        )
        assert isinstance(tasks, list)
        assert len(tasks) >= 1
        task = tasks[0]
        assert task.profile.name == "integration_test"
        assert task.uri == tmpdir
        assert len(task.grid_cells) >= 1

        # 3. Extract
        artifacts = drv.extract(task)
        assert isinstance(artifacts, gpd.GeoDataFrame)
        assert len(artifacts) == 1
        assert artifacts.iloc[0]["collection"] == "TEST"


@pytest.mark.integration
def test_search_to_prepare_empty_assets() -> None:
    """An empty search result yields empty tasks without error."""
    drv = AereoDriver()

    # Patch search to return empty GeoDataFrame
    search_mod = _make_mock_module(
        "mock_search_empty",
        """
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry
from typing import Any

supported_collections = ("*",)

def search_results(
    aoi: BaseGeometry | None,
    start_datetime: str | None,
    end_datetime: str | None,
    collections: list[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        columns=["id", "collection", "start_time", "end_time", "href", "geometry"],
        geometry="geometry",
    )
""",
    )
    sp = StagePlugins()
    sp.register("mock", search_mod)
    drv._search_plugins = sp

    profile = PipelineProfile(
        name="empty_test", resolution=100.0, plugin_hints={"search": "mock"}
    )
    result_gdf = drv.search(profile, aoi=None, start_datetime=None, end_datetime=None)
    assert result_gdf.empty

    grid_config = GridConfig(target_grid_dist=50_000)
    tasks = drv.prepare(
        assets=result_gdf,
        profile=profile,
        grid_config=grid_config,
        aoi=None,
        uri="/tmp",
    )
    assert tasks == []


@pytest.mark.integration
def test_extract_with_parallel_processors(monkeypatch) -> None:
    """Extract compiles parallel processor config and builds a valid DAG."""
    drv = AereoDriver()
    _patch_driver_with_mocks(drv)

    # Inject a fake process plugin with two functions.
    process_mod = _make_mock_module(
        "mock_process",
        """
from __future__ import annotations

import xarray as xr
from typing import Any

supported_collections = ("*",)

def compute_ndvi(ds: xr.Dataset) -> xr.Dataset:
    return ds

def compute_ndwi(ds: xr.Dataset) -> xr.Dataset:
    return ds
""",
    )
    proc_sp = StagePlugins()
    proc_sp.register("mock", process_mod)
    drv._process_plugins = proc_sp

    profile = PipelineProfile(
        name="processor_test",
        resolution=100.0,
        post_processors=[
            {"parallel": ["compute_ndvi", "compute_ndwi"]},
            "compute_ndvi",
        ],
        plugin_hints={
            "search": "mock",
            "download": "mock",
            "read": "mock",
            "reproject": "mock",
            "write": "mock",
        },
    )

    # Build a minimal task manually so we don't need search/prepare.
    df = pd.DataFrame(
        {
            "id": ["a1"],
            "collection": ["TEST"],
            "start_time": pd.to_datetime(["2024-01-01 10:00:00"]),
            "end_time": pd.to_datetime(["2024-01-01 11:00:00"]),
            "href": ["https://example.com/a.tif"],
            "geometry": [Point(0, 0)],
        }
    )
    assets = cast(
        GeoDataFrame[AssetSchema],
        gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326"),
    )

    from aereo.interfaces import ExtractionTask

    task = ExtractionTask(
        assets=assets,
        profile=profile,
        uri="/tmp",
        grid_cells=[],
        grid_config=GridConfig(target_grid_dist=50_000),
    )

    # The extract method should compile processors and build the DAG.
    # Because the mock modules wire together, this succeeds.
    artifacts = drv.extract(task)
    assert isinstance(artifacts, gpd.GeoDataFrame)


@pytest.mark.integration
def test_client_api_uses_hamilton_driver(monkeypatch) -> None:
    """AereoClient.search / prepare_for_extraction / execute_tasks delegate to the driver."""
    from aereo.client import AereoClient

    client = AereoClient()
    drv = AereoDriver()
    _patch_driver_with_mocks(drv)
    monkeypatch.setattr(client, "_driver", drv)

    profile = PipelineProfile(
        name="client_api_test",
        resolution=100.0,
        collections={"TEST": ["band"]},
        plugin_hints={
            "search": "mock",
            "download": "mock",
            "read": "mock",
            "reproject": "mock",
            "write": "mock",
        },
    )

    # search
    results = client.search(profiles=cast(Sequence[Any], [profile]))
    assert isinstance(results, gpd.GeoDataFrame)
    assert len(results) == 1

    # prepare_for_extraction
    grid_config = GridConfig(target_grid_dist=50_000)
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks = client.prepare_for_extraction(
            search_results=results,
            profiles=cast(Sequence[Any], [profile]),
            grid_config=grid_config,
            uri=tmpdir,
            cells_per_task=10,
        )
        assert len(tasks) >= 1

        # execute_tasks
        artifacts = client.execute_tasks(tasks)
        assert isinstance(artifacts, gpd.GeoDataFrame)
        assert len(artifacts) == 1
