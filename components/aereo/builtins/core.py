"""Built-in plugin implementations.

- ``ReprojectODC``: Default reprojector using ``odc-geo``.
- ``WriteGeoTIFF``: Default writer using ``rioxarray``.
- ``SelectBands``: Pre-reproject processor to keep only specified bands.
- ``QAMask``: Pre-reproject processor to mask cloudy/invalid pixels.
- ``NDVI``: Post-reproject processor to compute NDVI.
- ``Normalize``: Post-reproject processor for min-max or z-score normalisation.
- ``Composite``: Post-reproject processor for temporal compositing.
"""

from __future__ import annotations

from typing import Any, Mapping

from aereo.grid import GridCell
from aereo.interfaces import (
    AereoDataset,
    ExtractionTask,
    PluginParam,
    Processor,
    Reprojector,
    Writer,
)
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class ReprojectODC(Reprojector):
    """Default reprojector using ``odc-geo``.

    Expects *geobox* to be an ``odc.geo.geobox.GeoBox`` instance.
    """

    supported_collections = ("*",)

    def reproject(
        self,
        ds: AereoDataset,
        geobox: Any,
        params: Mapping[str, Any],
    ) -> AereoDataset:
        """Reproject *ds* to *geobox* using ``odc.geo.xr.reproject``."""
        from odc.geo.xr import reproject as odc_reproject  # type: ignore[reportAttributeAccessIssue]

        resampling = params.get("resampling", "nearest")
        return odc_reproject(ds, geobox, resampling=resampling)


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
        fpath: Any,
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

    def write(
        self,
        ds: AereoDataset,
        task: ExtractionTask,
        cell: GridCell,
        params: Mapping[str, Any],
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *ds* to GeoTIFF files under ``task.uri``.

        Returns:
            GeoDataFrame of written artifacts.
        """
        from pathlib import Path

        import geopandas as gpd
        import pandas as pd
        import rioxarray  # noqa: F401
        from shapely.geometry import box

        uri = task.uri
        cell_id = cell.id()
        out_dir = Path(uri) / task.profile.name / str(cell_id)
        out_dir.mkdir(parents=True, exist_ok=True)

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
                    fname = f"{var_name}_b{band_idx}_{cell_id}.tif"
                    fpath = out_dir / fname
                    if cog:
                        self._write_cog(
                            band_da,
                            fpath,
                            compress,
                            zlevel,
                            blocksize,
                            overview_resampling,
                            overview_levels,
                        )
                    else:
                        band_da.rio.to_raster(
                            fpath,
                            compress=compress,
                            zlevel=zlevel,
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
                fname = f"{var_name}_{cell_id}.tif"
                fpath = out_dir / fname
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


# ---------------------------------------------------------------------------
# Built-in Processors (Phase 2)
# ---------------------------------------------------------------------------


class SelectBands(Processor):
    """Pre-reproject processor that keeps only specified data variables.

    Dropping bands before reprojection reduces the data volume that the
    expensive reproject step must process.
    """

    supported_collections = ("*",)
    stage = "pre_reproject"

    def process(self, ds: AereoDataset, params: Mapping[str, Any]) -> AereoDataset:
        """Keep only the bands listed in *params["bands"]*.

        Args:
            ds: Input dataset.
            params: Must contain ``"bands"`` — a sequence of variable names to retain.

        Returns:
            A new dataset containing only the requested variables.

        Raises:
            ValueError: If ``params["bands"]`` is missing or empty.
        """
        bands = params.get("bands")
        if not bands:
            raise ValueError(
                "SelectBands requires params['bands'] to be a non-empty list of variable names."
            )

        keep = [str(b) for b in bands]
        missing = [b for b in keep if b not in ds.data_vars]
        if missing:
            raise ValueError(
                f"SelectBands: requested bands not found in dataset: {missing}"
            )

        return ds[keep]


class QAMask(Processor):
    """Pre-reproject processor that masks cloudy/invalid pixels using a QA band.

    Pixels where the QA band matches any of the specified bit-masks are set to
    NaN in all *other* data variables.  The QA band itself is dropped after
    masking.
    """

    supported_collections = ("*",)
    stage = "pre_reproject"

    def process(self, ds: AereoDataset, params: Mapping[str, Any]) -> AereoDataset:
        """Apply QA-based masking.

        Args:
            ds: Input dataset containing a QA variable.
            params: Must contain:
                - ``qa_band`` (str): Name of the QA variable in *ds*.
                - ``qa_mask_bits`` (Sequence[int]): Bit positions to mask.
                  A pixel is masked if ``(qa_value >> bit) & 1`` is 1 for *any*
                  listed bit.

        Returns:
            Dataset with masked pixels set to NaN.  The QA band is removed.

        Raises:
            ValueError: If required params are missing or the QA band does not exist.
        """
        import numpy as np

        qa_band = params.get("qa_band")
        qa_mask_bits = params.get("qa_mask_bits")

        if not qa_band or qa_mask_bits is None:
            raise ValueError(
                "QAMask requires params['qa_band'] and params['qa_mask_bits']."
            )

        if qa_band not in ds.data_vars:
            raise ValueError(
                f"QAMask: QA band '{qa_band}' not found in dataset. Available: {list(ds.data_vars)}"
            )

        qa = ds[qa_band]
        mask = np.zeros(qa.shape, dtype=bool)
        for bit in qa_mask_bits:
            mask |= ((qa.values >> bit) & 1).astype(bool)

        masked = ds.drop_vars(qa_band)
        for var in masked.data_vars:
            masked[var] = masked[var].where(~mask)

        return masked


class NDVI(Processor):
    """Post-reproject processor that computes the Normalised Difference Vegetation Index.

    NDVI is computed on co-registered pixels after reprojection so that the
    band math is physically correct.  The source red and NIR bands are dropped
    and only the ``ndvi`` variable is retained.
    """

    supported_collections = ("*",)
    stage = "post_reproject"

    def process(self, ds: AereoDataset, params: Mapping[str, Any]) -> AereoDataset:
        """Compute NDVI = (NIR - Red) / (NIR + Red).

        Args:
            ds: Input dataset containing red and NIR variables.
            params: Must contain:
                - ``ndvi_nir_band`` (str): Name of the NIR variable.
                - ``ndvi_red_band`` (str): Name of the red variable.

        Returns:
            Dataset with a single ``ndvi`` variable.  Source bands are removed.

        Raises:
            ValueError: If required params are missing or bands are not found.
        """
        nir_band = params.get("ndvi_nir_band")
        red_band = params.get("ndvi_red_band")

        if not nir_band or not red_band:
            raise ValueError(
                "NDVI requires params['ndvi_nir_band'] and params['ndvi_red_band']."
            )

        if nir_band not in ds.data_vars:
            raise ValueError(
                f"NDVI: NIR band '{nir_band}' not found. Available: {list(ds.data_vars)}"
            )
        if red_band not in ds.data_vars:
            raise ValueError(
                f"NDVI: red band '{red_band}' not found. Available: {list(ds.data_vars)}"
            )

        nir = ds[nir_band]
        red = ds[red_band]
        ndvi = (nir - red) / (nir + red)
        ndvi = ndvi.where((nir + red) != 0)

        result = ds.drop_vars([nir_band, red_band])
        result["ndvi"] = ndvi
        return result


class Normalize(Processor):
    """Post-reproject processor that normalises pixel values per band.

    Supports min-max scaling and z-score normalisation.  NaN pixels are ignored
    when computing statistics.
    """

    supported_collections = ("*",)
    stage = "post_reproject"

    def process(self, ds: AereoDataset, params: Mapping[str, Any]) -> AereoDataset:
        """Normalise each data variable.

        Args:
            ds: Input dataset.
            params: Must contain:
                - ``normalize_method`` (str): Either ``"minmax"`` or ``"zscore"``.

        Returns:
            Dataset with normalised variables.

        Raises:
            ValueError: If the method is unknown.
        """
        method = params.get("normalize_method", "minmax")

        if method not in ("minmax", "zscore"):
            raise ValueError(
                f"Normalize: unknown method '{method}'. Use 'minmax' or 'zscore'."
            )

        normalized = ds.copy()
        for var in normalized.data_vars:
            da = normalized[var]
            if method == "minmax":
                vmin = da.min(skipna=True)
                vmax = da.max(skipna=True)
                denom = vmax - vmin
                denom = denom.where(denom != 0, 1)
                normalized[var] = (da - vmin) / denom
            else:  # zscore
                mean = da.mean(skipna=True)
                std = da.std(skipna=True)
                std = std.where(std != 0, 1)
                normalized[var] = (da - mean) / std

        return normalized


class Composite(Processor):
    """Post-reproject processor that creates a temporal composite.

    Reduces the ``time`` dimension using a statistical method (median, mean, or
    max).  Useful for creating cloud-free or best-pixel composites.
    """

    supported_collections = ("*",)
    stage = "post_reproject"

    def process(self, ds: AereoDataset, params: Mapping[str, Any]) -> AereoDataset:
        """Reduce the ``time`` dimension to a single composite.

        Args:
            ds: Input dataset with a ``time`` dimension.
            params: Must contain:
                - ``composite_method`` (str): One of ``"median"``, ``"mean"``,
                  ``"max"``, ``"min"``.

        Returns:
            Dataset with the ``time`` dimension reduced to a single step.

        Raises:
            ValueError: If the method is unknown or ``time`` is missing.
        """
        method = params.get("composite_method", "median")

        if "time" not in ds.dims:
            raise ValueError("Composite requires a 'time' dimension in the dataset.")

        if method == "median":
            return ds.median(dim="time", keep_attrs=True)
        if method == "mean":
            return ds.mean(dim="time", keep_attrs=True)
        if method == "max":
            return ds.max(dim="time", keep_attrs=True)
        if method == "min":
            return ds.min(dim="time", keep_attrs=True)

        raise ValueError(
            f"Composite: unknown method '{method}'. Use 'median', 'mean', 'max', or 'min'."
        )
