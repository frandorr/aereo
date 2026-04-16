"""Tests for the data component normalize_instruments module.

Covers parse_value, classify_instrument, normalize_keys,
assign_channel_names, flatten_parsed_value, and finalize_channel.
"""

from aer.data.normalize_instruments import (
    parse_value,
    classify_instrument,
    normalize_keys,
    assign_channel_names,
    flatten_parsed_value,
    finalize_channel,
)


# ==========================================
#  parse_value tests
# ==========================================


def test_parse_single_value_with_unit():
    result = parse_value("0.64 µm")
    assert result == {"value": 0.64, "unit": "µm"}


def test_parse_single_value_no_unit():
    result = parse_value("42")
    assert result == {"value": 42, "unit": None}


def test_parse_float_value():
    result = parse_value("3.14")
    assert result == {"value": 3.14, "unit": None}


def test_parse_range_value():
    result = parse_value("645 - 2760 cm-1")
    assert result == {"min": 645.0, "max": 2760.0, "unit": "cm-1"}


def test_parse_dimension_value():
    result = parse_value("5.0 x 20.0 km")
    assert result == {"x": 5.0, "y": 20.0, "unit": "km"}


def test_parse_scientific_notation():
    result = parse_value("1.5e-3 m")
    assert result == {"value": 0.0015, "unit": "m"}


def test_parse_non_string_passthrough():
    assert parse_value(42) == 42
    assert parse_value(None) is None
    assert parse_value(["a", "b"]) == ["a", "b"]


def test_parse_plain_string():
    assert parse_value("VH") == "VH"
    assert parse_value("IW") == "IW"


# ==========================================
#  classify_instrument tests
# ==========================================


def test_classify_optical():
    cols = ["Central wavelength", "Bandwidth", "SNR low"]
    assert classify_instrument(cols) == "optical_infrared"


def test_classify_optical_by_wavelength():
    cols = ["Wavelength", "Spectral interval"]
    assert classify_instrument(cols) == "optical_infrared"


def test_classify_microwave():
    cols = ["Frequency", "GHz", "Quasi-polarisation"]
    assert classify_instrument(cols) == "microwave"


def test_classify_sar():
    cols = ["Operation mode", "Swath", "Incidence angle"]
    assert classify_instrument(cols) == "sar_active"


def test_classify_spectrometer_sounder():
    cols = ["Wave number", "Spectral resolution", "Number of channels"]
    assert classify_instrument(cols) == "spectrometer_sounder"


def test_classify_unknown():
    cols = ["Some random column"]
    assert classify_instrument(cols) == "unknown"


# ==========================================
#  normalize_keys tests
# ==========================================


def test_normalize_optical_keys():
    channel = {
        "Central wavelength": "0.64 µm",
        "Bandwidth": "0.02 µm",
        "SNR low": "100",
    }
    result = normalize_keys(channel, "optical_infrared")
    assert "central_wavelength" in result
    assert "bandwidth" in result
    assert "snr_low" in result


def test_normalize_microwave_keys():
    channel = {
        "Frequency": "6.925 GHz",
        "Bandwidth": "350 MHz",
        "Quasi-polarisation": "VH",
    }
    result = normalize_keys(channel, "microwave")
    assert "central_frequency" in result
    assert "bandwidth" in result
    assert "polarisations" in result


def test_normalize_sar_keys():
    channel = {
        "Operation mode": "IW",
        "Resolution": "5.0 x 20.0 m",
        "Swath width": "250 km",
    }
    result = normalize_keys(channel, "sar_active")
    assert "operation_mode" in result
    assert "spatial_resolution" in result
    assert "swath_width" in result


def test_normalize_spectrometer_keys():
    channel = {
        "Wave number range": "645 - 2760 cm-1",
        "Spectral resolution": "0.5 cm-1",
        "Number of channels": "8461",
    }
    result = normalize_keys(channel, "spectrometer_sounder")
    assert "wave_number_range" in result
    assert "spectral_resolution" in result
    assert "number_of_channels" in result


# ==========================================
#  assign_channel_names tests
# ==========================================


def test_assign_channel_names_known_instrument():
    channels = [{}, {}, {}]
    result = assign_channel_names("ABI", channels)
    assert result[0]["channel_name"] == "C01"
    assert result[1]["channel_name"] == "C02"
    assert result[2]["channel_name"] == "C03"


