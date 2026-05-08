"""Shared utilities for example notebooks and scripts."""

import cartopy.crs as ccrs
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from cartopy.io.img_tiles import OSM


def plot_aoi(
    gdf: gpd.GeoDataFrame,
    label: str = "AOI",
    buffer: float = 0.02,
    zoom: int = 12,
    figsize: tuple[int, int] = (10, 8),
) -> None:
    """Plot a GeoDataFrame on an OpenStreetMap base layer.

    Parameters
    ----------
    gdf:
        GeoDataFrame containing the geometry to plot.
    label:
        Legend label for the AOI outline.
    buffer:
        Degrees of padding around the geometry bounds.
    zoom:
        OSM tile zoom level (higher = more detailed).
    figsize:
        Matplotlib figure size in inches.
    """
    fig, ax = plt.subplots(
        figsize=figsize, subplot_kw={"projection": ccrs.PlateCarree()}
    )

    # OpenStreetMap tiles as base layer
    osm = OSM()
    ax.add_image(osm, zoom)

    # Plot AOI
    gdf.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=2.5)

    # Proxy artist for legend
    aoi_patch = mpatches.Patch(
        facecolor="none", edgecolor="red", linewidth=2.5, label=label
    )

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
    ax.legend(handles=[aoi_patch], loc="upper left")
    ax.set_title("Selected Area of Interest")

    plt.show()
