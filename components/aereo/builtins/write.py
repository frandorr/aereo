"""Built-in writer plugins for the AEREO pipeline.

This module provides writer plugins such as GeoTIFF/COG writers to output spatial
datasets to the filesystem or object storage.
"""

from __future__ import annotations

from typing import Any

from aereo.grid import GridCell
from aereo.interfaces import AereoDataset, ExtractionTask, Writer
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import Field


class WriteGeoTIFF(Writer):
    """Default writer that serialises each band as a GeoTIFF via ``rioxarray``.

    All rasterio/rioxarray write options (compression, tiling, COG overviews,
    nodata, etc.) are forwarded verbatim through the ``rio_params`` parameter.
    This keeps the writer unopinionated — the full rasterio profile API is
    available without any intermediate translation layer.
    """

    profile_name: str = "default"
    rio_params: dict[str, Any] = Field(default_factory=dict)

    def __call__(
        self,
        ds: AereoDataset,
        task: ExtractionTask,
        cell: GridCell,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* to GeoTIFF files using the standard EOIDS layout under ``task.uri``.

        Each (variable × band [× time-slice]) combination is written to its own
        file.  The ``rio_params`` entry in *params* is forwarded unchanged to
        ``da.rio.to_raster()``, giving callers full control over compression,
        tiling, COG conversion, nodata values, etc.

        Args:
            ds: The AereoDataset to write.  Must contain ``start_time`` and
                ``end_time`` in ``ds.attrs`` when no ``time`` dimension is present.
            task: The extraction task providing the output URI.
            cell: The grid cell being written.

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

        rio_params = dict(self.rio_params)

        # Build grid-cell metadata once
        grid_cell_id = cell.id()
        grid_dist = task.grid_config.target_grid_dist or cell.D
        cell_geometry = cell.geom
        cell_utm_crs = cell.utm_crs
        cell_utm_footprint = cell.utm_footprint

        # Derive source IDs from task assets
        source_ids = (
            ",".join(sorted({str(aid) for aid in task.assets["id"] if pd.notna(aid)}))
            if "id" in task.assets.columns
            else ""
        )

        # Determine collection
        collections = (
            list(task.assets["collection"].unique())
            if "collection" in task.assets.columns
            else []
        )
        collection = collections[0] if collections else None

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

                # Handle optional band dimension
                has_band = "band" in t_da.dims
                num_bands = t_da.sizes["band"] if has_band else 1
                for band_idx in range(num_bands):
                    band_da = t_da.isel(band=band_idx) if has_band else t_da

                    # Single band gets the variable name, multi-band gets B04_b0
                    desc = f"{var_name}_b{band_idx}" if num_bands > 1 else str(var_name)

                    fpath = build_eoids_path(
                        local_dir=uri,
                        profile_name=self.profile_name,
                        resolution=grid_dist,
                        collections=collections,
                        variables=[str(v) for v in ds.data_vars],
                        cell_id=cell_id,
                        start_time=slice_time,
                        end_time=slice_time if has_time else end_time,
                        desc=desc,
                        suffix="tif",
                    )

                    band_da.rio.to_raster(fpath, **rio_params)

                    # Unique artifact ID
                    artifact_id = (
                        f"{grid_cell_id}_{var_name}_{band_idx if num_bands > 1 else 0}"
                    )

                    records.append(
                        {
                            "id": artifact_id,
                            "source_ids": source_ids,
                            "start_time": slice_time,
                            "end_time": slice_time if has_time else end_time,
                            "uri": str(fpath),
                            "collection": collection,
                            "geometry": box(*band_da.rio.bounds()),
                            "grid_cell": grid_cell_id,
                            "grid_dist": grid_dist,
                            "cell_geometry": cell_geometry,
                            "cell_utm_crs": cell_utm_crs,
                            "cell_utm_footprint": cell_utm_footprint,
                        }
                    )

        if records:
            df = pd.DataFrame(records)
            gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=ds.rio.crs)
        else:
            gdf = gpd.GeoDataFrame(
                columns=[
                    "id",
                    "source_ids",
                    "start_time",
                    "end_time",
                    "uri",
                    "collection",
                    "geometry",
                    "grid_cell",
                    "grid_dist",
                    "cell_geometry",
                    "cell_utm_crs",
                    "cell_utm_footprint",
                ],
                geometry="geometry",
            )

        return GeoDataFrame[ArtifactSchema](gdf)
