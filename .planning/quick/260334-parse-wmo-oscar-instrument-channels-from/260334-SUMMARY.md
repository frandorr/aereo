# Quick Task 260334 Summary

## Objective
Parse WMO OSCAR instrument channel characteristics from each instrument's web page and store as one JSON file per instrument.

## Results
- **Total instruments in CSV:** 1,230
- **Instruments with channel data:** 262
- **Total channel entries:** varies per instrument type
- **JSON files created:** 262 in `components/aer/data/wmo_oscar_instruments/`
- **Total size:** 1.1 MB

## Implementation
- Script: `scripts/scrape_wmo_oscar_channels.py`
- Uses `httpx` + `beautifulsoup4` to fetch and parse each instrument's WMO OSCAR page
- Extracts "Detailed characteristics" frequency table (varies by instrument type)
- Outputs one JSON file per instrument with flexible column schema
- Rate limited at 0.5s between requests
- Supports `--limit N` and `--resume` flags

## Column examples by instrument type
- **Optical imagers (ABI):** Central wavelength, Bandwidth, SNR or NEΔT, Resolution
- **Multi-angle imagers (3MI):** Channel, Central wavelength, Bandwidth, Polarisation, SNR
- **Sounders (ACE-FTS):** Spectral range, No. of channels, Spectral resolution, SNR
- **SAR instruments:** different columns for frequency, polarization, etc.

## Files modified
- `scripts/scrape_wmo_oscar_channels.py` (rewritten for JSON output + resume support)
- `components/aer/data/wmo_oscar_instruments/*.json` (262 new files)
