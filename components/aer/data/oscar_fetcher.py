"""OSCAR API Data Fetcher

This module provides functions to fetch satellite and instrument data from the
WMO OSCAR (Observing Systems Capability Analysis and Review) API.

API Documentation: https://space.oscar.wmo.int/apidoc/
Base URL: https://space.oscar.wmo.int/api/v1

Example usage:
    from components.data.oscar_fetcher import (
        fetch_oscar_satellites,
        fetch_oscar_instruments,
        satellites_to_dataframe,
        extract_instruments_from_satellites,
    )

    # Fetch all satellites
    satellites = fetch_oscar_satellites()
    df_satellites = satellites_to_dataframe(satellites)

    # Extract instruments from satellite data
    df_instruments = extract_instruments_from_satellites(satellites)
"""

import time
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://space.oscar.wmo.int/api/v1"


def fetch_oscar_satellites(max_pages: int | None = None) -> list[dict[str, Any]]:
    """Fetch all satellites from OSCAR API with automatic pagination handling.

    API Endpoint: GET /api/v1/satellites
    Documentation: https://space.oscar.wmo.int/apidoc/

    Args:
        max_pages: Maximum number of pages to fetch (None for all)

    Returns:
        List of satellite dictionaries from _embedded.satellites
    """
    satellites = []
    page = 1

    while True:
        url = f"{BASE_URL}/satellites?page={page}"
        print(f"Fetching page {page}...", end=" ")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract satellites from _embedded
            page_satellites = data.get("_embedded", {}).get("satellites", [])
            if not page_satellites:
                print("No more data")
                break

            satellites.extend(page_satellites)
            print(f"Got {len(page_satellites)} satellites")

            # Check for next page
            next_link = data.get("_links", {}).get("next", {}).get("href")
            if not next_link:
                print("No next page")
                break

            page += 1

            # Check max_pages limit
            if max_pages and page > max_pages:
                print(f"Reached max_pages limit ({max_pages})")
                break

            # Small delay to be nice to the API
            time.sleep(0.1)

        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            break

    return satellites


def fetch_oscar_instruments(max_pages: int | None = None) -> list[dict[str, Any]]:
    """Fetch all instruments from OSCAR API with automatic pagination handling.

    API Endpoint: GET /api/v1/instruments
    Documentation: https://space.oscar.wmo.int/apidoc/

    Args:
        max_pages: Maximum number of pages to fetch (None for all)

    Returns:
        List of instrument dictionaries from _embedded.instruments
    """
    instruments = []
    page = 1

    while True:
        url = f"{BASE_URL}/instruments?page={page}"
        print(f"Fetching instruments page {page}...", end=" ")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract instruments from _embedded
            page_instruments = data.get("_embedded", {}).get("instruments", [])
            if not page_instruments:
                print("No more data")
                break

            instruments.extend(page_instruments)
            print(f"Got {len(page_instruments)} instruments")

            # Check for next page
            next_link = data.get("_links", {}).get("next", {}).get("href")
            if not next_link:
                print("No next page")
                break

            page += 1

            # Check max_pages limit
            if max_pages and page > max_pages:
                print(f"Reached max_pages limit ({max_pages})")
                break

            # Small delay to be nice to the API
            time.sleep(0.1)

        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            break

    return instruments


