"""Built-in writer plugins for the AEREO pipeline.

This module provides writer plugins such as GeoTIFF/COG writers to output spatial
datasets to the filesystem or object storage.
"""

from __future__ import annotations

from typing import Any, Mapping

from aereo.grid import GridCell
from aereo.interfaces import AereoDataset, ExtractionTask, PluginParam, Writer
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class WriteGeoTIFF(Writer):
    """Default writer that serialises each band as a GeoTIFF via ``rioxarray``.

    All rasterio/rioxarray write options (compression, tiling, COG overviews,
    nodata, etc.) are forwarded verbatim through the ``rio_params`` parameter.
    This keeps the writer unopinionated — the full rasterio profile API is
    available without any intermediate translation layer.

    Example — write a Cloud Optimized GeoTIFF with LZW compression::

        params = {
            "rio_params": {
                "compress": "lzw",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
        }
    """

    supported_collections = ("*",)

    optional_params = (
        PluginParam(
            name="rio_params",
            type="dict",
            description=(
                "Parameters forwarded verbatim to rioxarray ``to_raster``. "
                "Accepts any rasterio profile keyword (compress, zlevel, tiled, "
                "blockxsize, blockysize, nodata, driver, …)."
            ),
            default=None,
            required=False,
        ),
    )

    def write(
        self,
        ds: AereoDataset,
        task: ExtractionTask,
        cell: GridCell,
        params: Mapping[str, Any],
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* to GeoTIFF files using the standard EOIDS layout under ``task.uri``.

        Each (variable × band [× time-slice]) combination is written to its own
        file.  The ``rio_params`` entry in *params* is forwarded unchanged to
        ``da.rio.to_raster()``, giving callers full control over compression,
        tiling, COG conversion, nodata values, etc.

        Args:
            ds: The AereoDataset to write.  Must contain ``start_time`` and
                ``end_time`` in ``ds.attrs`` when no ``time`` dimension is present.
            task: The extraction task providing the output URI and profile.
            cell: The grid cell being written.
            params: Plugin parameters.  Recognised key: ``rio_params`` (dict).

        Returns:
            GeoDataFrame of written artifacts conforming to ``ArtifactSchema``.

        Raises:
            ValueError: If temporal metadata is missing and cannot be inferred.
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

        rio_params: dict[str, Any] = dict(params.get("rio_params") or {})

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

                    band_da.rio.to_raster(fpath, **rio_params)

                    # Keep band metadata as None for single-band variables
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
