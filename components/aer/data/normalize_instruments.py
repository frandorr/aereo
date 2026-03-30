import argparse
import glob
import json
import os
import re
import sys

# Regex patterns
RE_SINGLE = re.compile(r"^(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zµμ%-].*)$")
RE_RANGE = re.compile(
    r"^(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*-\s*(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zµμ%-].*)$"
)
RE_DIM = re.compile(
    r"^(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*[xX]\s*(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zµμ%-].*)$"
)


def parse_value(val_str):
    if not isinstance(val_str, str):
        return val_str

    val_str = val_str.strip()

    m_range = RE_RANGE.match(val_str)
    if m_range:
        return {
            "min": float(m_range.group(1)),
            "max": float(m_range.group(2)),
            "unit": m_range.group(3).strip(),
        }

    m_dim = RE_DIM.match(val_str)
    if m_dim:
        return {
            "x": float(m_dim.group(1)),
            "y": float(m_dim.group(2)),
            "unit": m_dim.group(3).strip(),
        }

    m_single = RE_SINGLE.match(val_str)
    if m_single:
        return {"value": float(m_single.group(1)), "unit": m_single.group(2).strip()}

    try:
        if "." in val_str:
            return {"value": float(val_str), "unit": None}
        return {"value": int(val_str), "unit": None}
    except ValueError:
        pass

    return val_str


def classify_instrument(cols_list):
    str_cols = " ".join([c.lower() for c in cols_list])
    if any(k in str_cols for k in ["operation mode", "swath", "incidence angle"]):
        return "sar_active"
    elif any(k in str_cols for k in ["frequency", "ghz", "quasi-polarisation"]):
        return "microwave"
    elif any(
        k in str_cols
        for k in [
            "wave number",
            "wavenumber",
            "number of channels",
            "resolving power",
            "spectral resolution",
        ]
    ):
        # Check it's truly a sounder (has spectral resolution AND range columns)
        has_resolution = any(
            "spectral resolution" in c.lower() or "resolving" in c.lower()
            for c in cols_list
        )
        has_range = any(
            "spectral range" in c.lower()
            or "cm-1" in c.lower()
            or "wave number" in c.lower()
            for c in cols_list
        )
        if has_resolution and has_range:
            return "spectrometer_sounder"
        elif any(
            k in str_cols
            for k in [
                "wave number",
                "wavenumber",
                "number of channels",
                "resolving power",
            ]
        ):
            return "spectrometer_sounder"
    if any(
        k in str_cols
        for k in [
            "wavelength",
            "spectral interval",
            "wavelenght",
            "spectral range",
            "central",
            # Explicit WMO OSCAR column names for nm-unit optical instruments (e.g. OLI, TIRS):
            "central wavelength",
            "snr",
        ]
    ):
        return "optical_infrared"
    return "unknown"


def normalize_keys(channel, category):
    norm = {}
    for k, v in channel.items():
        kl = k.lower()
        parsed = parse_value(v)

        if category == "optical_infrared":
            if "snr" in kl or "neΔt" in kl:
                if "low" in kl:
                    norm["snr_low"] = parsed
                elif "high" in kl:
                    norm["snr_high"] = parsed
                else:
                    norm["snr_or_nedt"] = parsed
            elif "wavelength" in kl or "spectral" in kl or "band" in kl:
                if (
                    "interval" in kl
                    or "bandwidth" in kl
                    or "width" in kl
                    or "range" in kl
                ):
                    norm["bandwidth"] = parsed
                else:
                    norm["central_wavelength"] = parsed
            elif "resolution" in kl or "ifov" in kl:
                norm["spatial_resolution"] = parsed
            else:
                norm[k] = parsed

        elif category == "microwave":
            if "frequency" in kl or "ghz" in kl:
                if isinstance(parsed, dict) and "unit" not in parsed:
                    parsed["unit"] = "GHz"
                norm["central_frequency"] = parsed
            elif "bandwidth" in kl or "mhz" in kl:
                if isinstance(parsed, dict) and "unit" not in parsed:
                    parsed["unit"] = "MHz"
                norm["bandwidth"] = parsed
            elif "polaris" in kl:
                norm["polarisations"] = parsed
            elif "neΔt" in kl:
                norm["nedt"] = parsed
            elif "ifov" in kl or "pixel" in kl or "resolution" in kl:
                norm["spatial_resolution"] = parsed
            else:
                norm[k] = parsed

        elif category == "sar_active":
            if "mode" in kl:
                norm["operation_mode"] = parsed
            elif "resolution" in kl:
                norm["spatial_resolution"] = parsed
            elif "swath" in kl:
                norm["swath_width"] = parsed
            elif "field" in kl or "regard" in kl or "incidence" in kl:
                norm["field_of_regard"] = parsed
            elif "polari" in kl:
                norm["polarisation"] = parsed
            else:
                norm[k] = parsed

        elif category == "spectrometer_sounder":
            if "wave number" in kl or "cm-1" in kl:
                norm["wave_number_range"] = parsed
            elif "spectral resolution" in kl or "resolving" in kl:
                norm["spectral_resolution"] = parsed
            elif "channel" in kl and "number" in kl:
                norm["number_of_channels"] = parsed
            elif "snr" in kl or "neΔt" in kl:
                norm["snr_or_nedt"] = parsed
            else:
                norm[k] = parsed
        else:
            norm[k] = parsed

    return norm


