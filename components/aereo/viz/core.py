"""Visualization utilities for plotting AOIs and geospatial data with cartopy."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import geopandas as gpd
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

_BASE_ZORDER = 0
_OVERLAY_ZORDER = 1
_WATER_COLOR = "#d6eaf8"
_WATER_EDGE_COLOR = "#5dade2"
_LAND_COLOR = "#f5f5f0"
_DEFAULT_LINEWIDTH = 0.4


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
            facecolor="none", edgecolor="blue", linewidth=1.5, label=asset_label
        )
        handles.append(asset_patch)

    aoi_patch = mpatches.Patch(
        facecolor="none", edgecolor="red", linewidth=2.5, label=label
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
        assets.plot(ax=ax, facecolor="none", edgecolor="blue", linewidth=1.5)

    # Plot AOI
    gdf.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=2.5)

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
        groups = search_results[group_by].unique()
        cmap = plt.get_cmap("tab10")
        for idx, group in enumerate(groups):
            subset = search_results[search_results[group_by] == group]
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
            edgecolor="red",
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


def plot_artifact_patches(
    artifacts: gpd.GeoDataFrame,
    *,
    cmap: str = "gray",
    ds_factor: int = 10,
    footprint_edgecolor: str = "red",
    footprint_linewidth: float = 2.0,
    annotate_cells: bool = True,
    annotation_color: str = "cyan",
    fig_width: float = 20.0,
    title: str = "Extracted Patches Spatial Overview",
) -> tuple[Figure, Axes]:
    """Plot extracted raster patches and their grid-cell footprints on one canvas.

    This is useful for quickly inspecting the spatial layout of artifacts
    produced by the extraction pipeline. Each patch's first band is plotted
    at a downsampled resolution, the UTM footprint is overlaid as a dashed
    polygon, and the grid cell ID is annotated at the footprint centre.

    Heavy dependencies (matplotlib, geopandas, rasterio) are imported lazily
    so callers only pay the import cost when this function is actually used.

    Args:
        artifacts: GeoDataFrame of extracted artifacts. Must contain the
            columns ``uri``, ``cell_utm_footprint``, and ``grid_cell``.
        cmap: Colormap passed to ``imshow`` for the raster data.
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

    Returns:
        A tuple of ``(figure, axes)``.

    Raises:
        ValueError: If ``artifacts`` is empty or missing a required column.
    """
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import rasterio
    from shapely.geometry.base import BaseGeometry

    required_cols = {"uri", "cell_utm_footprint", "grid_cell"}
    missing = required_cols - set(artifacts.columns)
    if missing:
        raise ValueError(f"artifacts is missing required columns: {sorted(missing)}")
    if artifacts.empty:
        raise ValueError("artifacts GeoDataFrame is empty")

    minx, miny, maxx, maxy = artifacts["cell_utm_footprint"].total_bounds
    width = maxx - minx
    height = maxy - miny
    aspect_ratio = width / height if height > 0 else 1.0
    fig_height = max(fig_width / aspect_ratio, 2.0)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    for _, row in artifacts.iterrows():
        footprint = cast(BaseGeometry, row["cell_utm_footprint"])

        # Plot the downsampled raster patch at its physical UTM location.
        try:
            with rasterio.open(row["uri"]) as src:
                out_shape = (int(src.height / ds_factor), int(src.width / ds_factor))
                data = src.read(1, out_shape=out_shape)
                bounds = src.bounds
                extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
            ax.imshow(data, cmap=cmap, extent=extent, origin="upper")
        except Exception:
            # If the raster cannot be read, still show the footprint.
            pass

        # Overlay the grid-cell footprint.
        gpd.GeoSeries([footprint]).plot(
            ax=ax,
            facecolor="none",
            edgecolor=footprint_edgecolor,
            linestyle="--",
            linewidth=footprint_linewidth,
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

    ax.set_title(title, fontsize=16)
    ax.set_xlabel("UTM X")
    ax.set_ylabel("UTM Y")
    ax.set_aspect("equal", "datalim")
    ax.set_xlim(minx - 1000, maxx + 1000)
    ax.set_ylim(miny - 1000, maxy + 1000)

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

    return fig, ax
