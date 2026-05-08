"""Visualization utilities for plotting AOIs and geospatial data with cartopy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import geopandas as gpd


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

    Parameters
    ----------
    gdf:
        GeoDataFrame containing the geometry to plot.
    label:
        Legend label for the AOI outline.
    buffer:
        Degrees of padding around the geometry bounds.
    width:
        Figure width in inches.
    height:
        Figure height in inches.
    assets:
        Optional GeoDataFrame of asset footprints to overlay.
    asset_label:
        Legend label for the asset footprints.
    tiles:
        Whether to fetch OpenStreetMap raster tiles. Default is ``False``
        to avoid HTTP 429 rate-limit errors.
    zoom:
        OSM tile zoom level when ``tiles=True``.
    """
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(
        figsize=(width, height), subplot_kw={"projection": ccrs.PlateCarree()}
    )

    # Base layer
    if tiles:
        from cartopy.io.img_tiles import OSM

        osm = OSM()
        ax.add_image(osm, zoom)
    else:
        ax.add_feature(cfeature.LAND, facecolor="#f5f5f0", zorder=0)
        ax.add_feature(cfeature.OCEAN, facecolor="#d6eaf8", zorder=0)
        ax.add_feature(cfeature.COASTLINE, linewidth=0.6, zorder=1)
        ax.add_feature(cfeature.BORDERS, linewidth=0.4, zorder=1)
        ax.add_feature(
            cfeature.LAKES,
            facecolor="#d6eaf8",
            edgecolor="#5dade2",
            linewidth=0.4,
            zorder=1,
        )
        ax.add_feature(cfeature.RIVERS, edgecolor="#5dade2", linewidth=0.4, zorder=1)

    # Plot asset footprints (under AOI so AOI is visible on top)
    handles = []
    if assets is not None and not assets.empty:
        assets.plot(ax=ax, facecolor="none", edgecolor="blue", linewidth=1.5)
        asset_patch = mpatches.Patch(
            facecolor="none", edgecolor="blue", linewidth=1.5, label=asset_label
        )
        handles.append(asset_patch)

    # Plot AOI
    gdf.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=2.5)
    aoi_patch = mpatches.Patch(
        facecolor="none", edgecolor="red", linewidth=2.5, label=label
    )
    handles.append(aoi_patch)

    # Set extent with a small buffer around the AOI
    bounds = gdf.total_bounds
    ax.set_extent(
        [
            bounds[0] - buffer,
            bounds[2] + buffer,
            bounds[1] - buffer,
            bounds[3] + buffer,
        ],
        crs=ccrs.PlateCarree(),
    )

    ax.gridlines(draw_labels=True, linestyle="--", alpha=0.5)
    ax.legend(handles=handles, loc="upper left")
    ax.set_title("Selected Area of Interest")

    plt.show()
