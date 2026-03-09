import os
import yaml  # type: ignore
from pathlib import Path
from structlog import get_logger

from aer.spectral.core import Instrument, Satellite, Band, BandType, Channel, Product

logger = get_logger()


def load_config_file(filepath: str) -> None:
    """Load a YAML configuration file to populate spectral definitions."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to read spectral config file '{filepath}': {e}")
        return

    if not data:
        return

    try:
        for inst in data.get("instruments", []):
            Instrument.register(name=inst["name"], url=inst.get("url"))

        for sat in data.get("satellites", []):
            Satellite.register(name=sat["name"], url=sat.get("url"))

        for prod in data.get("products", []):
            channels = []
            instrument_name = prod.get("instrument")
            if not instrument_name:
                logger.error(
                    f"Product '{prod.get('name')}' is missing required field 'instrument'. Skipping."
                )
                continue

            try:
                instrument = Instrument.get(instrument_name)
            except KeyError:
                logger.error(
                    f"Product '{prod.get('name')}' refers to unregistered instrument '{instrument_name}'. Skipping."
                )
                continue

            for ch_data in prod.get("channels", []):
                try:
                    band_data = ch_data["band"]
                    band_type_name = band_data["type"]
                    band_type = BandType.get(band_type_name)

                    band = Band(
                        name=str(band_data["name"]),
                        band_type=band_type,
                        central_wavelength=float(band_data["central_wavelength"]),
                        bandwidth=float(band_data["bandwidth"]),
                    )

                    channel = Channel(
                        c_id=str(ch_data["c_id"]),
                        instrument=instrument,
                        band=band,
                        resolution=int(ch_data["resolution"]),
                    )
                    channels.append(channel)
                except (KeyError, ValueError, TypeError) as e:
                    logger.error(
                        f"Malformed channel data in product '{prod.get('name')}': {e}. Skipping channel."
                    )
                    continue

            supported_satellites_names = prod.get("supported_satellites", [])
            valid_satellites = []
            for sat_name in supported_satellites_names:
                try:
                    valid_satellites.append(Satellite.get(sat_name))
                except KeyError:
                    logger.warning(
                        f"Product '{prod.get('name')}' refers to unknown satellite '{sat_name}'."
                    )

            # This will automatically register it in the Product._registry
            Product(
                name=prod["name"],
                instrument=instrument,
                supported_satellites=frozenset(valid_satellites),
                channels=tuple(channels),
            )
    except Exception as e:
        logger.error(f"Unexpected error parsing spectral config '{filepath}': {e}")


def load_defaults() -> None:
    """Load the default built-in spectral configuration."""
    default_path = Path(__file__).parent / "data" / "default_spectral.yaml"
    if default_path.exists():
        load_config_file(str(default_path))


def auto_load() -> None:
    """Load default configs, and any user-provided configs via AER_SPECTRAL_CONFIG_PATH."""
    load_defaults()

    config_path = os.environ.get("AER_SPECTRAL_CONFIG_PATH")
    if not config_path:
        return

    path = Path(config_path)
    if not path.exists():
        logger.warning(f"AER_SPECTRAL_CONFIG_PATH '{config_path}' does not exist.")
        return

    if path.is_dir():
        # Scan for yaml/yml files non-recursively by default
        for ext in ["*.yaml", "*.yml"]:
            for file in path.glob(ext):
                load_config_file(str(file))
    else:
        load_config_file(config_path)


# Automatically load definitions when this module is imported.
# auto_load() is deferred to __init__.py to prevent circular imports if necessary,
# but it's safe to call here or in __init__.py
