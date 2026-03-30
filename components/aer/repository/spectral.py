import csv
import json
from functools import lru_cache
from pathlib import Path

from aer.spectral import (
    ChannelType,
    Instrument,
    Satellite,
    create_channel,
)
from aer.repository.core import AerSpectralRepository


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
                if row["Acronym"].strip() == acronym:
                    sat_data = row
                    break

        if not sat_data:
            raise KeyError(f"Satellite with acronym '{acronym}' not found")

        payload = []
        if self.instruments_csv.exists():
            with open(self.instruments_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sats = [
                        s.strip()
                        for s in row.get("Satellites", "").split("\n")
                        if s.strip()
                    ]
                    if acronym in sats:
                        inst_acronym = row["Acronym"].strip()
                        try:
                            inst = self.get_instrument(
                                inst_acronym, satellite_acronym=acronym
                            )
                            payload.append(inst)
                        except Exception:
                            pass

        orbit = sat_data.get("Orbit", "").strip() or None
        alt_str = sat_data.get("Altitude", "").replace("km", "").strip()
        altitude_km = None
        if alt_str and alt_str != "TBD":
            try:
                altitude_km = float(alt_str)
            except ValueError:
                pass

        status = sat_data.get("Sat status", "").strip() or None
        agencies_str = sat_data.get("Agencies", "")
        agencies = [a.strip() for a in agencies_str.split("\n") if a.strip()] or None

        return Satellite(
            acronym=acronym,
            payload=payload,
            orbit=orbit,
            altitude_km=altitude_km,
            status=status,
            agencies=agencies,
        )

    @lru_cache(maxsize=64)
    def get_instrument(
        self, acronym: str, satellite_acronym: str | None = None
    ) -> Instrument:
        """
        Retrieve an instrument by its acronym (WMO Oscar format).
        If satellite_acronym is provided, it will be used to narrow down the search for the instrument's JSON file.

        Args:
            acronym: The unique acronym identifier for the instrument.
            satellite_acronym: Optional acronym of the satellite to which the instrument belongs, used for disambiguation when multiple instruments have similar acronyms.
        Returns:
            An Instrument object corresponding to the provided acronym.
        Raises:
            An exception if no instrument with the given acronym is found.
        """
        acronym = acronym.strip()

        if satellite_acronym is None:
            sat_acro = "UNKNOWN"
            if self.instruments_csv.exists():
                with open(self.instruments_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["Acronym"].strip() == acronym:
                            sats = [
                                s.strip()
                                for s in row.get("Satellites", "").split("\n")
                                if s.strip()
                            ]
                            if sats:
                                sat_acro = sats[0]
                            break
            satellite_acronym = sat_acro

        import re

        def slugify(text: str) -> str:
            t = text.lower().strip()
            t = re.sub(r"[^\w\s-]", "", t)
            t = re.sub(r"[\s_]+", "_", t)
            return t.strip("_")

        json_path = self.instruments_dir / f"{slugify(acronym)}.json"

        if not json_path.exists():
            json_path = None
            if self.instruments_dir.exists():
                for p in self.instruments_dir.glob("*.json"):
                    # Loose check
                    if slugify(acronym) in p.stem.lower() or p.stem.lower() in slugify(
                        acronym
                    ):
                        try:
                            with open(p, "r", encoding="utf-8") as jf:
                                data = json.load(jf)
                            if (
                                data.get("instrument_acronym", "").strip().lower()
                                == acronym.lower()
                            ):
                                json_path = p
                                break
                        except Exception:
                            pass

            if not json_path:
                raise KeyError(f"Instrument with acronym '{acronym}' not found")

        with open(json_path, "r", encoding="utf-8") as jf:
            data = json.load(jf)

        real_acronym = data.get("instrument_acronym", "").strip()
        if real_acronym.lower() != acronym.lower():
            raise KeyError(f"Instrument with acronym '{acronym}' not found")

        schema_type = data.get("schema_type", "")

        channels = []
        for ch in data.get("channels", []):
            channels.append(create_channel(schema_type, ch, real_acronym))

        return Instrument(
            satellite_acronym=str(satellite_acronym),
            acronym=real_acronym,
            channels=channels,
        )

    def get_channel(
        self,
        acronym: str,
        channel_name: str | None = None,
        channel_number: int | None = None,
    ) -> ChannelType:
        """
        Retrieve a channel by its instrument acronym and channel name or number.
        Args:
            acronym: The unique acronym identifier for the channel,
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

        inst = self.get_instrument(acronym)

        if channel_name is not None:
            for ch in inst.channels:
                if ch.channel_name.strip().lower() == channel_name.strip().lower():
                    return ch
            raise KeyError(
                f"Channel name '{channel_name}' not found in instrument '{acronym}'."
            )
        if channel_number is not None:
            if 1 <= channel_number <= len(inst.channels):
                return inst.channels[channel_number - 1]
            else:
                raise KeyError(
                    f"Channel number {channel_number} is out of range for instrument '{acronym}'."
                )

        raise KeyError(f"Channel '{acronym}' not found.")