# =============================================================================
# Explicit channel name mappings — sourced from official WMO, ESA, EUMETSAT,
# NASA, JAXA, CMA documentation and cross-referenced via web searches.
# =============================================================================
CHANNEL_MAPPINGS = {
    # --- Optical / Infrared Imagers ---
    "ABI": [f"C{i:02d}" for i in range(1, 17)],
    "VIIRS": [f"M{i}" for i in range(1, 17)] + ["DNB"] + [f"I{i}" for i in range(1, 6)],
    "MODIS": [f"B{i:02d}" for i in range(1, 37)],
    "AHI": [f"B{i:02d}" for i in range(1, 17)],
    "SEVIRI": [
        "VIS 0.6",
        "VIS 0.8",
        "NIR 1.6",
        "IR 3.9",
        "WV 6.2",
        "WV 7.3",
        "IR 8.7",
        "IR 9.7",
        "IR 10.8",
        "IR 12.0",
        "IR 13.4",
        "HRV",
    ],
    "FCI": [
        "VIS 0.4",
        "VIS 0.5",
        "VIS 0.6",
        "VIS 0.8",
        "VIS 0.9",
        "NIR 1.3",
        "NIR 1.6",
        "NIR 2.2",
        "IR 3.8",
        "IR 6.3",
        "IR 7.3",
        "IR 8.7",
        "IR 9.7",
        "IR 10.5",
        "IR 12.3",
        "IR 13.3",
    ],
    "SLSTR": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "F1", "F2"],
    "OLCI": [f"Oa{i:02d}" for i in range(1, 22)],
    "MSI": [
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B8A",
        "B09",
        "B10",
        "B11",
        "B12",
    ],
    "MSI (SENTINEL-2A)": [
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B8A",
        "B09",
        "B10",
        "B11",
        "B12",
    ],
    "MSI (SENTINEL-2B)": [
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B8A",
        "B09",
        "B10",
        "B11",
        "B12",
    ],
    "MSI (SENTINEL-2C)": [
        "B01",
        "B02",
        "B03",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B8A",
        "B09",
        "B10",
        "B11",
        "B12",
    ],
    "IMAGER (GOES 12-15)": ["B01", "B02", "B03", "B04", "B06"],
    "OCM (OCEANSAT-3)": [f"B{i:02d}" for i in range(1, 14)],
    # WMO OSCAR lists OLI channels by ascending wavelength, so Cirrus (1375nm, Landsat B9)
    # appears at position 5 — before SWIR1 (1650nm, B6) and SWIR2 (2215nm, B7).
    # Reference: https://space.oscar.wmo.int/instruments/view/oli
    #            https://www.usgs.gov/landsat-missions/landsat-8
    "OLI": ["B1", "B2", "B3", "B4", "B5", "B9", "B6", "B7", "B8"],
    "TIRS": ["B10", "B11"],
    "ASTER": [
        "B01",
        "B02",
        "B3N",
        "B3B",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B09",
        "B10",
        "B11",
        "B12",
        "B13",
        "B14",
    ],
    "MISR": ["Blue", "Green", "Red", "NIR"],
    "AVHRR/3": ["1", "2", "3A", "3B", "4", "5"],
    "AVHRR3": ["1", "2", "3A", "3B", "4", "5"],
    "AVHRR": ["1", "2", "3", "4", "5"],
    "AVHRR2": ["1", "2", "3", "4", "5"],
    "SGLI": [
        "VN1",
        "VN2",
        "VN3",
        "VN4",
        "VN5",
        "VN6",
        "VN7",
        "VN8",
        "VN9",
        "VN10",
        "VN11",
        "P1",
        "P2",
        "SW1",
        "SW2",
        "SW3",
        "SW4",
        "T1",
        "T2",
    ],
    "AGRI": [f"CH{i:02d}" for i in range(1, 16)],
    "MERSI-2": [f"CH{i:02d}" for i in range(1, 26)],
    "MERSI-3": [f"CH{i:02d}" for i in range(1, 26)],
    "MERSI-RM": [f"CH{i:02d}" for i in range(1, 11)],
    "GHI": [f"CH{i:02d}" for i in range(1, 13)],
    "METIMAGE": [f"CH{i:02d}" for i in range(1, 21)],
    "3MI": [f"CH{i:02d}" for i in range(1, 13)],
    "MSU-MR": [f"CH{i}" for i in range(1, 7)],
    "CERES": ["SW", "Total", "Window"],
    # --- Microwave Radiometers ---
    "ATMS": [f"CH{i:02d}" for i in range(1, 23)],
    "AMSR2": [
        "6.9V",
        "6.9H",
        "7.3V",
        "7.3H",
        "10.7V",
        "10.7H",
        "18.7V",
        "18.7H",
        "23.8V",
        "23.8H",
        "36.5V",
        "36.5H",
        "89.0V_A",
        "89.0H_A",
        "89.0V_B",
        "89.0H_B",
    ],
    "AMSU-A": [f"CH{i:02d}" for i in range(1, 16)],
    "MHS": [f"CH{i:02d}" for i in range(1, 6)],
    "MWHS-2": [f"CH{i:02d}" for i in range(1, 16)],
    "MWTS-2": [f"CH{i:02d}" for i in range(1, 14)],
    "MWTS-3": [f"CH{i:02d}" for i in range(1, 18)],
    "SSMIS": [f"CH{i:02d}" for i in range(1, 25)],
    "MTVZA-GY": [f"CH{i:02d}" for i in range(1, 30)],
    "COWVR": [f"CH{i:02d}" for i in range(1, 10)],
    "MWRI-1": [
        "10.65V",
        "10.65H",
        "18.7V",
        "18.7H",
        "23.8V",
        "23.8H",
        "36.5V",
        "36.5H",
        "89.0V",
        "89.0H",
    ],
    "MWRI-2": [f"CH{i:02d}" for i in range(1, 27)],
    "MWRI-RM": [f"CH{i:02d}" for i in range(1, 17)],
    "HSB": [f"CH{i:02d}" for i in range(1, 6)],
    "GMI (CORE)": [
        "10.65V",
        "10.65H",
        "18.7V",
        "18.7H",
        "23.8V",
        "36.64V",
        "36.64H",
        "89.0V",
        "89.0H",
        "166.0V",
        "166.0H",
        "183.31V_1",
        "183.31V_2",
    ],
    "TMS (TOMORROW)": [f"CH{i:02d}" for i in range(1, 13)],
    "MWI (WSF-M)": [
        "10.85V",
        "10.85H",
        "10.85_3",
        "10.85_4",
        "18.85V",
        "18.85H",
        "18.85_3",
        "18.85_4",
        "23.8V",
        "23.8H",
        "36.75V",
        "36.75H",
        "36.75_3",
        "36.75_4",
        "37.3V",
        "37.3H",
        "89.0V",
        "89.0H",
    ],
    "SOUNDER (INSAT)": [f"CH{i:02d}" for i in range(1, 20)],
    # --- Spectrometer / Sounders ---
    "CRIS": ["LWIR", "MWIR", "SWIR"],
    "IASI": ["Band 1", "Band 2", "Band 3"],
    "TROPOMI": [
        "UV-1",
        "UV-2",
        "UVIS-3",
        "UVIS-4",
        "NIR-5",
        "NIR-6",
        "SWIR-7",
        "SWIR-8",
    ],
    "HIRAS": ["LWIR", "MWIR", "SWIR"],
    "IKFS-2": ["LWIR", "MWIR", "SWIR"],
    "GIIRS": ["LWIR", "MWIR"],
    "GIIRS-2": ["LWIR", "MWIR"],
    "AIRS": ["LWIR", "MWIR", "SWIR"],
    "TANSO-FTS": ["Band 1", "Band 2", "Band 3", "Band 4"],
    "GOME-2": ["Band 1A", "Band 1B", "Band 2A", "Band 2B", "Band 3", "Band 4"],
    # --- SAR / Active ---
    "CSG-SAR": ["Spotlight-2A", "Spotlight-2B", "Stripmap", "PingPong", "ScanSAR"],
    "SAR-2000": ["Spotlight", "Stripmap", "ScanSAR huge region", "ScanSAR wide region"],
    "PALSAR-2": ["Spotlight", "Stripmap", "ScanSAR"],
    "SAR_RCM": [
        "Low Noise",
        "Low Resolution",
        "Medium Resolution",
        "High Resolution",
        "Very High Resolution",
        "Ship Detection",
        "Spotlight",
        "Extra Low Noise",
        "Quad-Pol",
    ],
    "SAR-C (SENTINEL-1)": [
        "Stripmap",
        "Interferometric Wide swath",
        "Extra Wide swath",
        "Wave",
    ],
    "SAR (RADARSAT-1)": [
        "Standard",
        "Wide",
        "Fine",
        "ScanSAR Narrow",
        "ScanSAR Wide",
        "Extended High",
        "Extended Low",
    ],
}


