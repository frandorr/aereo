"""Pandera schemas for validating aer dataframes.

Contains schema definitions for search results and grid dataframes
used across the aereo plugin system.
"""

from __future__ import annotations

from typing import cast

import geopandas as gpd
import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoDataFrame, GeoSeries


class GridSchema(pa.DataFrameModel):
    """Schema for grid dataframes used in the aereo plugin system.

    This schema defines the expected structure of the GeoDataFrame representing
    the spatial grid used for task preparation and artifact organization. It
    includes fields for grid cell identifiers, spatial geometry, and any
    additional metadata needed for task preparation and artifact management.

    Attributes:
        grid_cell: Unique identifier for the grid cell (e.g., "0U_0R").
        grid_dist: Distance in meters that defines the size of the grid cell.
        cell_geometry: Spatial geometry of the grid cell (e.g., footprint).
        cell_utm_crs: EPSG code for the UTM coordinate reference system corresponding to the grid_cell.
        cell_utm_footprint: Spatial geometry of the grid_cell footprint in the UTM coordinate reference system.
    """

    grid_cell: Series[pa.String] = pa.Field(nullable=False)
    grid_dist: Series[pa.Int] = pa.Field(nullable=False)
    cell_geometry: GeoSeries = pa.Field(nullable=False)
    cell_utm_crs: Series[pa.String] = pa.Field(nullable=False)
    cell_utm_footprint: GeoSeries = pa.Field(nullable=False)

    class Config:
        coerce = True
        strict = False


class AssetSchema(pa.DataFrameModel):
    """Schema for search results returned by the `search` hook.

    This schema defines the expected structure of the GeoDataFrame returned
    by search implementations. It includes fields for collection identifiers,
    spatial geometry, temporal information, and any additional metadata needed
    for task preparation and extraction.

    Attributes:
        id: Unique identifier for the search result (e.g., a product ID).
        collection: Identifier for the collection this result belongs to.
        geometry: Spatial geometry of the result (e.g., footprint).
        start_time: Start time of the data acquisition.
        end_time: End time of the data acquisition.
        href: URL or reference to the data source for extraction.
        crs: Native coordinate reference system of the asset (e.g., "EPSG:32633").
            When present, all assets in an ``ExtractionTask`` must share the
            same value so the reader can return a single ``xr.Dataset`` in
            native CRS.
    """

    id: Series[pa.String] = pa.Field(nullable=False)
    collection: Series[pa.String] = pa.Field(nullable=False)
    geometry: GeoSeries = pa.Field(nullable=True)
    start_time: Series[pa.DateTime] = pa.Field(nullable=False)
    end_time: Series[pa.DateTime] = pa.Field(nullable=False)
    href: Series[pa.String] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True


class ArtifactSchema(GridSchema):
    """Schema for artifacts created during extraction.

    Inherits all fields from :class:`GridSchema`.

    Attributes:
        id: Unique identifier for the artifact.
        source_ids: Comma-separated list of source identifiers that contributed to the artifact.
        start_time: Start time of the data acquisition for the artifact.
        end_time: End time of the data acquisition for the artifact.
        uri: URI or reference to the artifact's location (e.g., file path, cloud storage URL).
        geometry: Spatial geometry of the artifact (e.g., footprint).
        collection: Identifier for the collection this artifact belongs to,
            which can be used for organizational and metadata purposes.
    """

    id: Series[pa.String] = pa.Field(unique=True, nullable=False)
    source_ids: Series[pa.String] = pa.Field(nullable=False)
    start_time: Series[pa.DateTime] = pa.Field(nullable=True)
    end_time: Series[pa.DateTime] = pa.Field(nullable=True)
    uri: Series[pa.String] = pa.Field(nullable=False)
    geometry: GeoSeries = pa.Field(nullable=False)
    collection: Series[pa.String] = pa.Field(nullable=True)

    @classmethod
    def empty_geodataframe(cls) -> GeoDataFrame["ArtifactSchema"]:
        """Return an empty GeoDataFrame with ArtifactSchema columns.

        Returns:
            An empty validated GeoDataFrame with the correct schema columns,
            including a geometry column.
        """
        columns = list(cls.to_schema().columns.keys())
        if "geometry" not in columns:
            columns.append("geometry")
        gdf = gpd.GeoDataFrame(columns=columns, geometry="geometry")
        return cast(GeoDataFrame["ArtifactSchema"], cls.validate(gdf))
