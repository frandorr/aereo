"""Pandera schemas for validating aer dataframes.

Contains schema definitions for search results and grid dataframes
used across the aer plugin system.
"""

import pandera.pandas as pa
from pandera.typing import Series
from pandera.typing.geopandas import GeoSeries


class SearchResultSchema(pa.DataFrameModel):
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


class GridSchema(pa.DataFrameModel):  # type: ignore[misc]
    """Schema for validating a MajorTom-compliant grid GeoDataFrame.

    Defines the standard set of columns for the global grid.

    grid_cell: A unique identifier for each grid cell, typically in the format "row_col" (e.g., "0U_0R").
    row: The row identifier for the grid cell.
    col: The column identifier for the grid cell.
    utm_crs: The EPSG code for the UTM coordinate reference system corresponding to the grid cell's location,
            which can be used for spatial analysis and transformations.
    dist: The distance in meters that defines the size of each grid cell, which can be used for spatial analysis and transformations.

    """

    grid_cell: Series[str]
    utm_footprint: GeoSeries
    utm_crs: Series[str]
    dist: Series[int]
