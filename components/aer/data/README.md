# WMO OSCAR Instrument Data Tools

This directory contains scripts and tools for processing and normalizing satellite instrument metadata scraped from the WMO OSCAR (Observing Systems Capability Analysis and Review Tool) database.

## 1. Fetching OSCAR Data

The `oscar_fetcher.py` script automatically fetches satellite and instrument metadata directly from the WMO OSCAR API, avoiding the need for manual CSV exports. When run, it handles API pagination and generates two files in the current directory: `wmo_oscar_satellites.csv` and `wmo_oscar_instruments.csv`.

**Usage:**

```bash
uv run python oscar_fetcher.py
```

## 2. Scraping Missing Satellite Instruments

Sometimes the original WMO data does not provide complete channel tables in a structured format for all payloads.

The `scrape_missing_instruments.py` script automatically reads `wmo_oscar_instruments.csv`, identifies instruments that lack a corresponding JSON file, and scrapes their channel tables directly from the OSCAR web pages.

**Usage:**

```bash
uv run python scrape_missing_instruments.py
```

Options:
- `--instruments-csv`: Path to the input instruments CSV (default: `wmo_oscar_instruments.csv`)
- `--out-dir`: The directory to write scraped `.json` files (default: `wmo_oscar_instruments`)
- `--status`: Scrape instruments with a specific status, e.g. 'Operational' (default: `all`)

## 3. Normalizing Instrument Schemas

The raw JSON files scraped for instruments (found in the `wmo_oscar_instruments` directory) inherently possess varying, unstructured column schemas due to the varying technological specs of optical, microwave, SAR, and spectrometer instruments.

The `normalize_instruments.py` script automatically standardizes these structures into robust, queryable JSON schemas.

It accomplishes three primary objectives:
1. **Schema Standardization:** Classifies every instrument into 1 of 4 core schemas:
   - `optical_infrared`
   - `microwave`
   - `spectrometer_sounder`
   - `sar_active`
2. **Value Parsing:** Extracts numeric values, ranges (`min`/`max`), dimensions (`x`/`y`), and separates them from their associated physical units (e.g., `"0.4 - 0.7 µm"` becomes an object with `min`, `max`, and `unit`).
3. **Channel Nomenclature:** Intelligently maps the confusing, generic index names (e.g., "Channel 1") of major operational platforms to their genuine, industry-standard spectral identifiers (e.g., MODIS `B01-B36`, ABI `C01-C16`, VIIRS `M1-M16`). It consults an internal fact-checked dictionary (`CHANNEL_MAPPINGS`) built from verified documentation by ESA, JAXA, NASA, WMO, and CMA.

**Usage:**

```bash
uv run python normalize_instruments.py
```

By default with no arguments, this looks for `./wmo_oscar_instruments` and writes to `./wmo_oscar_instruments_normalized`.

You can overwrite your raw JSON files in-place or point to custom folders using arguments:

```bash
# Overwrite in-place
uv run python normalize_instruments.py -i ./wmo_oscar_instruments -o ./wmo_oscar_instruments
```

## Adding New Instrument Channels

If a new premier operational instrument fails to map its correct channel names automatically (and instead falls back to `Band_01`, `Band_02`), you can manually update the explicit naming dictionary.

Open `normalize_instruments.py`, locate the `CHANNEL_MAPPINGS` dictionary at the top of the script, and append the appropriate string array covering your new payload's channel identifiers.

## Nomenclature Sources & References

The hardcoded `CHANNEL_MAPPINGS` in the normalization script replaces vague WMO table indices with rigorous, industry-standard channel names. This mapping was fact-checked against the following specific, verified documentation URLs:

### Copernicus / ESA (European Space Agency)
*   **MSI (Sentinel-2A/B/C):** 13 bands (`B01`-`B12`, `B8A`).
    *Reference:* [Sentinel-2 MSI Technical Guide](https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-2-msi/msi-instrument/) | [ESA Sentinel-2](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2)
*   **SAR-C (Sentinel-1):** Operational Swath Modes (`Stripmap`, `Interferometric Wide Swath`, `Extra Wide Swath`, `Wave`).
    *Reference:* [Sentinel-1 SAR Acquisition Modes](https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-1-sar/acquisition-modes/) | [ESA Sentinel-1](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1)