def test_assign_channel_names_viirs():
    channels = [{}] * 5
    result = assign_channel_names("VIIRS", channels)
    assert result[0]["channel_name"] == "M1"
    assert result[1]["channel_name"] == "M2"


def test_assign_channel_names_unknown_instrument():
    channels = [{}, {}]
    result = assign_channel_names("UNKNOWN", channels)
    assert result[0]["channel_name"] == "Band_01"
    assert result[1]["channel_name"] == "Band_02"


def test_assign_channel_names_preserves_existing():
    channels = [{"band": "Custom"}]
    result = assign_channel_names("UNKNOWN", channels)
    assert result[0]["channel_name"] == "Custom"


def test_assign_channel_names_case_insensitive():
    channels = [{}]
    result = assign_channel_names("abi", channels)
    assert result[0]["channel_name"] == "C01"


# ==========================================
#  flatten_parsed_value tests
# ==========================================


def test_flatten_value_dict():
    assert flatten_parsed_value({"value": 42.0, "unit": "m"}) == 42.0


def test_flatten_range_dict():
    assert flatten_parsed_value({"min": 1.0, "max": 10.0, "unit": "m"}) == 1.0


def test_flatten_dim_dict():
    assert flatten_parsed_value({"x": 5.0, "y": 20.0, "unit": "m"}) == [5.0, 20.0]


def test_flatten_to_meters_km():
    assert (
        flatten_parsed_value({"value": 250.0, "unit": "km"}, to_meters=True) == 250000.0
    )


def test_flatten_to_meters_cm():
    assert flatten_parsed_value({"value": 100.0, "unit": "cm"}, to_meters=True) == 1.0


def test_flatten_to_meters_mm():
    assert flatten_parsed_value({"value": 500.0, "unit": "mm"}, to_meters=True) == 0.5


def test_flatten_to_meters_list():
    result = flatten_parsed_value({"x": 5.0, "y": 20.0, "unit": "km"}, to_meters=True)
    assert result == [5000.0, 20000.0]


def test_flatten_plain_number():
    assert flatten_parsed_value(42) == 42.0


def test_flatten_none():
    assert flatten_parsed_value(None) is None


# ==========================================
#  finalize_channel tests
# ==========================================


def test_finalize_optical_channel():
    ch = {
        "channel_name": "B1",
        "central_wavelength": {"value": 0.64, "unit": "µm"},
        "bandwidth": {"value": 0.02, "unit": "µm"},
        "spatial_resolution": {"value": 371.0, "unit": "m"},
        "snr_low": "100",
    }
    result = finalize_channel(ch, "optical_infrared")
    assert result["central_wavelength"] == 0.64
    assert result["bandwidth"] == 0.02
    assert result["spatial_resolution"] == 371.0
    assert result["snr_low"] == "100"


def test_finalize_microwave_channel():
    ch = {
        "channel_name": "B1",
        "central_frequency": {"value": 6.925, "unit": "GHz"},
        "bandwidth": {"value": 350.0, "unit": "MHz"},
        "spatial_resolution": {"value": 62.0, "unit": "km"},
    }
    result = finalize_channel(ch, "microwave")
    assert result["central_frequency"] == 6.925
    assert result["spatial_resolution"] == 62000.0  # km -> m


def test_finalize_sar_channel():
    ch = {
        "channel_name": "IW",
        "spatial_resolution": {"x": 5.0, "y": 20.0, "unit": "m"},
        "swath_width": {"value": 250.0, "unit": "km"},
    }
    result = finalize_channel(ch, "sar_active")
    assert result["spatial_resolution"] == [5.0, 20.0]
    assert result["swath_width"] == 250000.0


def test_finalize_spectrometer_channel():
    ch = {
        "channel_name": "Band 1",
        "wave_number_range": {"min": 645.0, "max": 2760.0, "unit": "cm-1"},
        "spectral_resolution": {"value": 0.5, "unit": "cm-1"},
        "number_of_channels": {"value": 8461, "unit": None},
    }
    result = finalize_channel(ch, "spectrometer_sounder")
    assert result["wave_number_min"] == 645.0
    assert result["wave_number_max"] == 2760.0
    assert result["spectral_resolution"] == 0.5
    assert result["number_of_channels"] == 8461.0
