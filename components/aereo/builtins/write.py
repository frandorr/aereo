"""Built-in writer plugins for the AEREO pipeline.

This module provides writer plugins such as GeoTIFF/COG writers to output spatial
datasets to the filesystem or object storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from aereo.grid import GridCell
from aereo.interfaces import AereoDataset, ExtractionTask, PluginParam, Writer
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class WriteGeoTIFF(Writer):
    """Default writer that serialises each band as a GeoTIFF via ``rioxarray``.

    When ``cog=True`` is passed in *params*, outputs are translated to
    Cloud Optimized GeoTIFF (COG) with internal tiling and overviews.
    """

    supported_collections = ("*",)

    optional_params = (
        PluginParam(
            name="cog",
            type="bool",
            description="Enable Cloud Optimized GeoTIFF output.",
            default=False,
            required=False,
        ),
        PluginParam(
            name="blocksize",
            type="int",
            description="Tile width/height in pixels when cog=True.",
            default=512,
            required=False,
        ),
        PluginParam(
            name="overview_resampling",
            type="choice",
            description="Resampling method for COG overviews.",
            default="nearest",
            choices=["nearest", "bilinear", "cubic", "lanczos", "average", "mode"],
            required=False,
        ),
        PluginParam(
            name="overview_levels",
            type="list[str]",
            description="Explicit overview decimation levels. Auto-generated if omitted.",
            default=None,
            required=False,
        ),
    )

    def _write_cog(
        self,
        da: Any,
        fpath: Path,
        compress: str,
        zlevel: int,
        blocksize: int,
        overview_resampling: str,
        overview_levels: list[int] | None,
    ) -> None:
        """Write a DataArray to a Cloud Optimized GeoTIFF.

        Writes a tiled GeoTIFF with internal overviews to a temporary file,
        then moves it to the final destination.  This preserves the requested
        tile size, overviews, and metadata tags without relying on GDAL's
        COG driver (which can override block sizes and strip tags).

        Args:
            da: DataArray to write.
            fpath: Destination path.
            compress: Compression algorithm (e.g. ``"deflate"``).
            zlevel: Compression level.
            blocksize: Tile width/height in pixels.
            overview_resampling: Resampling method for overviews.
            overview_levels: Explicit decimation levels. Auto-generated if omitted.

        Returns:
            None
        """
        import shutil
        import tempfile

        import rasterio
        from rasterio.enums import Resampling

        suffix = fpath.suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name

        da.rio.to_raster(
            tmp_path,
            compress=compress,
            zlevel=zlevel,
            tiled=True,
            blockxsize=blocksize,
            blockysize=blocksize,
        )

        with rasterio.open(tmp_path, "r+") as src:
            if overview_levels is None:
                overview_levels = [
                    2**i for i in range(1, 8) if 2**i < min(src.height, src.width)
                ]
            if overview_levels:
                resamp = getattr(Resampling, overview_resampling, Resampling.nearest)
                src.build_overviews(overview_levels, resamp)
                src.update_tags(ns="rio_overview", resampling=overview_resampling)

        shutil.move(tmp_path, fpath)

    def _write_band(
        self,
        da: Any,
        fpath: Path,
        cog: bool,
        compress: str,
        zlevel: int,
        blocksize: int,
        overview_resampling: str,
        overview_levels: list[int] | None,
    ) -> None:
        """Write a single DataArray to disk, optionally as a COG.

        Args:
            da: DataArray to write.
            fpath: Destination path.
            cog: Whether to write as Cloud Optimized GeoTIFF.
            compress: Compression algorithm (e.g. ``"deflate"``).
            zlevel: Compression level.
            blocksize: Tile width/height in pixels when *cog* is True.
            overview_resampling: Resampling method for COG overviews.
            overview_levels: Explicit decimation levels. Auto-generated if omitted.

        Returns:
            None
        """
        if cog:
            self._write_cog(
                da,
                fpath,
                compress,
                zlevel,
                blocksize,
                overview_resampling,
                overview_levels,
            )
        else:
            da.rio.to_raster(
                fpath,
                compress=compress,
                zlevel=zlevel,
            )

    def write(
        self,
        ds: AereoDataset,
        task: ExtractionTask,
        cell: GridCell,
        params: Mapping[str, Any],
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* to GeoTIFF files using the standard EOIDS layout under ``task.uri``.

        Returns:
            GeoDataFrame of written artifacts.
        """
        import geopandas as gpd
        import pandas as pd
        import rioxarray  # noqa: F401
        from shapely.geometry import box
        from aereo.eoids import build_eoids_path

        uri = task.uri
        cell_id = cell.id()

        start_time = None
        end_time = None
        if "start_time" in task.assets.columns:
            try:
                non_null_starts = task.assets["start_time"].dropna()
                if not non_null_starts.empty:
                    start_time = pd.to_datetime(non_null_starts.min()).to_pydatetime()
            except Exception:
                pass
        if "end_time" in task.assets.columns:
            try:
                non_null_ends = task.assets["end_time"].dropna()
                if not non_null_ends.empty:
                    end_time = pd.to_datetime(non_null_ends.max()).to_pydatetime()
            except Exception:
                pass

        compress = params.get("compress", "deflate")
        zlevel = params.get("zlevel", 1)
        cog = params.get("cog", False)
        blocksize = params.get("blocksize", 512)
        overview_resampling = params.get("overview_resampling", "nearest")
        overview_levels = params.get("overview_levels")

        records = []
        for var_name in ds.data_vars:
            da = ds[var_name]
            if "band" in da.dims:
                # Multi-band variable — write each band separately
                for band_idx in range(da.sizes["band"]):
                    band_da = da.isel(band=band_idx)
                    fpath = build_eoids_path(
                        local_dir=uri,
                        profile=task.profile,
                        cell_id=cell_id,
                        start_time=start_time,
                        end_time=end_time,
                        desc=f"{var_name}_b{band_idx}",
                        suffix="tif",
                    )
                    self._write_band(
                        band_da,
                        fpath,
                        cog,
                        compress,
                        zlevel,
                        blocksize,
                        overview_resampling,
                        overview_levels,
                    )
                    records.append(
                        {
                            "path": str(fpath),
                            "variable": var_name,
                            "band": band_idx,
                            "cell_id": cell_id,
                            "geometry": box(*band_da.rio.bounds()),
                        }
                    )
            else:
                fpath = build_eoids_path(
                    local_dir=uri,
                    profile=task.profile,
                    cell_id=cell_id,
                    start_time=start_time,
                    end_time=end_time,
                    desc=str(var_name),
                    suffix="tif",
                )
                self._write_band(
                    da,
                    fpath,
                    cog,
                    compress,
                    zlevel,
                    blocksize,
                    overview_resampling,
                    overview_levels,
                )
                records.append(
                    {
                        "path": str(fpath),
                        "variable": var_name,
                        "band": None,
                        "cell_id": cell_id,
                        "geometry": box(*da.rio.bounds()),
                    }
                )

        if records:
            df = pd.DataFrame(records)
            gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=ds.rio.crs)
        else:
            gdf = gpd.GeoDataFrame(
                columns=["path", "variable", "band", "cell_id", "geometry"],
                geometry="geometry",
            )

        return GeoDataFrame[ArtifactSchema](gdf)