def satellites_to_dataframe(satellites_data: list[dict]) -> pd.DataFrame:
    """Convert raw satellite API data to a clean pandas DataFrame.

    Args:
        satellites_data: List of satellite dictionaries from OSCAR API

    Returns:
        DataFrame with columns:
            - id: Satellite ID
            - slug: URL-friendly identifier
            - acronym: Short name
            - fullname: Full satellite name
            - space_agency: Operating agency (NASA, JAXA, etc.)
            - status: Active/Inactive/etc.
            - orbit: Orbit type
            - launch_date: Launch date string
            - eol: End of life date
            - altitude: Orbital altitude
            - longitude: Orbital longitude (null for LEO)
            - ect: Equator crossing time
            - wigos_id: WIGOS station identifier
            - data_access_link: URL for data access
            - link: Satellite info link
            - payload: String with instrument names (like original Excel)
    """
    if not satellites_data:
        return pd.DataFrame()

    records = []
    for sat in satellites_data:
        # Extract instrument names for payload column
        instruments = sat.get("satellite-instruments", [])
        payload_slugs = []
        for inst in instruments:
            instrument_data = inst.get("instrument", {})
            slug = instrument_data.get("slug")
            if slug and slug not in payload_slugs:
                payload_slugs.append(slug)
        payload = payload_slugs if payload_slugs else None

        record = {
            "id": sat.get("id"),
            "slug": sat.get("slug"),
            "acronym": sat.get("acronym"),
            "fullname": sat.get("fullname"),
            "space_agency": sat.get("space_agency"),
            "status": sat.get("status"),
            "orbit": sat.get("orbit"),
            "launch_date": sat.get("launch_date"),
            "eol": sat.get("EoL"),
            "altitude": sat.get("Altitude"),
            "longitude": sat.get("longitude"),
            "ect": sat.get("ECT"),
            "wigos_id": sat.get("WIGOS_Station_Identifier"),
            "data_access_link": sat.get("data_access_link"),
            "link": sat.get("link"),
            "payload": payload,
        }
        records.append(record)

    return pd.DataFrame(records)


def extract_instruments_from_satellites(satellites_data: list[dict]) -> pd.DataFrame:
    """Extract instruments from satellite data and create a DataFrame.

    Each satellite has a 'satellite-instruments' array containing
    instruments mounted on that satellite.

    Args:
        satellites_data: List of satellite dictionaries from OSCAR API

    Returns:
        DataFrame with columns:
            - satellite_id: Parent satellite ID (foreign key)
            - satellite_acronym: Parent satellite acronym
            - instrument_id: Instrument ID
            - slug: Instrument slug
            - name: Short instrument name
            - fullname: Full instrument name
            - instrument_type: Type of instrument
            - providing_agency: Agency providing the instrument
            - start_date: When instrument started operating
            - eol: End of life for instrument
            - status: Instrument status
            - classification: List of classification categories (flattened)
    """
    if not satellites_data:
        return pd.DataFrame()

    records = []
    for sat in satellites_data:
        sat_id = sat.get("id")
        sat_acronym = sat.get("acronym")
        instruments = sat.get("satellite-instruments", [])

        for inst in instruments:
            instrument_data = inst.get("instrument", {})

            # Flatten classification list to string
            classification = inst.get("classification", [])
            classification_str = ", ".join(classification) if classification else None

            record = {
                "satellite_id": sat_id,
                "satellite_acronym": sat_acronym,
                "instrument_id": instrument_data.get("id"),
                "slug": instrument_data.get("slug"),
                "name": instrument_data.get("name"),
                "fullname": instrument_data.get("fullname"),
                "instrument_type": instrument_data.get("instrumenttype"),
                "providing_agency": instrument_data.get("providing-agency"),
                "start_date": inst.get("start-date"),
                "eol": inst.get("EoL"),
                "status": inst.get("status"),
                "classification": classification_str,
            }
            records.append(record)

    return pd.DataFrame(records)


def fetch_and_process_all_data(
    max_pages: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convenience function to fetch and process all OSCAR data.

    Args:
        max_pages: Maximum number of pages to fetch (None for all)

    Returns:
        Tuple of (satellites_df, instruments_df)
    """
    print("=" * 60)
    print("FETCHING OSCAR DATA")
    print("=" * 60)

    # Fetch satellites
    satellites_raw = fetch_oscar_satellites(max_pages=max_pages)
    df_satellites = satellites_to_dataframe(satellites_raw)

    # Extract instruments
    df_instruments = extract_instruments_from_satellites(satellites_raw)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Satellites: {len(df_satellites)}")
    print(f"Instruments: {len(df_instruments)}")
    print(f"Unique instruments: {df_instruments['instrument_id'].nunique()}")

    return df_satellites, df_instruments


if __name__ == "__main__":
    # Demo: Fetch and display data
    df_satellites, df_instruments = fetch_and_process_all_data(max_pages=None)
    # save to wmo_oscar_instruments.csv and wmo_oscar_satellites.csv
    df_satellites.to_csv("wmo_oscar_satellites.csv", index=False)
    df_instruments.to_csv("wmo_oscar_instruments.csv", index=False)
