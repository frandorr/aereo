"""Pandera schemas for validating aer dataframes.

Contains schema definitions for search results and grid dataframes
used across the aer plugin system.
"""

import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoSeries


class GridSchema(pa.DataFrameModel):
    """Schema for grid dataframes used in the aer plugin system.

    This schema defines the expected structure of the GeoDataFrame representing
    the spatial grid used for task preparation and artifact organization. It
    includes fields for grid cell identifiers, spatial geometry, and any
    additional metadata needed for task preparation and artifact management.

    Fields:
        grid_cell (str): Unique identifier for the grid cell (e.g., "0U_0R").
        grid_dist (int): Distance in meters that defines the size of the grid cell.
        grid_geometry (geometry): Spatial geometry of the grid cell (e.g., footprint).
        grid_utm_crs (str): EPSG code for the UTM coordinate reference system corresponding to the grid_cell.
        grid_utm_footprint (geometry): Spatial geometry of the grid_cell footprint in the UTM coordinate reference system.
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

    Fields:
        id (str): Unique identifier for the search result (e.g., a product ID).
        collection (str): Identifier for the collection this result belongs to.
        geometry (geometry): Spatial geometry of the result (e.g., footprint).
        start_time (datetime): Start time of the data acquisition.
        end_time (datetime): End time of the data acquisition.
        href (str): URL or reference to the data source for extraction.
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
    """
    Schema for artifacts created during extraction.

    Attributes:
    - id (str): Unique identifier for the artifact.
    - source_ids (str): Comma-separated list of source identifiers that contributed to the artifact.
    - start_time (datetime): Start time of the data acquisition for the artifact.
    - end_time (datetime): End time of the data acquisition for the artifact.
    - uri (str): URI or reference to the artifact's location (e.g., file path, cloud storage URL).
    - geometry (geometry): Spatial geometry of the artifact (e.g., footprint).
    - collection (str, optional): Identifier for the collection this artifact belongs to,
        which can be used for organizational and metadata purposes.

    GridSchema fields are inherited, so the artifact will also include:
    - grid_cell (str): Unique identifier for the grid cell (e.g., "0U_0R").
    - grid_dist (int): Distance in meters that defines the size of the grid cell.
    - cell_geometry (geometry): Spatial geometry of the grid cell (e.g., footprint).
    - cell_utm_crs (str): EPSG code for the UTM coordinate reference system corresponding to the grid_cell.
    - cell_utm_footprint (geometry): Spatial geometry of the grid_cell footprint in the UTM coordinate reference system.

    """

    id: Series[pa.String] = pa.Field(unique=True, nullable=False)
    source_ids: Series[pa.String] = pa.Field(nullable=False)
    start_time: Series[pa.DateTime] = pa.Field(nullable=True)
    end_time: Series[pa.DateTime] = pa.Field(nullable=True)
    uri: Series[pa.String] = pa.Field(nullable=False)
    geometry: GeoSeries = pa.Field(nullable=False)
    collection: Series[pa.String] = pa.Field(nullable=True)

    class Config:
        coerce = True
        strict = False
