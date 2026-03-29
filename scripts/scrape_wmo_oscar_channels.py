#!/usr/bin/env python3
"""Scrape WMO OSCAR instrument channel characteristics from each instrument's web page.

Reads wmo_oscar_instruments.csv, fetches each instrument's OSCAR page,
extracts the "Detailed characteristics" frequency table, and writes
wmo_oscar_channels.csv with one row per channel.
"""

import argparse
import csv
import logging
import time
import urllib.parse
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://space.oscar.wmo.int/instruments/view/"
DATA_DIR = Path(__file__).resolve().parent.parent / "components" / "aer" / "data"
INSTRUMENTS_CSV = DATA_DIR / "wmo_oscar_instruments.csv"
CHANNELS_CSV = DATA_DIR / "wmo_oscar_channels.csv"

CSV_FIELDS = [
    "instrument_id",
    "instrument_acronym",
    "central_wavelength",
    "bandwidth",
    "snr_or_nedt",
    "resolution",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_instruments(path: Path) -> list[dict]:
    """Load instruments from the OSCAR instruments CSV."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def fetch_page(client: httpx.Client, acronym: str) -> str | None:
    """Fetch the OSCAR instrument page HTML. Returns None on failure."""
    url = BASE_URL + urllib.parse.quote(acronym.lower())
    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPStatusError as exc:
        log.warning("HTTP %s for %s (%s)", exc.response.status_code, acronym, url)
        return None
    except httpx.RequestError as exc:
        log.warning("Request error for %s: %s", acronym, exc)
        return None


def parse_channels(html: str) -> list[dict[str, str]]:
    """Parse the frequency table from an instrument page.

    Returns a list of dicts with keys: central_wavelength, bandwidth,
    snr_or_nedt, resolution.
    """
    soup = BeautifulSoup(html, "html.parser")
    freq_div = soup.find("div", class_="frequencytable")
    if freq_div is None:
        return []

    table = freq_div.find("table")
    if table is None:
        return []

    rows = table.find_all("tr")
    channels: list[dict[str, str]] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        # Skip header rows that contain <strong> tags
        if cells[0].find("strong"):
            continue
        channels.append(
            {
                "central_wavelength": cells[0].get_text(strip=True),
                "bandwidth": cells[1].get_text(strip=True),
                "snr_or_nedt": cells[2].get_text(strip=True),
                "resolution": cells[3].get_text(strip=True),
            }
        )
    return channels


def run(limit: int | None = None) -> None:
    """Main scraper loop."""
    instruments = load_instruments(INSTRUMENTS_CSV)
    total = len(instruments)
    if limit:
        instruments = instruments[:limit]
        log.info("Processing first %d of %d instruments", limit, total)
    else:
        log.info("Processing all %d instruments", total)

    all_channels: list[dict] = []
    instruments_with_channels = 0

    client = httpx.Client(
        headers={"User-Agent": "aer-scraper/1.0 (research; contact: aer-project)"},
        follow_redirects=True,
    )

    try:
        for i, inst in enumerate(instruments, 1):
            inst_id = inst["Id"]
            acronym = inst["Acronym"]

            html = fetch_page(client, acronym)
            if html is None:
                if i % 50 == 0:
                    log.info(
                        "Processed %d/%d instruments, %d channels so far",
                        i,
                        len(instruments),
                        len(all_channels),
                    )
                time.sleep(0.5)
                continue

            channels = parse_channels(html)
            if channels:
                instruments_with_channels += 1
                for ch in channels:
                    all_channels.append(
                        {
                            "instrument_id": inst_id,
                            "instrument_acronym": acronym,
                            **ch,
                        }
                    )

            if i % 50 == 0:
                log.info(
                    "Processed %d/%d instruments, %d channels so far",
                    i,
                    len(instruments),
                    len(all_channels),
                )

            time.sleep(0.5)
    finally:
        client.close()

    # Write output CSV
    CHANNELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(CHANNELS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(all_channels)

    log.info(
        "Done: %d instruments processed, %d with channels, %d total channel rows → %s",
        len(instruments),
        instruments_with_channels,
        len(all_channels),
        CHANNELS_CSV,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape WMO OSCAR instrument channel characteristics."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N instruments (for testing).",
    )
    args = parser.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
