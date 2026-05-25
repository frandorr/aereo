#!/usr/bin/env python3
"""Scrape WMO OSCAR instrument channel characteristics from each instrument's web page.

Reads wmo_oscar_instruments.csv, fetches each instrument's OSCAR page,
extracts the "Detailed characteristics" frequency table, and writes
one JSON file per instrument to components/aereo/data/wmo_oscar_instruments/.
"""

import argparse
import csv
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://space.oscar.wmo.int/instruments/view/"
DATA_DIR = Path(__file__).resolve().parent.parent / "components" / "aereo" / "data"
INSTRUMENTS_CSV = DATA_DIR / "wmo_oscar_instruments.csv"
OUTPUT_DIR = DATA_DIR / "wmo_oscar_instruments"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Convert acronym to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    return text.strip("_")


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


def parse_characteristics(html: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the Detailed characteristics frequency table.

    Returns (columns, channels) where:
    - columns: list of header strings from the table
    - channels: list of dicts mapping header -> cell value

    Returns ([], []) if no frequency table found.
    """
    soup = BeautifulSoup(html, "html.parser")
    freq_div = soup.find("div", class_="frequencytable")
    if freq_div is None:
        return [], []

    table = freq_div.find("table")
    if table is None:
        return [], []

    rows = table.find_all("tr")
    if not rows:
        return [], []

    # Find header row (contains <strong> tags)
    header_row_idx = 0
    columns: list[str] = []
    for i, row in enumerate(rows):
        cells = row.find_all("td")
        if cells and cells[0].find("strong"):
            columns = [c.get_text(strip=True) for c in cells]
            header_row_idx = i
            break

    if not columns:
        return [], []

    channels: list[dict[str, str]] = []
    for row in rows[header_row_idx + 1 :]:
        cells = row.find_all("td")
        if not cells or len(cells) < len(columns):
            continue
        channel = {}
        for j, col in enumerate(columns):
            channel[col] = cells[j].get_text(strip=True)
        # Skip empty rows
        if any(v for v in channel.values()):
            channels.append(channel)

    return columns, channels


def run(limit: int | None = None, resume: bool = False) -> None:
    """Main scraper loop."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    instruments = load_instruments(INSTRUMENTS_CSV)
    total = len(instruments)
    if limit:
        instruments = instruments[:limit]
        log.info("Processing first %d of %d instruments", limit, total)
    else:
        log.info("Processing all %d instruments", total)

    instruments_with_channels = 0
    total_channels = 0
    skipped = 0
    errors = 0
    already_done = 0

    client = httpx.Client(
        headers={"User-Agent": "aer-scraper/1.0 (research; contact: aer-project)"},
        follow_redirects=True,
    )

    try:
        for i, inst in enumerate(instruments, 1):
            inst_id = inst["Id"]
            acronym = inst["Acronym"]
            fullname = inst.get("Full name", "")

            # Skip if already processed (resume mode)
            slug = slugify(acronym)
            out_path = OUTPUT_DIR / f"{slug}.json"
            if resume and out_path.exists():
                already_done += 1
                if already_done % 100 == 0:
                    log.info("Skipped %d already-processed instruments", already_done)
                continue

            html = fetch_page(client, acronym)
            if html is None:
                errors += 1
                if i % 50 == 0:
                    log.info(
                        "Progress: %d/%d | %d with channels | %d errors",
                        i,
                        len(instruments),
                        instruments_with_channels,
                        errors,
                    )
                time.sleep(0.5)
                continue

            columns, channels = parse_characteristics(html)
            if channels:
                instruments_with_channels += 1
                total_channels += len(channels)

                data = {
                    "instrument_id": int(inst_id),
                    "instrument_acronym": acronym,
                    "instrument_fullname": fullname,
                    "url": BASE_URL + urllib.parse.quote(acronym.lower()),
                    "columns": columns,
                    "channels": channels,
                }

                out_path = OUTPUT_DIR / f"{slug}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                skipped += 1

            if i % 50 == 0:
                log.info(
                    "Progress: %d/%d | %d with channels | %d skipped | %d errors",
                    i,
                    len(instruments),
                    instruments_with_channels,
                    skipped,
                    errors,
                )

            time.sleep(0.5)
    finally:
        client.close()

    log.info(
        "Done: %d processed | %d with channels (%d total channels) | %d skipped | %d errors | %d already done",
        len(instruments),
        instruments_with_channels,
        total_channels,
        skipped,
        errors,
        already_done,
    )
    log.info("JSON files written to: %s", OUTPUT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape WMO OSCAR instrument channel characteristics to JSON."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N instruments (for testing).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip instruments that already have JSON files.",
    )
    args = parser.parse_args()
    run(limit=args.limit, resume=args.resume)


if __name__ == "__main__":
    main()