def assign_channel_names(instrument_acronym, norm_channels):
    acronym = instrument_acronym if instrument_acronym else ""
    acronym_upper = acronym.upper()

    for i, ch in enumerate(norm_channels):
        name = None

        # Check if original data gave it a band name via its column
        for k, v in ch.items():
            if k.lower() in ["band id", "channel", "band"]:
                if isinstance(v, str):
                    name = v.strip()
                elif isinstance(v, dict) and "value" in v:
                    val = v["value"]
                    name = (
                        str(int(val))
                        if isinstance(val, float) and val.is_integer()
                        else str(val)
                    )
            elif k.lower() == "channel number":
                val = v
                if isinstance(val, dict) and "value" in val:
                    name = f"CH{int(val['value']):02d}"
                elif isinstance(val, (int, float)):
                    name = f"CH{int(val):02d}"
                else:
                    name = f"CH{val}"

        # Override with explicit mapping if available (case-insensitive lookup)
        mapping_key = None
        if acronym_upper in {k.upper() for k in CHANNEL_MAPPINGS}:
            for k in CHANNEL_MAPPINGS:
                if k.upper() == acronym_upper:
                    mapping_key = k
                    break
        if mapping_key and i < len(CHANNEL_MAPPINGS[mapping_key]):
            name = CHANNEL_MAPPINGS[mapping_key][i]

        if not name:
            name = f"Band_{i + 1:02d}"

        # Place channel_name at the top of the dict
        new_ch = {"channel_name": name}
        for k, v in ch.items():
            if k != "channel_name":
                new_ch[k] = v
        norm_channels[i] = new_ch

    return norm_channels


