import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path

from aer.repository.models import (
    ChannelType,
    Instrument,
    Satellite,
)


class AerSpectralRepository(ABC):
    """Abstract Base Class defining the Aer data access interface.

    This repository orchestrates persistence and retrieval across several
    conceptual spaces based on the Aer Entity-Relationship schema.
    """

    # ==========================================
    #  Satellites, Instruments & Channels methods
    # ==========================================

    @abstractmethod
    def get_satellite(self, acronym: str) -> Satellite:
        """Retrieve a satellite by its acronym.

        Args:
            acronym: The unique acronym identifier for the satellite.
        Returns:
            A Satellite object corresponding to the provided acronym.
        Raises:
            An exception if no satellite with the given acronym is found.
        """
        pass

    @abstractmethod
    def get_instrument(self, acronym: str) -> Instrument:
        """Retrieve an instrument by its acronym.

        Args:
            acronym: The unique acronym identifier for the instrument.
        Returns:
            An Instrument object corresponding to the provided acronym.
        Raises:
            An exception if no instrument with the given acronym is found.
        """
        pass

    @abstractmethod
    def get_channel(self, acronym: str) -> ChannelType:
        """Retrieve a channel by its acronym.

        Args:
            acronym: The unique acronym identifier for the channel.
        Returns:
            A ChannelType object corresponding to the provided acronym.
        Raises:
            An exception if no channel with the given acronym is found.
        """
        pass


class AerLocalSpectralRepository(AerSpectralRepository):
    """Implementation of AerRepository for local spectral data."""

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            self.data_dir = Path(__file__).parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.instruments_dir = self.data_dir / "wmo_oscar_instruments"
        self.instruments_csv = self.data_dir / "wmo_oscar_instruments.csv"
        self.satellites_csv = self.data_dir / "wmo_oscar_satellites.csv"

    def get_satellite(self, acronym: str) -> Satellite:
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
            raise KeyError(f"Satellite '{acronym}' not found.")

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

    def get_instrument(
        self, acronym: str, satellite_acronym: str | None = None
    ) -> Instrument:
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
                raise KeyError(f"Instrument '{acronym}' not found.")

        with open(json_path, "r", encoding="utf-8") as jf:
            data = json.load(jf)

        real_acronym = data.get("instrument_acronym", "").strip()
        if real_acronym.lower() != acronym.lower():
            raise KeyError(f"Instrument '{acronym}' not found.")

        schema_type = data.get("schema_type", "")
        from aer.repository.models import create_channel

        channels = []
        for ch in data.get("channels", []):
            channels.append(create_channel(schema_type, ch, real_acronym))

        return Instrument(
            satellite_acronym=str(satellite_acronym),
            acronym=real_acronym,
            channels=channels,
        )

    def get_channel(self, acronym: str) -> ChannelType:
        if "_" not in acronym:
            raise KeyError(
                f"Channel acronym must be INSTRUMENT_CHANNEL, got '{acronym}'"
            )
        inst_acro, ch_name = acronym.split("_", 1)

        inst = self.get_instrument(inst_acro)
        for ch in inst.channels:
            if ch.channel_name == ch_name:
                return ch

        raise KeyError(f"Channel '{acronym}' not found.")
