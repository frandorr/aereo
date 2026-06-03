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

        start_time = ds.attrs.get("start_time")
        end_time = ds.attrs.get("end_time")

        if "time" not in ds.dims and (start_time is None or end_time is None):
            raise ValueError(
                "AereoDataset must contain 'start_time' and 'end_time' in ds.attrs "
                "when no 'time' dimension is present to construct EOIDS compliant paths."
            )

        compress = params.get("compress", "deflate")
        zlevel = params.get("zlevel", 1)
        cog = params.get("cog", False)
        blocksize = params.get("blocksize", 512)
        overview_resampling = params.get("overview_resampling", "nearest")
        overview_levels = params.get("overview_levels")

        records = []
        for var_name in ds.data_vars:
            da = ds[var_name]

            # Handle optional time dimension: if present, slice over it.
            has_time = "time" in da.dims
            time_coords = da.coords["time"].values if has_time else [None]

            for time_idx, time_val in enumerate(time_coords):
                t_da = da.isel(time=time_idx) if has_time else da

                # Resolve timestamp for this specific slice
                slice_time = (
                    pd.to_datetime(time_val).to_pydatetime()
                    if time_val is not None
                    else start_time
                )

                # Since band is strictly guaranteed to be present:
                num_bands = t_da.sizes["band"]
                for band_idx in range(num_bands):
                    band_da = t_da.isel(band=band_idx)

                    # Single band gets the variable name, multi-band gets B04_b0
                    desc = f"{var_name}_b{band_idx}" if num_bands > 1 else str(var_name)

                    fpath = build_eoids_path(
                        local_dir=uri,
                        profile=task.profile,
                        cell_id=cell_id,
                        start_time=slice_time,
                        end_time=slice_time if has_time else end_time,
                        desc=desc,
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

                    # Keep band metadata as None for single-band variables to match original behaviour
                    band_val = band_idx if num_bands > 1 else None

                    records.append(
                        {
                            "path": str(fpath),
                            "variable": var_name,
                            "band": band_val,
                            "cell_id": cell_id,
                            "geometry": box(*band_da.rio.bounds()),
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
