"""Visualization utilities for plotting AOIs and geospatial data with cartopy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import geopandas as gpd

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

    handles = []
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

    Returns:
        None. Displays the plot via ``plt.show()``.
    """
    import cartopy.crs as ccrs
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(
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
    bounds = gdf.total_bounds
    ax.set_extent(  # type: ignore[reportAttributeAccessIssue]
        [
            bounds[0] - buffer,
            bounds[2] + buffer,
            bounds[1] - buffer,
            bounds[3] + buffer,
        ],
        crs=ccrs.PlateCarree(),
    )

    ax.gridlines(  # type: ignore[reportAttributeAccessIssue]
        draw_labels=True, linestyle="--", alpha=0.5
    )
    ax.legend(handles=handles, loc="upper left")
    ax.set_title("Selected Area of Interest")

    plt.show()
