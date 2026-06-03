"""Built-in reader plugins for the AEREO pipeline.

This module provides a default Reader implementation that uses ``odc.stac``
to lazily load pixel data from STAC items in native CRS as an AereoDataset.
"""

from __future__ import annotations

from typing import Any, Mapping

from aereo.interfaces import AereoDataset, ExtractionTask, PluginParam, Reader
from aereo.interfaces import infer_dataset_time_bounds

try:
    from odc.stac import load as odc_load
except ImportError:  # pragma: no cover
    odc_load = None  # type: ignore[assignment]


class ReadODCSTAC(Reader):
    """Built-in reader that uses ``odc.stac.load`` to fetch STAC asset data.

    Reconstructs :class:`pystac.Item` objects from the ``stac_item`` column
    that :class:`~aereo.builtins.search.SearchSTAC` stores in the assets
    GeoDataFrame, then delegates to ``odc.stac.load`` for lazy, dask-backed
    raster loading.

    The only Aereo-specific behaviour injected automatically:

    * **bbox** — derived from the union of ``task.grid_cells`` and intersected
      with ``task.aoi`` when present.  Injected into ``odc_params`` if the
      caller did not provide it explicitly.
    * **bands** — inferred from ``task.profile.collections`` when absent from
      ``odc_params``.  Pass ``odc_params={"bands": [...]}`` to override.
    * **time bounds** — ``ds.attrs["start_time"]``/``"end_time"`` are set via
      :func:`~aereo.interfaces.infer_dataset_time_bounds` so the writer can
      build EOIDS compliant paths.

    Every other ``odc.stac.load`` option (``groupby``, ``chunks``,
    ``resampling``, ``dtype``, ``stac_cfg``, ``patch_url``, …) is forwarded
    verbatim through ``odc_params``.

    Example::

        params = {
            "odc_params": {
                "bands": ["B04", "B08"],
                "groupby": "solar_day",
                "chunks": {"x": 2048, "y": 2048},
                "resampling": "bilinear",
            }
        }
    """

    supported_collections = ("*",)

    optional_params = (
        PluginParam(
            name="odc_params",
            type="dict",
            description=(
                "Parameters forwarded verbatim to ``odc.stac.load``. "
                "Accepts any keyword the function understands: ``bands``, "
                "``groupby``, ``chunks``, ``resampling``, ``dtype``, "
                "``stac_cfg``, ``patch_url``, … "
                "``bbox`` is auto-injected from the task's grid cells if absent."
            ),
            default=None,
            required=False,
        ),
    )

    def read(
        self,
        task: ExtractionTask,
        params: Mapping[str, Any],
    ) -> AereoDataset:
        """Load STAC assets for *task* using ``odc.stac.load``.

        Reconstructs :class:`pystac.Item` objects from the ``stac_item``
        column of ``task.assets``, constrains the load to the task's grid-cell
        bounding box, and returns a dataset tagged with temporal bounds in
        ``ds.attrs``.

        Args:
            task: Extraction task carrying assets, profile, grid cells, and AOI.
            params: Plugin parameters.  Recognised key: ``odc_params`` (dict).

        Returns:
            AereoDataset (potentially dask-backed) in the native CRS of the
            STAC items.

        Raises:
            ImportError: If ``odc-stac`` or ``pystac`` is not installed.
            ValueError: If no ``stac_item`` column is found in ``task.assets``
                or no valid STAC items can be reconstructed.
        """
        import pystac
        from shapely.ops import unary_union

        if odc_load is None:  # pragma: no cover
            raise ImportError(
                "odc-stac is required for ReadODCSTAC. "
                "Install it with: pip install 'aereo[stac]'"
            )

        assets_df = task.assets
        profile = task.profile

        # ------------------------------------------------------------------
        # 1. Reconstruct pystac.Item objects from the stac_item dict column.
        # ------------------------------------------------------------------
        if "stac_item" not in assets_df.columns:
            raise ValueError(
                "ReadODCSTAC requires a 'stac_item' column in task.assets. "
                "Ensure the search plugin (e.g. SearchSTAC) stores full STAC "
                "item dictionaries there."
            )

        # Deduplicate by STAC item ID — one pystac.Item per physical scene.
        seen_ids: set[str] = set()
        items: list[pystac.Item] = []
        for raw in assets_df["stac_item"]:
            if raw is None:
                continue
            item = pystac.Item.from_dict(raw)
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                items.append(item)

        if not items:
            raise ValueError("No valid STAC items found in task.assets['stac_item'].")

        # ------------------------------------------------------------------
        # 2. Build odc_params — start from the caller's dict, then inject
        #    Aereo-managed values only when absent.
        # ------------------------------------------------------------------
        odc_params: dict[str, Any] = dict(params.get("odc_params") or {})

        # Auto-inject bbox from grid cells if not provided.
        if "bbox" not in odc_params:
            cell_geoms = [
                cell.geom for cell in task.grid_cells if cell.geom is not None
            ]
            aoi = task.aoi

            if cell_geoms:
                spatial_extent = unary_union(cell_geoms)
                if aoi is not None:
                    spatial_extent = spatial_extent.intersection(aoi)
            elif aoi is not None:
                spatial_extent = aoi
            else:
                spatial_extent = None

            if spatial_extent is not None and not spatial_extent.is_empty:
                odc_params["bbox"] = spatial_extent.bounds  # (minx, miny, maxx, maxy)

        # Auto-infer bands from profile collections if not provided.
        if "bands" not in odc_params and profile.collections:
            odc_params["bands"] = [
                v for vars_list in profile.collections.values() for v in vars_list
            ]

        # ------------------------------------------------------------------
        # 3. Load via odc.stac.
        # ------------------------------------------------------------------
        ds: AereoDataset = odc_load(items, **odc_params)

        # ------------------------------------------------------------------
        # 4. Tag ds.attrs with temporal bounds so the writer can build paths.
        # ------------------------------------------------------------------
        infer_dataset_time_bounds(ds)

        return ds
