"""Real-world AEREO + Hamilton example with plugin_hints.

Users can override the default plugin selection per-profile via
``plugin_hints`` (same concept as current AereoProfile.plugin_hints).

Resolution order:
  1. If plugin_hint is provided for a stage, use that specific plugin.
  2. Otherwise, fall back to collection-based auto-resolution.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import geopandas as gpd
import pandas as pd
import xarray as xr
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry.base import BaseGeometry

GridCell = Any  # placeholder


# =============================================================================
# 0.  DISCOVERY — entry points per-plugin, with collection matching
# =============================================================================

def _discover_plugins(group: str) -> dict[str, Any]:
    """Discover Hamilton modules by entry-point group.

    Returns two structures:
      • name_to_module:  {entry_point_name: module}  — for plugin_hint lookup
      • collection_to_module: {collection: module}   — for auto-resolution
    """
    name_to_module: dict[str, Any] = {}
    collection_to_module: dict[str, Any] = {}
    wildcard_module: Any | None = None

    for ep in importlib.metadata.entry_points(group=group):
        try:
            mod = importlib.import_module(ep.value)
            name_to_module[ep.name] = mod

            collections = getattr(mod, "supported_collections", ("*",))
            if "*" in collections:
                wildcard_module = mod
            for col in collections:
                if col != "*":
                    collection_to_module[col] = mod
        except Exception as exc:
            print(f"Failed to load {group} plugin {ep.name}: {exc}")

    return name_to_module, collection_to_module, wildcard_module


def _resolve_plugin(
    stage: str,
    collection: str,
    plugin_hint: str | None,
    name_to_module: dict[str, Any],
    collection_to_module: dict[str, Any],
    wildcard_module: Any | None,
) -> Any:
    """Resolve which plugin module to use for a given stage.

    Priority:
      1. plugin_hint (explicit user choice)
      2. collection match (auto-discovery)
      3. wildcard fallback
    """
    # 1. Explicit hint wins
    if plugin_hint is not None:
        if plugin_hint in name_to_module:
            return name_to_module[plugin_hint]
        raise ValueError(
            f"Plugin hint '{plugin_hint}' for stage '{stage}' not found. "
            f"Available: {list(name_to_module.keys())}"
        )

    # 2. Collection match
    if collection in collection_to_module:
        return collection_to_module[collection]

    # 3. Wildcard fallback
    if wildcard_module is not None:
        return wildcard_module

    raise ValueError(
        f"No plugin found for stage '{stage}', collection '{collection}'. "
        f"Try providing a plugin_hint."
    )


# =============================================================================
# 1.  DRIVER — resolves plugins per-profile with plugin_hints
# =============================================================================

class AereoDriver:
    """Discovers all plugins once; resolves per-request via plugin_hints."""

    def __init__(self):
        self._search = _discover_plugins("aereo.search")
        self._download = _discover_plugins("aereo.download")
        self._read = _discover_plugins("aereo.read")
        self._reproject = _discover_plugins("aereo.reproject")
        self._write = _discover_plugins("aereo.write")

    def _get_stage_module(
        self,
        stage: str,
        collection: str,
        plugin_hint: str | None,
    ) -> Any:
        name_map, col_map, wildcard = getattr(self, f"_{stage}")
        return _resolve_plugin(
            stage, collection, plugin_hint, name_map, col_map, wildcard
        )

    def search(
        self,
        collection: str,
        aoi: BaseGeometry,
        start: str,
        end: str,
        plugin_hint: str | None = None,
    ) -> GeoDataFrame:
        from hamilton import driver

        mod = self._get_stage_module("search", collection, plugin_hint)
        dr = driver.Builder().with_modules(mod).build()
        results = dr.execute(
            ["search_results"],
            inputs={"aoi": aoi, "start_datetime": start, "end_datetime": end, "collection": collection},
        )
        return results["search_results"]

    def extract(
        self,
        assets: GeoDataFrame,
        grid_cells: Sequence[GridCell],
        collection: str,
        output_uri: str,
        plugin_hints: Mapping[str, str] | None = None,
    ) -> GeoDataFrame:
        from hamilton import driver

        hints = dict(plugin_hints or {})

        # Resolve each stage independently
        download_mod = self._get_stage_module("download", collection, hints.get("download"))
        read_mod = self._get_stage_module("read", collection, hints.get("read"))
        reproject_mod = self._get_stage_module("reproject", collection, hints.get("reproject"))
        write_mod = self._get_stage_module("write", collection, hints.get("write"))

        dr = (
            driver.Builder()
            .with_modules(download_mod, read_mod, reproject_mod, write_mod)
            .build()
        )

        results = dr.execute(
            ["artifacts_gdf"],
            inputs={
                "assets": assets,
                "grid_cells": grid_cells,
                "output_uri": output_uri,
                "collection": collection,
            },
        )
        return results["artifacts_gdf"]


# =============================================================================
# 2.  EXAMPLE PROFILE WITH PLUGIN_HINTS
# =============================================================================

# User can create multiple profiles, each with different plugin combinations:

PROFILE_SENTINEL3_EARTHACCESS = {
    "name": "s3_olci_earthaccess",
    "collection": "S3OLCI",
    "resolution": 300,
    "plugin_hints": {
        "search": "earthaccess",   # use NASA Earthdata search
        "read": "satpy",          # use satpy for reading
        "download": "generic",    # use generic HTTP downloader
        "reproject": "odc_geo",   # use odc-geo
        "write": "cog_eoids",     # use COG writer with EOIDS naming
    },
}

PROFILE_SENTINEL3_PLANETARY = {
    "name": "s3_olci_planetary",
    "collection": "S3OLCI",
    "resolution": 300,
    "plugin_hints": {
        "search": "planetary_computer",  # different search backend
        "read": "satpy",                # same reader
        "download": "planetary",         # PC-signed URL downloader
        "reproject": "odc_geo",
        "write": "cog_eoids",
    },
}

PROFILE_GOES16 = {
    "name": "goes16_abi",
    "collection": "GOES-16",
    "resolution": 2000,
    "plugin_hints": {
        "search": "aws_goes",      # AWS open data for GOES
        "read": "satpy",          # satpy also handles ABI
        "download": "generic",
        "reproject": "odc_geo",
        "write": "cog_eoids",
    },
}

# Profile with NO hints — relies entirely on auto-resolution by collection
PROFILE_NO_HINTS = {
    "name": "s3_auto",
    "collection": "S3OLCI",
    "resolution": 300,
    # plugin_hints omitted — driver will auto-resolve
}


# =============================================================================
# 3.  USAGE
# =============================================================================

def example_run_with_hints():
    from shapely.geometry import box

    drv = AereoDriver()
    aoi = box(-70, -40, -68, -39)

    # Profile 1: Earthaccess search + satpy read
    profile = PROFILE_SENTINEL3_EARTHACCESS
    assets = drv.search(
        collection=profile["collection"],
        aoi=aoi,
        start="2024-01-01",
        end="2024-01-02",
        plugin_hint=profile["plugin_hints"].get("search"),
    )
    artifacts = drv.extract(
        assets=assets,
        grid_cells=["cell_0", "cell_1"],
        collection=profile["collection"],
        output_uri="./output",
        plugin_hints=profile["plugin_hints"],
    )

    # Profile 2: No hints — auto-resolve
    profile2 = PROFILE_NO_HINTS
    assets2 = drv.search(
        collection=profile2["collection"],
        aoi=aoi,
        start="2024-01-01",
        end="2024-01-02",
        # plugin_hint omitted — auto-resolved
    )

    return artifacts


# =============================================================================
# 4.  PLUGIN MODULES (same as before, with entry point names)
# =============================================================================

# --- Search: earthaccess ---
supported_collections = ("*",)


def search_assets(
    aoi: BaseGeometry,
    start_datetime: str,
    end_datetime: str,
    collection: str,
) -> GeoDataFrame:
    import earthaccess

    auth = earthaccess.login(strategy="netrc")
    results = earthaccess.search_data(
        short_name=collection,
        bounding_box=tuple(aoi.bounds),
        temporal=(start_datetime, end_datetime),
    )
    records = [
        {
            "granule_id": g["meta"]["native-id"],
            "collection": collection,
            "geometry": g["umm"]["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0],
            "href": g["umm"]["RelatedUrls"][0]["URL"],
        }
        for g in results
    ]
    df = pd.DataFrame(records)
    return GeoDataFrame(gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326"))


# --- Search: planetary_computer ---
# Another plugin in a different repo
# Entry point: [project.entry-points."aereo.search"]
#              planetary_computer = "aereo_search_planetary.nodes"

# --- Read: satpy ---
supported_collections = ("*",)


def read_scenes(extracted_assets: dict[str, Path], collection: str) -> xr.Dataset:
    from satpy import Scene

    READER_MAP = {"S3OLCI": "olci_l1b", "GOES-16": "abi_l1b"}
    reader = READER_MAP.get(collection, collection)

    scenes = [Scene(filenames=[str(p)], reader=reader) for p in extracted_assets.values()]
    for scn in scenes:
        scn.load(["Oa01", "Oa02"])
    return scenes[0].to_xarray_dataset() if len(scenes) == 1 else xr.concat(
        [s.to_xarray_dataset() for s in scenes], dim="time"
    )


# --- Download: generic ---
supported_collections = ("*",)


def download_assets(assets: GeoDataFrame, download_dir: str = "/tmp/aereo") -> dict[str, Path]:
    import requests

    out_dir = Path(download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = {}
    for _, row in assets.iterrows():
        local = out_dir / f"{row['granule_id']}.zip"
        if not local.exists():
            r = requests.get(row["href"], stream=True)
            r.raise_for_status()
            with open(local, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        downloaded[row["granule_id"]] = local
    return downloaded


def unzip_assets(downloaded_assets: dict[str, Path]) -> dict[str, Path]:
    extracted = {}
    for gid, zip_path in downloaded_assets.items():
        extract_dir = zip_path.with_suffix("")
        if not extract_dir.exists():
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        extracted[gid] = extract_dir
    return extracted


# --- Reproject: odc_geo ---
supported_collections = ("*",)


def reproject_to_grid(read_scenes: xr.Dataset, grid_cells: Sequence[Any]) -> dict[str, xr.Dataset]:
    from odc.geo.xr import reproject as odc_reproject

    reprojected = {}
    for cell in grid_cells:
        geobox = cell.area_def(resolution=read_scenes.rio.resolution(), padding=0)
        reprojected[cell.id()] = odc_reproject(read_scenes, geobox, resampling="bilinear")
    return reprojected


# --- Write: cog_eoids ---
supported_collections = ("*",)


def write_cogs(
    reprojected_to_grid: dict[str, xr.Dataset],
    output_uri: str,
    collection: str,
) -> GeoDataFrame:
    import rioxarray  # noqa: F401
    from shapely.geometry import box

    records = []
    out_root = Path(output_uri)
    for cell_id, ds in reprojected_to_grid.items():
        for var in ds.data_vars:
            da = ds[var]
            out_dir = out_root / collection / cell_id
            out_dir.mkdir(parents=True, exist_ok=True)
            fpath = out_dir / f"{var}_{cell_id}.tif"
            da.rio.to_raster(fpath, driver="COG")
            records.append({
                "path": str(fpath),
                "variable": var,
                "cell_id": cell_id,
                "collection": collection,
                "geometry": box(*da.rio.bounds()),
            })
    df = pd.DataFrame(records)
    return GeoDataFrame(gpd.GeoDataFrame(df, geometry="geometry", crs=ds.rio.crs))


# =============================================================================
# 5.  ENTRY POINTS SUMMARY
# =============================================================================
#
# aereo-search-earthaccess/pyproject.toml:
#   [project.entry-points."aereo.search"]
#   earthaccess = "aereo_search_earthaccess.nodes"
#
# aereo-search-planetary/pyproject.toml:
#   [project.entry-points."aereo.search"]
#   planetary_computer = "aereo_search_planetary.nodes"
#
# aereo-read-satpy/pyproject.toml:
#   [project.entry-points."aereo.read"]
#   satpy = "aereo_read_satpy.nodes"
#
# aereo-core/pyproject.toml:
#   [project.entry-points."aereo.download"]
#   generic = "aereo_core.nodes"
#
#   [project.entry-points."aereo.reproject"]
#   odc_geo = "aereo_core.nodes"
#
#   [project.entry-points."aereo.write"]
#   cog_eoids = "aereo_core.nodes"
#
# =============================================================================