def flatten_parsed_value(val, to_meters=False):
    if val is None:
        return None

    if isinstance(val, dict):
        unit = val.get("unit")
        res = None

        if "value" in val:
            res = float(val["value"])
        elif "min" in val:
            res = float(val["min"])
        elif "x" in val and "y" in val:
            res = [float(val["x"]), float(val["y"])]
        elif "x" in val:
            res = float(val["x"])
        else:
            return None

        if to_meters and isinstance(unit, str):
            ul = unit.lower()
            multiplier = 1.0
            if "km" in ul:
                multiplier = 1000.0
            elif "cm" in ul:
                multiplier = 1.0 / 100.0
            elif "mm" in ul:
                multiplier = 1.0 / 1000.0

            if isinstance(res, list):
                res = [r * multiplier for r in res]
            else:
                res *= multiplier

        return res

    if isinstance(val, (int, float)):
        return float(val)

    return val


def finalize_channel(ch, category):
    out = dict(ch)

    # Extract unit once
    for k in ["central_wavelength", "central_frequency", "wave_number_range"]:
        if k in ch and isinstance(ch[k], dict):
            out["unit"] = ch[k].get("unit")
            break

    # Flatten fields depending on schema
    if category == "optical_infrared":
        out["central_wavelength"] = flatten_parsed_value(ch.get("central_wavelength"))
        out["bandwidth"] = flatten_parsed_value(ch.get("bandwidth"))
        out["spatial_resolution"] = flatten_parsed_value(
            ch.get("spatial_resolution"), to_meters=True
        )
        out["snr_low"] = flatten_parsed_value(ch.get("snr_low"))
        out["snr_high"] = flatten_parsed_value(ch.get("snr_high"))
        out["snr_or_nedt"] = flatten_parsed_value(ch.get("snr_or_nedt"))

    elif category == "microwave":
        out["central_frequency"] = flatten_parsed_value(ch.get("central_frequency"))
        out["bandwidth"] = flatten_parsed_value(ch.get("bandwidth"))
        out["spatial_resolution"] = flatten_parsed_value(
            ch.get("spatial_resolution"), to_meters=True
        )
        out["nedt"] = flatten_parsed_value(ch.get("nedt"))

    elif category == "sar_active":
        out["spatial_resolution"] = flatten_parsed_value(
            ch.get("spatial_resolution"), to_meters=True
        )
        out["swath_width"] = flatten_parsed_value(ch.get("swath_width"), to_meters=True)
        out["field_of_regard"] = flatten_parsed_value(ch.get("field_of_regard"))

    elif category == "spectrometer_sounder":
        wn = ch.get("wave_number_range", {})
        if isinstance(wn, dict):
            out["wave_number_min"] = wn.get("min")
            out["wave_number_max"] = wn.get("max")

        out["spectral_resolution"] = flatten_parsed_value(ch.get("spectral_resolution"))
        out["number_of_channels"] = flatten_parsed_value(ch.get("number_of_channels"))
        out["snr_or_nedt"] = flatten_parsed_value(ch.get("snr_or_nedt"))

    return out


