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


def _normalize_header(text: str) -> str:
    """Map a header cell text to one of our output column names."""
    t = text.lower().strip()
    if "central" in t and "wavelength" in t:
        return "central_wavelength"
    if "bandwidth" in t:
        return "bandwidth"
    if "snr" in t or "nedt" in t or "ne" in t and "t" in t:
        return "snr_or_nedt"
    if "resolution" in t:
        return "resolution"
    return ""


def _detect_columns(header_cells: list) -> dict[int, str]:
    """Inspect header cells and return {cell_index: output_field_name} mapping."""
    mapping: dict[int, str] = {}
    for idx, cell in enumerate(header_cells):
        field = _normalize_header(cell.get_text(strip=True))
        if field:
            mapping[idx] = field
    return mapping


def parse_channels(html: str) -> list[dict[str, str]]:
    """Parse the frequency table from an instrument page.

    Returns a list of dicts with keys: central_wavelength, bandwidth,
    snr_or_nedt, resolution.

    Tables have varying column layouts. We detect which columns correspond
    to our output fields by examining header cell text.
    """
    soup = BeautifulSoup(html, "html.parser")
    freq_div = soup.find("div", class_="frequencytable")
    if freq_div is None:
        return []

    table = freq_div.find("table")
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    # Detect column mapping from the header row (first <tr> with <strong> or <th>)
    col_map: dict[int, str] = {}
    header_row_idx = 0
    for i, row in enumerate(rows):
        cells = row.find_all("td")
        if cells and cells[0].find("strong"):
            col_map = _detect_columns(cells)
            header_row_idx = i
            break

    if not col_map:
        # Fallback: assume 4-column layout (central_wavelength, bandwidth, snr_or_nedt, resolution)
        col_map = {
            0: "central_wavelength",
            1: "bandwidth",
            2: "snr_or_nedt",
            3: "resolution",
        }

    channels: list[dict[str, str]] = []
    for row in rows[header_row_idx + 1 :]:
        cells = row.find_all("td")
        if not cells:
            continue
        # Need at least enough cells for the highest mapped index
        max_idx = max(col_map.keys())
        if len(cells) <= max_idx:
            continue
        entry: dict[str, str] = {}
        for idx, field in col_map.items():
            entry[field] = cells[idx].get_text(strip=True)
        # Only keep rows that have at least a wavelength
        if entry.get("central_wavelength"):
            channels.append(entry)
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
