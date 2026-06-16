"""Built-in writer plugins for the AEREO pipeline.

This module provides writer plugins such as GeoTIFF/COG writers to output spatial
datasets to the filesystem or object storage.
"""

from __future__ import annotations

from typing import Any

import xarray as xr
from aereo.grid import ExtractionPatch
from aereo.interfaces import ExtractionTask, Writer
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import Field


def _dataset_to_raster_bands(ds: xr.Dataset) -> xr.DataArray:
    """Combine all data variables in *ds* into a single multi-band DataArray.

    Each variable becomes one or more raster bands. Variables that already
    contain a ``band`` dimension with more than one band are expanded so that
    every original band becomes a separate raster band. The resulting
    DataArray has a ``band`` dimension whose coordinate values identify the
    source variable (and original band, when applicable).

    Args:
        ds: Dataset whose variables share the same spatial grid.

    Returns:
        A DataArray with ``band`` as the leading dimension, suitable for
        ``rio.to_raster()``.

    Raises:
        ValueError: If the dataset contains no data variables.
    """
    band_arrays: list[xr.DataArray] = []

    for var_name in ds.data_vars:
        da = ds[var_name]
        if "band" in da.dims and da.sizes["band"] != 1:
            # Multi-band variable: one raster band per original band.
            for band_val in da.coords["band"].values:
                band_da = da.sel(band=band_val).drop_vars("band", errors="ignore")
                band_da = band_da.expand_dims(band=[f"{var_name}_{band_val}"])
                band_arrays.append(band_da)
        else:
            # Single-band variable (or band dim of size 1).
            if "band" in da.dims:
                da = da.squeeze("band", drop=True)
            da = da.expand_dims(band=[str(var_name)])
            band_arrays.append(da)

    if not band_arrays:
        raise ValueError("Dataset contains no data variables to write.")

    combined = xr.concat(band_arrays, dim="band")
    combined = combined.transpose("band", ...)
    # Ensure each raster band gets a distinct description. rioxarray writes
    # band descriptions from the ``long_name`` attribute; when it is a list or
    # tuple with one entry per band, each band is labelled correctly. Without
    # this, the first variable's ``long_name`` is applied to every band.
    combined.attrs["long_name"] = list(combined.coords["band"].values)
    return combined


class WriteGeoTIFF(Writer):
    """Default writer that serialises a cell's variables as one GeoTIFF via ``rioxarray``.

    All ``data_vars`` for a single cell are written to **one file** as separate
    raster bands, following the EOIDS convention of one artifact file per grid
    cell. When a variable itself contains multiple bands they are stored as
    additional raster bands inside the same file — the ``variable`` EOIDS key
    lists the full set of bands (joined by ``+``).

    All rasterio/rioxarray write options (compression, tiling, COG overviews,
    nodata, etc.) are forwarded verbatim through the ``rio_params`` parameter.
    This keeps the writer unopinionated — the full rasterio profile API is
    available without any intermediate translation layer.

    If the parent :class:`~aereo.pipeline.ExtractionJob` declares a
    ``derivative`` name, outputs are placed under a
    ``derivatives/<name>/`` subdirectory of ``output_uri``.
    """

    rio_params: dict[str, Any] = Field(default_factory=dict)

    def __call__(
        self,
        ds: xr.Dataset,
        task: ExtractionTask,
        patch: ExtractionPatch,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* to a GeoTIFF using the standard EOIDS layout under ``task.output_uri``.

        All variables are combined into a single multi-band raster per grid cell.
        If the dataset has a ``time`` dimension, one file is written per time
        slice. The ``rio_params`` entry is forwarded unchanged to
        ``da.rio.to_raster()``, giving callers full control over compression,
        tiling, COG conversion, nodata values, etc.

        Args:
            ds: The xarray.Dataset to write.  Must contain ``start_time`` and
                ``end_time`` in ``ds.attrs`` when no ``time`` dimension is present.
            task: The extraction task providing the output URI.
            patch: The extraction patch being written.

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

        uri = task.output_uri
        cell_id = patch.id

        start_time = ds.attrs.get("start_time")
        end_time = ds.attrs.get("end_time")

        if "time" not in ds.dims and (start_time is None or end_time is None):
            raise ValueError(
                "xarray.Dataset must contain 'start_time' and 'end_time' in ds.attrs "
                "when no 'time' dimension is present to construct EOIDS compliant paths."
            )

        rio_params = dict(self.rio_params)

        # Build patch metadata once
        grid_cell_id = patch.id
        grid_dist = patch.d
        resolution = patch.resolution
        cell_geometry = patch.cell_geometry
        cell_utm_crs = patch.utm_crs
        cell_utm_footprint = patch.utm_footprint

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

        job_name = task.job.name
        derivative = task.derivative

        # Handle optional time dimension: if present, slice over it.
        has_time = "time" in ds.dims
        time_coords = ds.coords["time"].values if has_time else [None]

        records = []
        for time_idx, time_val in enumerate(time_coords):
            ds_slice = ds.isel(time=time_idx) if has_time else ds

            # Resolve timestamp for this specific slice
            slice_time = (
                pd.to_datetime(time_val).to_pydatetime()
                if time_val is not None
                else start_time
            )

            combined_da = _dataset_to_raster_bands(ds_slice)

            fpath = build_eoids_path(
                local_dir=uri,
                job_name=job_name,
                resolution=resolution,
                collections=collections,
                variables=[str(v) for v in ds.data_vars],
                cell_id=cell_id,
                start_time=slice_time,
                end_time=slice_time if has_time else end_time,
                derivative=derivative,
                suffix="tif",
            )

            combined_da.rio.to_raster(fpath, **rio_params)

            # Unique artifact ID
            time_str = slice_time.strftime("%Y%m%dT%H%M%S") if slice_time else ""
            var_names = "+".join(str(v) for v in ds.data_vars)
            artifact_id = f"{grid_cell_id}_{var_names}_{time_str}"

            records.append(
                {
                    "id": artifact_id,
                    "source_ids": source_ids,
                    "start_time": slice_time,
                    "end_time": slice_time if has_time else end_time,
                    "uri": str(fpath),
                    "collection": collection,
                    "geometry": box(*combined_da.rio.bounds()),
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
