"""Local file-based implementation of AerSpectralRepository.

Reads satellite, instrument, and channel data from CSV and JSON files
extracted from the WMO OSCAR database, providing cached retrieval
by acronym with disambiguation support.
"""

import csv
import json
from functools import lru_cache
from pathlib import Path

from aer.repository.core import AerSpectralRepository
from aer.spectral import (
    ChannelType,
    Instrument,
    Satellite,
    create_channel,
)


class AerLocalSpectralRepository(AerSpectralRepository):
    """Implementation of AerRepository for local spectral data.
    It assumes a specific directory structure and file formats for storing satellite,
    instrument, and channel data. The repository reads from
    CSV files for satellite and instrument metadata, and JSON.
    CSV files were extracted from the WMO OSCAR database, while JSON files for instruments are expected
    to follow a specific schema that includes the instrument acronym and its channels.
    The repository provides methods to retrieve satellite,
    instrument, and channel information based on their acronyms,
    """

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            self.data_dir = Path(__file__).parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.instruments_dir = self.data_dir / "wmo_oscar_instruments"
        self.instruments_csv = self.data_dir / "wmo_oscar_instruments.csv"
        self.satellites_csv = self.data_dir / "wmo_oscar_satellites.csv"

    @lru_cache(maxsize=64)
    def get_satellite(self, acronym: str) -> Satellite:
        """
        Retrieve a satellite by its acronym (WMO Oscar format).

        Args:
            acronym: The unique acronym identifier for the satellite.
        Returns:
            A Satellite object corresponding to the provided acronym.
        Raises:
            An exception if no satellite with the given acronym is found.
        """
        acronym = acronym.strip()

        sat_data = None

        if not self.satellites_csv.exists():
            raise FileNotFoundError(
                f"Satellites CSV not found at {self.satellites_csv}"
            )

        with open(self.satellites_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row["acronym"].strip() == acronym) or (
                    row["slug"].strip() == acronym
                ):
                    sat_data = row
                    break

        if not sat_data:
            raise KeyError(f"Satellite with acronym '{acronym}' not found")

        payload = []
        for instrument_slug in sat_data["payload"]:
            try:
                instrument = self.get_instrument(instrument_slug)
                payload.append(instrument)
            except Exception:
                pass

        # metadata = all key values from sat_data
        # except for acronym and apyload
        metadata = {
            k: v.strip()
            for k, v in sat_data.items()
            if k not in ["acronym", "payload"] and v.strip()
        }

        return Satellite(acronym=acronym, payload=payload, metadata=metadata)

    @lru_cache(maxsize=64)
    def get_instrument(self, acronym: str) -> Instrument:
        """
        Retrieve an instrument by its acronym/slug (WMO Oscar format).

        Args:
            acronym: The unique acronym identifier for the instrument.
                Check the WMO OSCAR database acronym format.
                Or components/data/wmo_oscar_instruments.csv for the list of available instruments and their acronym/slugs.
        Returns:
            An Instrument object corresponding to the provided acronym.
        Raises:
            An exception if no instrument with the given acronym is found.
        """

        json_path = self.instruments_dir / f"{acronym}.json"
        if not json_path.exists():
            if self.instruments_csv.exists():
                with open(self.instruments_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["name"].strip() == acronym:
                            slug = row["slug"].strip()
                            json_path = self.instruments_dir / f"{slug}.json"
                            break

        if not json_path.exists():
            raise KeyError(f"Instrument with acronym '{acronym}' not found")

        with open(json_path, "r", encoding="utf-8") as jf:
            data = json.load(jf)

        schema_type = data.get("schema_type", "")

        acronym = data.get("instrument_acronym", "").strip()
        # metadata is all key values from data except for instrument_acronym
        metadata = {
            k: v.strip()
            for k, v in data.items()
            if k not in ["instrument_acronym"] and isinstance(v, str) and v.strip()
        }

        channels = []
        for ch in data.get("channels", []):
            channels.append(create_channel(schema_type, ch))

        return Instrument(
            acronym=acronym,
            channels=channels,
            metadata=metadata,
        )

    def get_channel(
        self,
        instrument: Instrument,
        channel_name: str | None = None,
        channel_number: int | None = None,
    ) -> ChannelType:
        """
        Retrieve a channel by its instrument and channel name or number.
        Args:
            instrument: The instrument the channels belongs to.,
            channel_name: Optional name of the channel to retrieve.
                        If provided, it will be used to find by channel name within the instrument.
            channel_number: Optional number of the channel to retrieve (from 1 to N).
                        If provided, it will be used to find by channel position within the instrument.
        """
        if channel_name is None and channel_number is None:
            raise ValueError("Either channel_name or channel_number must be provided.")
        if channel_name is not None and channel_number is not None:
            raise ValueError(
                "Only one of channel_name or channel_number should be provided."
            )

        if channel_name is not None:
            for ch in instrument.channels:
                if ch.channel_name.strip().lower() == channel_name.strip().lower():
                    return ch
            raise KeyError(
                f"Channel name '{channel_name}' not found in instrument {instrument.acronym}."
            )
        if channel_number is not None:
            if 1 <= channel_number <= len(instrument.channels):
                return instrument.channels[channel_number - 1]
            else:
                raise KeyError(
                    f"Channel number {channel_number} is out of range for instrument {instrument.acronym}."
                )

        raise KeyError("Channel not found ")
