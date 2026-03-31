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
import pandas as pd
import httpx
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


def normalize_payload_for_url(payload: str) -> str:
    """
    Apply exact URL formatting for WMO OSCAR payload URLs.
    Many payload strings in the Satellites CSV look like "CRIS (ACE)",
    but the OSCAR URL endpoint uses "cris_ace".
    """
    n = payload.lower().strip()
    n = n.replace(" (", "_").replace(")", "").replace(" ", "_").replace("/", "")
    return n


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


def run(sat_csv: Path, output_dir: Path, all_status: bool = False):
    output_dir.mkdir(parents=True, exist_ok=True)

    satellites = pd.read_csv(sat_csv)
    if all_status:
        payloads = (
            satellites["Payload"]
            .dropna()
            .str.split("\n")
            .explode()
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
        )
    else:
        payloads = (
            satellites.loc[satellites["Sat status"] == "Operational", "Payload"]
            .dropna()
            .str.split("\n")
            .explode()
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
        )

    log.info(f"Checking {len(payloads)} unique payloads from satellite records...")

    existing_files = set(f.name for f in output_dir.glob("*.json"))

    client = httpx.Client(
        headers={"User-Agent": "aer-scraper/1.0 (research)"},
        follow_redirects=True,
    )

    added = 0
    skipped = 0
    no_channels = 0

    try:
        for payload in payloads:
            slug = slugify(payload)
            filename = f"{slug}.json"

            if filename in existing_files:
                skipped += 1
                continue

            # WMO often translates "Instrument (Satellite)" into "instrument_satellite"
            search_acronym = normalize_payload_for_url(payload)

            # Check if this alternate slug already exists just to be safe
            alt_slug = slugify(search_acronym)
            if f"{alt_slug}.json" in existing_files:
                skipped += 1
                continue

            html = fetch_page(client, search_acronym)

            # If standard string formatting didn't work, try stripping the satellite name completely
            if not html and " (" in payload:
                base_acronym = normalize_payload_for_url(payload.split(" (")[0])
                html = fetch_page(client, base_acronym)
                search_acronym = base_acronym

            if not html:
                time.sleep(0.3)
                continue

            cols, channels = parse_characteristics(html)

            if channels:
                data = {
                    "instrument_id": None,
                    "instrument_acronym": payload,
                    "instrument_fullname": "",
                    "url": BASE_URL + search_acronym,
                    "columns": cols,
                    "channels": channels,
                }
                out_path = output_dir / filename
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                log.info(
                    f"[SUCCESS] Scraped {len(channels)} channels for {payload} ({filename})"
                )
                added += 1
                existing_files.add(filename)
                existing_files.add(f"{alt_slug}.json")
            else:
                log.debug(
                    f"[NO DATA] No channels table found for {payload} at OSCAR URL: {search_acronym}"
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
        "--sat-csv",
        type=str,
        default="wmo_oscar_satellites.csv",
        help="Path to wmo_oscar_satellites.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="wmo_oscar_instruments",
        help="Directory where JSONs are saved",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape all payloads, not just 'Operational' ones",
    )

    args = parser.parse_args()

    sat_csv = Path(args.sat_csv)
    out_dir = Path(args.out_dir)

    if not sat_csv.exists():
        log.error(f"Provided satellite CSV path doesn't exist: {sat_csv}")
        return

    run(sat_csv, out_dir, args.all)


if __name__ == "__main__":
    main()