def main():
    parser = argparse.ArgumentParser(
        description="Normalize WMO OSCAR JSON instruments and map genuine channel names."
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        type=str,
        default="wmo_oscar_instruments",
        help="Path to the directory containing scraped JSON instrument files (default: wmo_oscar_instruments).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="wmo_oscar_instruments_normalized",
        help="Path to the output directory to write processed files (default: wmo_oscar_instruments_normalized). Use the same as input if you want to overwrite.",
    )
    args = parser.parse_args()

    # Expand relative paths
    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.isdir(input_dir):
        print(f"Error: Input directory {input_dir} does not exist.")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    files = glob.glob(os.path.join(input_dir, "*.json"))
    if not files:
        print(f"No JSON files found in {input_dir}")
        sys.exit(0)

    count = 0
    for f in files:
        try:
            with open(f, "r") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            print(f"Skipping {os.path.basename(f)}: invalid JSON")
            continue

        cols = data.get("original_columns") or data.get("columns", [])
        if not cols and data.get("channels"):
            cols = list(data["channels"][0].keys())

        category = data.get("schema_type")
        if not category or category == "unknown":
            category = classify_instrument(cols)
        acronym = data.get("instrument_acronym", "").strip()

        norm_channels = []
        for ch in data.get("channels", []):
            norm = normalize_keys(ch, category)
            norm = finalize_channel(norm, category)
            norm_channels.append(norm)

        # Assign specific channel names
        norm_channels = assign_channel_names(acronym, norm_channels)

        normalized_data = {
            "instrument_id": data.get("instrument_id"),
            "instrument_acronym": acronym,
            "instrument_fullname": data.get("instrument_fullname"),
            "url": data.get("url"),
            "schema_type": category,
            "original_columns": cols,
            "channels": norm_channels,
        }

        out_path = os.path.join(output_dir, os.path.basename(f))
        with open(out_path, "w") as out_f:
            json.dump(normalized_data, out_f, indent=2, ensure_ascii=False)

        count += 1

    print(f"Processed {count} JSON files. Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
