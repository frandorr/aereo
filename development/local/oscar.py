"""OSCAR Data Explorer - Marimo Notebook

This notebook demonstrates the usage of the OSCAR API fetcher module
located at: components/data/oscar_fetcher.py

The module provides functions to fetch satellite and instrument data from
the WMO OSCAR database and convert it to pandas DataFrames.
"""

import marimo

__generated_with = "0.21.1"
app = marimo.App(width="medium")


@app.cell
def _():
    """Import the OSCAR fetcher module."""
    from aer.data.oscar_fetcher import (
        fetch_and_process_all_data,
    )

    print("=" * 60)
    print("OSCAR FETCHER MODULE IMPORTED")
    print("=" * 60)
    print("\nAvailable functions:")
    print("  - fetch_oscar_satellites(max_pages=None)")
    print("  - fetch_oscar_instruments(max_pages=None)")
    print("  - satellites_to_dataframe(satellites_data)")
    print("  - extract_instruments_from_satellites(satellites_data)")
    print("  - fetch_and_process_all_data(max_pages=None)")
    return (fetch_and_process_all_data,)


@app.cell
def _(fetch_and_process_all_data):
    """Fetch and process OSCAR data (limited to 2 pages for demo)."""
    print("=" * 60)
    print("FETCHING OSCAR DATA (Demo - 2 pages)")
    print("=" * 60)

    # Fetch data (2 pages = 60 satellites with ~180 instruments)
    df_satellites, df_instruments = fetch_and_process_all_data(max_pages=1)
    return df_instruments, df_satellites


@app.cell
def _(df_satellites):
    df_satellites
    return


@app.cell
def _(df_instruments):
    df_instruments
    return


@app.cell
def _(df_satellites):
    """Display satellites DataFrame."""
    print("=" * 60)
    print("SATELLITES DATAFRAME")
    print("=" * 60)
    print(f"\nShape: {df_satellites.shape}")
    print(f"Columns: {list(df_satellites.columns)}")
    print("\nFirst 5 rows:")
    print(df_satellites.head())
    print("\nData types:")
    print(df_satellites.dtypes)
    return


@app.cell
def _(df_instruments):
    """Display instruments DataFrame."""
    print("=" * 60)
    print("INSTRUMENTS DATAFRAME")
    print("=" * 60)
    print(f"\nShape: {df_instruments.shape}")
    print(f"Columns: {list(df_instruments.columns)}")
    print("\nFirst 10 rows:")
    print(df_instruments.head(10))
    print("\nInstruments per satellite (sample):")
    print(df_instruments.groupby("satellite_acronym").size().head(15))
    return


@app.cell
def _(df_instruments):
    df_instruments.drop_duplicates(subset=["slug"])
    return


@app.cell
def _(df_satellites):
    df_satellites[
        df_satellites.data_access_link.notna() & (df_satellites.status == "Operational")
    ].sort_values("slug")
    return


@app.cell
def _(df_instruments, df_satellites):
    """Display summary statistics."""
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    print("\nSatellites:")
    print(f"  Total: {len(df_satellites)}")
    print(f"  Active: {len(df_satellites[df_satellites['status'] == 'Active'])}")
    print(f"  Inactive: {len(df_satellites[df_satellites['status'] == 'Inactive'])}")
    print(f"  Space Agencies: {df_satellites['space_agency'].nunique()}")
    print("  Top agencies:")
    print(df_satellites["space_agency"].value_counts().head())

    print("\nInstruments:")
    print(f"  Total: {len(df_instruments)}")
    print(f"  Unique instruments: {df_instruments['instrument_id'].nunique()}")
    print("  Instrument types (top 10):")
    print(df_instruments["instrument_type"].value_counts().head(10))

    print("\nSample satellite-instrument relationships:")
    sample = df_instruments[["satellite_acronym", "name", "instrument_type"]].head(10)
    print(sample.to_string(index=False))
    return


@app.cell
def _():
    """API Documentation reference."""
    print("=" * 60)
    print("API DOCUMENTATION")
    print("=" * 60)
    print("""
    OSCAR (Observing Systems Capability Analysis and Review)
    is the WMO's database of satellite observing systems.

    API Base URL: https://space.oscar.wmo.int/api/v1
    Documentation: https://space.oscar.wmo.int/apidoc/

    Module location: components/data/oscar_fetcher.py

    Usage example:
    from components.data.oscar_fetcher import fetch_and_process_all_data

    # Fetch all data
    df_satellites, df_instruments = fetch_and_process_all_data()

    # Or fetch specific number of pages
    df_satellites, df_instruments = fetch_and_process_all_data(max_pages=5)

    The module handles pagination automatically and converts the API
    response (HAL+JSON format) into clean pandas DataFrames.
    """)
    return


if __name__ == "__main__":
    app.run()