*   **OLCI & SLSTR (Sentinel-3):**
    *Reference:* [Sentinel-3 OLCI Instrument](https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-3-olci/) | [EUMETSAT Sentinel-3](https://www.eumetsat.int/sentinel-3)

### NASA / NOAA Earth Observing System (EOS)
*   **VIIRS (Suomi NPP, NOAA-20/21):** M-Bands (`M1-M16`), I-Bands (`I1-I5`), and `DNB`.
    *Reference:* [NOAA STAR VIIRS Bands](https://www.star.nesdis.noaa.gov/jpss/VIIRS.php)
*   **MODIS (Terra/Aqua):** `B01` - `B36`.
    *Reference:* [NASA MODIS Specifications](https://modis.gsfc.nasa.gov/about/specifications.php)
*   **GPM Microwave Imager (GMI):** Core microwave frequencies (10.65 to 183.31 GHz).
    *Reference:* [NASA GPM GMI Instrument](https://gpm.nasa.gov/missions/GPM/GMI)
*   **GOES-R ABI:** `C01` - `C16`.
    *Reference:* [NOAA GOES-R ABI Bands](https://www.goes-r.gov/spacesegment/abi.html)
*   **Legacy GOES 12-15 Imager:** Non-sequential index `B01-B04, B06`.
    *Reference:* [CIMSS GOES Imager Channels](https://cimss.ssec.wisc.edu/goes/goes_imager_channels.html) | [eoPortal GOES-N](https://www.eoportal.org/satellite-missions/goes-n)
*   **Landsat OLI (Landsat 8/9):** 9 bands (`B1`–`B9`). Note: WMO OSCAR lists channels by ascending wavelength, placing Cirrus (B9, 1375 nm) before SWIR1 (B6) and SWIR2 (B7) — the `CHANNEL_MAPPINGS` entry accounts for this non-sequential order.
    *Reference:* [USGS Landsat 8 Science Bands](https://www.usgs.gov/landsat-missions/landsat-8) | [WMO OSCAR OLI Instrument](https://space.oscar.wmo.int/instruments/view/oli)
*   **Landsat TIRS (Landsat 8/9):** 2 thermal bands (`B10`, `B11`).
    *Reference:* [USGS Landsat 8 Science Bands](https://www.usgs.gov/landsat-missions/landsat-8) | [WMO OSCAR TIRS Instrument](https://space.oscar.wmo.int/instruments/view/tirs)

### ISRO (Indian Space Research Organisation)
*   **INSAT Sounder:** 19 sequential IR/VIS atmosphere channels.
    *Reference:* [eoPortal INSAT-3D Mission](https://www.eoportal.org/satellite-missions/insat-3d)
*   **OceanSat-3 (EOS-06) OCM:** 13 narrow VNIR bands.
    *Reference:* [eoPortal OceanSat-3 Mission](https://www.eoportal.org/satellite-missions/oceansat-3)

### US Space Force / Commercial Observations
*   **WSF-M MWI:** Polarimetric microwave imager frequencies.
    *Reference:* [eoPortal Weather System Follow-on Microwave](https://www.eoportal.org/satellite-missions/wsf-m)
*   **Tomorrow.io TMS:** 91-205 GHz microwave sounder profiling bands.
    *Reference:* [Tomorrow.io Weather Radar Space Constellation](https://www.tomorrow.io/space/)

### RadarSat / CSA (Canadian Space Agency)
*   **SAR (RADARSAT-1):** Beam Modes (`Standard`, `Wide`, `Fine`, `ScanSAR`, etc.).
    *Reference:* [CSA RADARSAT-1 Modes](https://www.asc-csa.gc.ca/eng/satellites/radarsat1/)

### EUMETSAT / JAXA
*   **SEVIRI (Meteosat):** 12 specific channels (`VIS 0.6`, `IR 10.8`, `HRV`).
    *Reference:* [EUMETSAT MSG Instruments](https://www.eumetsat.int/meteosat-second-generation#MSG-instruments)
*   **AHI (Himawari 8/9):** 16 band mapping.
    *Reference:* [JMA Himawari-8/9 Technical Info](https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/spsg_ahi.html)
