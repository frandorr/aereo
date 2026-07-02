"""Visualization utilities for plotting AOIs and geospatial data with cartopy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, cast

from structlog import get_logger

if TYPE_CHECKING:
    import geopandas as gpd
    import numpy as np
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

logger = get_logger()

_BASE_ZORDER = 0
_OVERLAY_ZORDER = 1
_WATER_COLOR = "#d6eaf8"
_WATER_EDGE_COLOR = "#5dade2"
_LAND_COLOR = "#f5f5f0"
_DEFAULT_LINEWIDTH = 0.4

_ASSET_EDGE_COLOR = "blue"
_AOI_EDGE_COLOR = "red"
_PERCENTILE_LOW = 2.0
_PERCENTILE_HIGH = 98.0
_ZSCORE_STD_MULTIPLIER = 2.0
_ZSCORE_PLOT_LO = -2.0
_ZSCORE_PLOT_HI = 2.0
_FOOTPRINT_VIEW_BUFFER_M = 1000.0


def _add_base_layer(ax, tiles: bool, zoom: int) -> None:
    """Add base map layer to the axes.

    Args:
        ax: Matplotlib axes with a cartopy projection.
        tiles: Whether to fetch OpenStreetMap raster tiles.
        zoom: OSM tile zoom level when ``tiles=True``.
    """
    import cartopy.feature as cfeature

    if tiles:
        from cartopy.io.img_tiles import OSM

        osm = OSM()
        ax.add_image(osm, zoom)
    else:
        ax.add_feature(cfeature.LAND, facecolor=_LAND_COLOR, zorder=_BASE_ZORDER)
        ax.add_feature(cfeature.OCEAN, facecolor=_WATER_COLOR, zorder=_BASE_ZORDER)
        ax.add_feature(cfeature.COASTLINE, linewidth=0.6, zorder=_OVERLAY_ZORDER)
        ax.add_feature(
            cfeature.BORDERS, linewidth=_DEFAULT_LINEWIDTH, zorder=_OVERLAY_ZORDER
        )
        ax.add_feature(
            cfeature.LAKES,
            facecolor=_WATER_COLOR,
            edgecolor=_WATER_EDGE_COLOR,
            linewidth=_DEFAULT_LINEWIDTH,
            zorder=_OVERLAY_ZORDER,
        )
        ax.add_feature(
            cfeature.RIVERS,
            edgecolor=_WATER_EDGE_COLOR,
            linewidth=_DEFAULT_LINEWIDTH,
            zorder=_OVERLAY_ZORDER,
        )


def _set_extent_with_buffer(ax, bounds: list[float], buffer: float) -> None:
    """Set axes extent from bounds ``[minx, miny, maxx, maxy]`` plus a buffer.

    Args:
        ax: Matplotlib axes with a cartopy projection.
        bounds: Total-bounds array ``[minx, miny, maxx, maxy]``.
        buffer: Padding in CRS units added to each side.
    """
    import cartopy.crs as ccrs

    ax.set_extent(  # type: ignore[reportAttributeAccessIssue]
        [
            bounds[0] - buffer,
            bounds[2] + buffer,
            bounds[1] - buffer,
            bounds[3] + buffer,
        ],
        crs=ccrs.PlateCarree(),
    )


def _build_legend_patches(
    assets: gpd.GeoDataFrame | None,
    asset_label: str,
    label: str,
) -> list:
    """Build legend patches for asset footprints and AOI.

    Args:
        assets: Optional GeoDataFrame of asset footprints.
        asset_label: Legend label for the asset footprints.
        label: Legend label for the AOI outline.

    Returns:
        List of matplotlib Patch objects for the legend.
    """
    import matplotlib.patches as mpatches

    handles: list = []
    if assets is not None and not assets.empty:
        asset_patch = mpatches.Patch(
            facecolor="none",
            edgecolor=_ASSET_EDGE_COLOR,
            linewidth=1.5,
            label=asset_label,
        )
        handles.append(asset_patch)

    aoi_patch = mpatches.Patch(
        facecolor="none", edgecolor=_AOI_EDGE_COLOR, linewidth=2.5, label=label
    )
    handles.append(aoi_patch)
    return handles


def _plot_temporal_heatmap(
    ax_temporal: Axes,
    search_results: gpd.GeoDataFrame,
    group_by: str,
    temporal_bins: str,
) -> None:
    """Render the acquisition-density heatmap on *ax_temporal*.

    Falls back to a centred "No temporal data" message when the input is
    missing required columns or contains no rows.

    Args:
        ax_temporal: Matplotlib axes for the right-hand panel.
        search_results: GeoDataFrame of search assets.
        group_by: Column name to group time bins by.
        temporal_bins: Pandas frequency string (e.g. ``"1D"``).
    """
    import matplotlib.pyplot as plt
    import pandas as pd

    has_time = (
        "start_time" in search_results.columns
        and group_by in search_results.columns
        and not search_results.empty
    )
    if not has_time:
        _show_no_temporal_text(ax_temporal)
        return

    df = search_results.copy()
    df["time_bin"] = pd.to_datetime(df["start_time"]).dt.floor(temporal_bins)
    heatmap_data = df.groupby([group_by, "time_bin"]).size().unstack(fill_value=0)

    if heatmap_data.empty:
        _show_no_temporal_text(ax_temporal)
        return

    im = ax_temporal.imshow(
        heatmap_data.to_numpy(),
        aspect="auto",
        cmap="YlOrRd",
    )
    ax_temporal.set_xticks(range(len(heatmap_data.columns)))
    ax_temporal.set_xticklabels(
        [str(c) for c in heatmap_data.columns], rotation=45, ha="right"
    )
    ax_temporal.set_yticks(range(len(heatmap_data.index)))
    ax_temporal.set_yticklabels([str(i) for i in heatmap_data.index])
    ax_temporal.set_title("Acquisition Density")
    ax_temporal.set_xlabel("Time bin")
    ax_temporal.set_ylabel(group_by)
    plt.colorbar(im, ax=ax_temporal, label="Asset count")


def _show_no_temporal_text(ax: Axes) -> None:
    """Draw a centred "No temporal data" message and set the panel title.

    Args:
        ax: Matplotlib axes to annotate.
    """
    ax.text(
        0.5,
        0.5,
        "No temporal data",
        ha="center",
        va="center",
        transform=ax.transAxes,
    )
    ax.set_title("Acquisition Density")


def plot_aoi(
    gdf: gpd.GeoDataFrame,
    label: str = "AOI",
    buffer: float = 0.02,
    width: float = 8,
    height: float = 6,
    assets: gpd.GeoDataFrame | None = None,
    asset_label: str = "Assets",
    tiles: bool = False,
    zoom: int = 12,
) -> None:
    """Plot a GeoDataFrame on a map.

    By default uses local Natural Earth vector features (no HTTP calls).
    Set ``tiles=True`` to use OpenStreetMap raster tiles.

    Dependencies (cartopy, matplotlib) are imported lazily so users
    only need them installed when this function is actually called.

    Args:
        gdf: GeoDataFrame containing the geometry to plot.
        label: Legend label for the AOI outline.
        buffer: Degrees of padding around the geometry bounds.
        width: Figure width in inches.
        height: Figure height in inches.
        assets: Optional GeoDataFrame of asset footprints to overlay.
        asset_label: Legend label for the asset footprints.
        tiles: Whether to fetch OpenStreetMap raster tiles. Default is
            ``False`` to avoid HTTP 429 rate-limit errors.
        zoom: OSM tile zoom level when ``tiles=True``.

    Side Effects:
        Displays the plot via ``plt.show()``.
    """
    import cartopy.crs as ccrs
    import matplotlib.pyplot as plt

    _, ax = plt.subplots(
        figsize=(width, height), subplot_kw={"projection": ccrs.PlateCarree()}
    )

    _add_base_layer(ax, tiles, zoom)

    # Plot asset footprints (under AOI so AOI is visible on top)
    if assets is not None and not assets.empty:
        assets.plot(
            ax=ax,
            facecolor="none",
            edgecolor=_ASSET_EDGE_COLOR,
            linewidth=1.5,
        )

    # Plot AOI
    gdf.plot(
        ax=ax,
        facecolor="none",
        edgecolor=_AOI_EDGE_COLOR,
        linewidth=2.5,
    )

    handles = _build_legend_patches(assets, asset_label, label)

    # Set extent with a small buffer around the AOI
    _set_extent_with_buffer(ax, list(gdf.total_bounds), buffer)

    ax.gridlines(  # type: ignore[reportAttributeAccessIssue]
        draw_labels=True, linestyle="--", alpha=0.5
    )
    ax.legend(handles=handles, loc="upper left")
    ax.set_title("Selected Area of Interest")

    plt.show()


def plot_coverage(
    search_results: gpd.GeoDataFrame,
    aoi: gpd.GeoDataFrame | None = None,
    *,
    group_by: str = "collection",
    temporal_bins: str = "1D",
    width: float = 14,
    height: float = 6,
) -> Figure:
    """Visualise spatial-temporal coverage of search results.

    Produces a two-panel figure:

    1. **Map** — semi-transparent asset footprints coloured by *group_by* column
       (default ``collection``), with the AOI outlined in red.
    2. **Temporal heatmap** — acquisition density per (*group_by*, time-bin).

    All heavy dependencies (matplotlib, cartopy, seaborn) are imported lazily
    so callers only pay the import cost when this function is actually used.

    Args:
        search_results: GeoDataFrame of search assets (must contain a
            ``geometry`` column and the column named by *group_by*).
        aoi: Optional GeoDataFrame with the AOI boundary. If provided, the
            map extent is centred on the AOI and uncovered regions are
            highlighted.
        group_by: Column name to group footprints and temporal bins by.
            Default is ``"collection"``.
        temporal_bins: Pandas frequency string for temporal binning
            (e.g. ``"1D"``, ``"1H"``). Default is ``"1D"``.
        width: Figure width in inches.
        height: Figure height in inches.

    Returns:
        A :class:`matplotlib.figure.Figure` with two subplots.
    """
    import cartopy.crs as ccrs
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(width, height))
    gs = fig.add_gridspec(1, 2, width_ratios=[2, 1])
    ax_map = fig.add_subplot(gs[0, 0], projection=ccrs.PlateCarree())
    ax_temporal = fig.add_subplot(gs[0, 1])

    # ------------------------------------------------------------------
    # 1. Map panel
    # ------------------------------------------------------------------
    _add_base_layer(ax_map, tiles=False, zoom=12)

    # Plot asset footprints coloured by group_by
    if group_by in search_results.columns and not search_results.empty:
        cmap = plt.get_cmap("tab10")
        for idx, (group, subset) in enumerate(search_results.groupby(group_by)):
            color = cmap(idx % 10)
            subset.plot(
                ax=ax_map,
                facecolor=color,
                edgecolor="none",
                alpha=0.4,
                label=str(group),
                transform=ccrs.PlateCarree(),
            )

    # Plot AOI outline
    if aoi is not None and not aoi.empty:
        aoi.plot(
            ax=ax_map,
            facecolor="none",
            edgecolor=_AOI_EDGE_COLOR,
            linewidth=2.0,
            label="AOI",
            transform=ccrs.PlateCarree(),
        )
        _set_extent_with_buffer(ax_map, list(aoi.total_bounds), buffer=0.02)
    elif not search_results.empty:
        _set_extent_with_buffer(ax_map, list(search_results.total_bounds), buffer=0.02)

    ax_map.gridlines(  # type: ignore[reportAttributeAccessIssue]
        draw_labels=True, linestyle="--", alpha=0.5
    )
    ax_map.set_title("Spatial Coverage")
    ax_map.legend(loc="upper left")

    # ------------------------------------------------------------------
    # 2. Temporal heatmap panel
    # ------------------------------------------------------------------
    _plot_temporal_heatmap(
        ax_temporal=ax_temporal,
        search_results=search_results,
        group_by=group_by,
        temporal_bins=temporal_bins,
    )

    plt.tight_layout()
    return fig


def _normalize_bands(bands: int | Sequence[int] | None) -> tuple[int, ...]:
    """Normalize the ``bands`` argument into a 1-based band index tuple.

    Args:
        bands: Single band index, sequence of band indices, or ``None``.

    Returns:
        Tuple of 1-based band indices.
    """
    if bands is None:
        return (1,)
    if isinstance(bands, int):
        return (bands,)
    return tuple(int(b) for b in bands)


def _compute_stretch_params(values: np.ndarray) -> tuple[float, float, float, float]:
    """Return (lo, hi, mean, std) for a flattened array of valid values.

    Args:
        values: Flattened array of valid pixel values.

    Returns:
        ``(lo, hi, mean, std)`` where ``lo`` and ``hi`` are the 2nd and 98th
        percentiles.
    """
    import numpy as np

    if values.size == 0:
        return np.nan, np.nan, np.nan, np.nan
    lo, hi = np.percentile(values, [_PERCENTILE_LOW, _PERCENTILE_HIGH])
    return float(lo), float(hi), float(np.mean(values)), float(np.std(values))


def plot_artifact_patches(
    artifacts: gpd.GeoDataFrame,
    *,
    cmap: str = "gray",
    bands: int | Sequence[int] | None = None,
    stretch: Literal["minmax", "percentile", "zscore"] = "minmax",
    ds_factor: int = 10,
    footprint_edgecolor: str = _AOI_EDGE_COLOR,
    footprint_linewidth: float = 2.0,
    annotate_cells: bool = True,
    annotation_color: str = "cyan",
    fig_width: float = 20.0,
    title: str = "Extracted Patches Spatial Overview",
    vmin: float | None = None,
    vmax: float | None = None,
    colorbar: bool = True,
    colorbar_label: str | None = None,
    nodata: float | None = None,
) -> tuple[Figure, Axes]:
    """Plot extracted raster patches and their grid-cell footprints on one canvas.

    This is useful for quickly inspecting the spatial layout of artifacts
    produced by the extraction pipeline. By default each patch's first band
    is plotted at a downsampled resolution, the UTM footprint is overlaid as
    a dashed polygon, and the grid cell ID is annotated at the footprint
    centre.

    Pass ``bands`` as a sequence of band indices (1-based) to render multiple
    bands together as an RGB/RGBA image. When more than one band is requested,
    ``cmap`` and ``colorbar`` are ignored. ``vmin``/``vmax`` are only used by
    the single-band ``zscore`` stretch.

    All normalization is computed across the **whole AOI** (all patches) so
    adjacent patches share the same color scale. Choose ``stretch`` to control
    how that normalization is performed:

    * ``"minmax"`` (default): linear stretch from the global minimum to the
      global maximum.
    * ``"percentile"``: linear stretch between the global 2nd and 98th
      percentiles; outliers are clipped.
    * ``"zscore"``: subtract the global mean and divide by the global standard
      deviation. For single-band plots the values are kept as z-scores and
      displayed with ``vmin=-2``, ``vmax=2`` by default. For multi-band plots
      the z-scores are clipped to ``[-2, 2]`` and mapped to ``[0, 1]``.

    Pass ``vmin``/``vmax`` to fix the range for variables such as NDVI, or to
    override the z-score bounds when using ``stretch="zscore"``.

    Heavy dependencies (matplotlib, geopandas, rasterio) are imported lazily
    so callers only pay the import cost when this function is actually used.

    Args:
        artifacts: GeoDataFrame of extracted artifacts. Must contain the
            columns ``uri``, ``cell_utm_footprint``, and ``grid_cell``.
        cmap: Colormap passed to ``imshow`` for single-band raster data.
        bands: Band index or list of band indices to plot (1-based). Use a
            sequence of 3 bands (e.g. ``[1, 2, 3]``) for an RGB composite.
        stretch: Normalization strategy applied across the whole AOI.
        ds_factor: Downsample factor applied to each patch before plotting.
            Larger values produce a lighter, faster render.
        footprint_edgecolor: Colour of the dashed footprint outline.
        footprint_linewidth: Width of the dashed footprint outline.
        annotate_cells: Whether to draw the grid cell ID at each footprint's
            centre.
        annotation_color: Colour of the grid-cell ID text.
        fig_width: Width of the figure in inches. The height is derived from
            the data's aspect ratio.
        title: Title shown above the map.
        vmin: Fixed lower bound for the colormap. Only used for single-band
            plots. For ``stretch="zscore"`` it defaults to ``-2``.
        vmax: Fixed upper bound for the colormap. Only used for single-band
            plots. For ``stretch="zscore"`` it defaults to ``2``.
        colorbar: Whether to draw a colorbar for the raster data. Only used
            for single-band plots.
        colorbar_label: Optional label for the colorbar.
        nodata: Nodata value to mask as transparent. If ``None``, the nodata
            value read from each raster is used. Invalid floating-point values
            are always masked.

    Returns:
        A tuple of ``(figure, axes)``.

    Raises:
        ValueError: If ``artifacts`` is empty or missing a required column.
    """
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    import rasterio
    from shapely.geometry.base import BaseGeometry

    required_cols = {"uri", "cell_utm_footprint", "grid_cell"}
    missing = required_cols - set(artifacts.columns)
    if missing:
        raise ValueError(f"artifacts is missing required columns: {sorted(missing)}")
    if artifacts.empty:
        raise ValueError("artifacts GeoDataFrame is empty")

    band_list = _normalize_bands(bands)
    n_bands = len(band_list)
    is_rgb = n_bands > 1

    minx, miny, maxx, maxy = artifacts["cell_utm_footprint"].total_bounds
    width = maxx - minx
    height = maxy - miny
    aspect_ratio = width / height if height > 0 else 1.0
    fig_height = max(fig_width / aspect_ratio, 2.0)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    # First pass: load every patch (downsampled) and collect all valid pixel
    # values per band so normalization is computed across the whole AOI.
    # Nodata and NaN/Inf are converted to NaN so gaps/overlaps stay transparent.
    band_values: list[list[np.ndarray]] = [[] for _ in range(n_bands)]

    import rasterio.errors

    # Load each distinct URI once.  The MajorTOM artifact index may contain
    # multiple rows that point at the same file (e.g. raw read -> write with
    # no reprojection), so caching the loaded patch avoids redundant I/O and
    # keeps normalization from double-counting identical rasters.
    uri_to_patch: dict[str, tuple[np.ndarray, Any] | None] = {}

    for uri in artifacts["uri"].unique():
        try:
            with rasterio.open(uri) as src:
                out_shape = (int(src.height / ds_factor), int(src.width / ds_factor))
                bounds = src.bounds
                src_nodata = src.nodata
                mask_value = nodata if nodata is not None else src_nodata

                if is_rgb:
                    data = src.read(band_list, out_shape=out_shape).astype(np.float32)
                else:
                    data = src.read(band_list[0], out_shape=out_shape).astype(
                        np.float32
                    )
                    data = data[None, :, :]

                data = np.where(np.isfinite(data), data, np.nan)
                if mask_value is not None:
                    data = np.where(data == mask_value, np.nan, data)

                for b in range(n_bands):
                    band_data = data[b]
                    valid = band_data[np.isfinite(band_data)]
                    if valid.size:
                        band_values[b].append(valid.ravel())

                uri_to_patch[uri] = (data, bounds)
        except (rasterio.errors.RasterioError, OSError) as exc:
            logger.warning("patch_read_failed", uri=uri, error=str(exc))
            uri_to_patch[uri] = None

    band_params = [
        _compute_stretch_params(np.concatenate(v) if v else np.array([]))
        for v in band_values
    ]

    if is_rgb:
        band_lo: list[float] = []
        band_hi: list[float] = []
        for b in range(n_bands):
            lo, hi, mean, std = band_params[b]
            values = np.concatenate(band_values[b]) if band_values[b] else np.array([])
            if stretch == "minmax" and values.size:
                lo = float(values.min())
                hi = float(values.max())
            elif stretch == "zscore":
                lo = (
                    mean - _ZSCORE_STD_MULTIPLIER * std
                    if np.isfinite(std) and std > 0
                    else np.nan
                )
                hi = (
                    mean + _ZSCORE_STD_MULTIPLIER * std
                    if np.isfinite(std) and std > 0
                    else np.nan
                )
            band_lo.append(lo)
            band_hi.append(hi)
    else:
        lo, hi, mean, std = band_params[0]
        values = np.concatenate(band_values[0]) if band_values[0] else np.array([])
        if stretch == "minmax" and values.size:
            plot_lo = float(values.min())
            plot_hi = float(values.max())
        elif stretch == "percentile":
            plot_lo, plot_hi = lo, hi
        else:  # zscore
            plot_lo, plot_hi = _ZSCORE_PLOT_LO, _ZSCORE_PLOT_HI
        plot_vmin = vmin if vmin is not None else plot_lo
        plot_vmax = vmax if vmax is not None else plot_hi

    im = None
    drawn_uris: set[str] = set()
    footprints: list[BaseGeometry] = []

    for _, row in artifacts.iterrows():
        footprint = cast(BaseGeometry, row["cell_utm_footprint"])
        footprints.append(footprint)

        patch_info = uri_to_patch.get(str(row["uri"]))
        if patch_info is not None:
            uri = str(row["uri"])
            if uri not in drawn_uris:
                drawn_uris.add(uri)
                data, bounds = patch_info
                extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
                if is_rgb:
                    rgb = np.zeros(
                        (data.shape[1], data.shape[2], n_bands), dtype=np.float32
                    )
                    for b in range(n_bands):
                        lo = band_lo[b]
                        hi = band_hi[b]
                        if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                            rgb[:, :, b] = np.clip((data[b] - lo) / (hi - lo), 0.0, 1.0)
                        else:
                            rgb[:, :, b] = np.where(np.isfinite(data[b]), 0.5, np.nan)
                    im = ax.imshow(
                        rgb,
                        extent=extent,
                        origin="upper",
                    )
                else:
                    data = data[0]
                    if stretch == "zscore":
                        if np.isfinite(std) and std > 0:
                            data = (data - mean) / std
                        else:
                            data = np.where(np.isfinite(data), 0.0, np.nan)
                    im = ax.imshow(
                        data,
                        cmap=cmap,
                        extent=extent,
                        origin="upper",
                        vmin=plot_vmin,
                        vmax=plot_vmax,
                    )

        # Annotate the grid cell ID at the footprint centre.
        if annotate_cells:
            centroid = footprint.centroid
            ax.text(
                centroid.x,
                centroid.y,
                str(row.get("grid_cell", "")),
                color=annotation_color,
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                bbox={
                    "facecolor": "black",
                    "alpha": 0.5,
                    "pad": 1,
                    "edgecolor": "none",
                },
            )

    # Overlay all grid-cell footprints in one call.
    if footprints:
        gpd.GeoSeries(footprints).plot(
            ax=ax,
            facecolor="none",
            edgecolor=footprint_edgecolor,
            linestyle="--",
            linewidth=footprint_linewidth,
        )

    ax.set_title(title, fontsize=16)
    ax.set_xlabel("UTM X")
    ax.set_ylabel("UTM Y")
    ax.set_aspect("equal", "datalim")
    ax.set_xlim(minx - _FOOTPRINT_VIEW_BUFFER_M, maxx + _FOOTPRINT_VIEW_BUFFER_M)
    ax.set_ylim(miny - _FOOTPRINT_VIEW_BUFFER_M, maxy + _FOOTPRINT_VIEW_BUFFER_M)

    legend_patch = mpatches.Patch(
        edgecolor=footprint_edgecolor,
        facecolor="none",
        linestyle="--",
        linewidth=footprint_linewidth,
        label="Target Grid Cell",
    )
    fig.legend(
        handles=[legend_patch],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.1),
        ncol=1,
        fontsize=12,
    )

    if (
        not is_rgb
        and colorbar
        and im is not None
        and plot_vmin is not None
        and plot_vmax is not None
    ):
        cbar = fig.colorbar(im, ax=ax, shrink=0.6)
        if colorbar_label:
            cbar.set_label(colorbar_label)

    return fig, ax
