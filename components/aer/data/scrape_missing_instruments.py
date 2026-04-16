"""Scrape missing instrument data from WMO OSCAR website.

Fetches instrument channel tables from the WMO OSCAR space website
for operational satellites, parses the HTML to extract channel
characteristics, and saves them as JSON files for use by the
normalize_instruments script.
"""

#!/usr/bin/env python3
import argparse
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import cast

import httpx
import pandas as pd
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://space.oscar.wmo.int/instruments/view/"


def slugify(text: str) -> str:
    """Convert acronym to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "_", text)
    return text.strip("_")


def fetch_page(client: httpx.Client, normalized_acronym: str) -> str | None:
    """Fetch the OSCAR instrument page HTML. Returns None on failure."""
    url = BASE_URL + urllib.parse.quote(normalized_acronym)
    try:
        resp = client.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log.debug(f"Fetch failed for {normalized_acronym}: {e}")
        return None


def parse_characteristics(html: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the Detailed characteristics frequency table."""
    soup = BeautifulSoup(html, "html.parser")
    freq_div = soup.find("div", class_="frequencytable")
    if not freq_div:
        return [], []

    table = freq_div.find("table")
    if not table:
        return [], []

    rows = table.find_all("tr")
    if not rows:
        return [], []

    columns = []
    header_row_idx = 0
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        if cells and (row.find("th") or cells[0].find("strong")):
            columns = [c.get_text(separator=" ", strip=True) for c in cells]
            header_row_idx = i
            break

    if not columns:
        return [], []

    channels = []
    for row in rows[header_row_idx + 1 :]:
        cells = row.find_all("td")
        if not cells or len(cells) < len(columns):
            continue
        channel = {
            col: cells[j].get_text(separator=" ", strip=True)
            for j, col in enumerate(columns)
        }
        if any(v for v in channel.values()):
            channels.append(channel)

    return columns, channels


def run(instruments_csv: Path, output_dir: Path, status: str = "all"):
    output_dir.mkdir(parents=True, exist_ok=True)

    instruments = pd.read_csv(instruments_csv)
    if status == "all":
        instruments = instruments.drop_duplicates(subset=["slug"]).reset_index(
            drop=True
        )
    else:
        instruments = (
            cast(pd.DataFrame, instruments[instruments["status"] == status])
            .drop_duplicates(subset=["slug"])
            .reset_index(drop=True)
        )

    existing_files = set(f.name for f in output_dir.glob("*.json"))

    client = httpx.Client(
        headers={"User-Agent": "aer-scraper/1.0 (research)"},
        follow_redirects=True,
    )

    added = 0
    skipped = 0
    no_channels = 0

    try:
        for _, row in instruments.iterrows():
            slug = cast(str, row["slug"])
            name = row["name"]
            fullname = row["fullname"]
            instrument_type = row["instrument_type"]
            classification = row["classification"]
            filename = f"{slug}.json"

            if filename in existing_files:
                skipped += 1
                continue

            html = fetch_page(client, slug)
            if not html:
                continue

            cols, channels = parse_characteristics(html)

            if channels:
                data = {
                    "instrument_acronym": name,
                    "instrument_fullname": fullname,
                    "instrument_type": instrument_type,
                    "instrument_classification": classification,
                    "url": BASE_URL + slug,
                    "columns": cols,
                    "channels": channels,
                }
                out_path = output_dir / filename
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                log.info(
                    f"[SUCCESS] Scraped {len(channels)} channels for {slug} ({filename})"
                )
                added += 1
                existing_files.add(filename)
                existing_files.add(f"{slug}.json")
            else:
                log.debug(
                    f"[NO DATA] No channels table found for {slug} at OSCAR URL: {BASE_URL + slug}"
                )
                no_channels += 1

            time.sleep(0.3)

    finally:
        client.close()

    log.info(
        f"Done. Added: {added} | Skipped existing: {skipped} | No channels found on site: {no_channels}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Fetch missing scraped JSON payloads based on operational satellites list."
    )
    parser.add_argument(
        "--instruments-csv",
        type=str,
        default="wmo_oscar_instruments.csv",
        help="Path to wmo_oscar_instruments.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="wmo_oscar_instruments",
        help="Directory where JSONs are saved",
    )
    parser.add_argument(
        "--status",
        type=str,
        default="all",
        help="Scrape instruments with the specified status",
    )

    args = parser.parse_args()

    instruments_csv = Path(args.instruments_csv)
    out_dir = Path(args.out_dir)

    if not instruments_csv.exists():
        log.error(f"Provided satellite CSV path doesn't exist: {instruments_csv}")
        return

    run(instruments_csv, out_dir, args.status)


if __name__ == "__main__":
    main()
