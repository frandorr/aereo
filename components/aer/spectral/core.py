from typing import FrozenSet, ClassVar, Dict, Optional

import attrs


@attrs.frozen
class Instrument:
    """An extensible registry of instruments.

    Core instruments (ABI, VIIRS, MODIS, etc.) are pre-registered at module
    load time.  Plugins can add new instruments via ``register()`` and should
    capture the return value for type-safe usage::

        OLI = Instrument.register("OLI", "https://...")
        channel = Channel(c_id="B1", instrument=OLI, ...)
    """

    name: str
    url: Optional[str] = None

    _registry: ClassVar[Dict[str, "Instrument"]] = {}

    # explicit type stub for mypy
    ABI: ClassVar["Instrument"]
    VIIRS: ClassVar["Instrument"]
    MODIS: ClassVar["Instrument"]
    OLCI: ClassVar["Instrument"]
    SLSTR: ClassVar["Instrument"]

    def __repr__(self) -> str:
        return f"Instrument.{self.name.replace('-', '_').upper()}"

    @classmethod
    def register(cls, name: str, url: Optional[str] = None) -> "Instrument":
        """Register a new instrument or return an existing one.

        Plugin authors should capture the return value for full type safety::

            OLI = Instrument.register("OLI")
            # mypy knows OLI is Instrument — use it directly.

        The instance is also attached as a class attribute (e.g.
        ``Instrument.OLI``) for interactive convenience, but this is
        invisible to static type checkers for dynamically-added entries.
        """
        if name in cls._registry:
            return cls._registry[name]

        instance = cls(name=name, url=url)
        cls._registry[name] = instance

        setattr(cls, name.replace("-", "_").upper(), instance)
        return instance

    @classmethod
    def get(cls, name: str) -> "Instrument":
        """Retrieve a registered instrument by name."""
        if name not in cls._registry:
            raise KeyError(
                f"Instrument '{name}' is not registered. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["Instrument", ...]:
        """Return all registered instruments."""
        return tuple(cls._registry.values())


Instrument.register("ABI", "https://space.oscar.wmo.int/instruments/view/abi")
Instrument.register("VIIRS", "https://space.oscar.wmo.int/instruments/view/viirs")
Instrument.register("MODIS", "https://space.oscar.wmo.int/instruments/view/modis")
Instrument.register("OLCI", "https://space.oscar.wmo.int/instruments/view/olci")
Instrument.register("SLSTR", "https://space.oscar.wmo.int/instruments/view/slstr")


@attrs.frozen
class Satellite:
    """An extensible registry of satellites.

    Core satellites are pre-registered at module load time.  Plugins can
    add new satellites via ``register()`` and should capture the return
    value for type-safe usage::

        LANDSAT_8 = Satellite.register("LANDSAT_8", "https://...")
    """

    name: str
    url: Optional[str] = None

    _registry: ClassVar[Dict[str, "Satellite"]] = {}

    # explicit type stub for mypy
    TERRA: ClassVar["Satellite"]
    AQUA: ClassVar["Satellite"]
    NOAA_20: ClassVar["Satellite"]
    NOAA_21: ClassVar["Satellite"]
    SNPP: ClassVar["Satellite"]
    GOES_16: ClassVar["Satellite"]
    GOES_18: ClassVar["Satellite"]
    GOES_19: ClassVar["Satellite"]
    SENTINEL_3A: ClassVar["Satellite"]
    SENTINEL_3B: ClassVar["Satellite"]

    def __repr__(self) -> str:
        return f"Satellite.{self.name.replace('-', '_').upper()}"

    @classmethod
    def register(cls, name: str, url: Optional[str] = None) -> "Satellite":
        """Register a new satellite or return an existing one.

        Plugin authors should capture the return value for full type safety::

            LANDSAT_8 = Satellite.register("LANDSAT_8")
        """
        if name in cls._registry:
            return cls._registry[name]

        instance = cls(name=name, url=url)
        cls._registry[name] = instance

        setattr(cls, name.replace("-", "_").upper(), instance)
        return instance

    @classmethod
    def get(cls, name: str) -> "Satellite":
        """Retrieve a registered satellite by name."""
        if name not in cls._registry:
            raise KeyError(
                f"Satellite '{name}' is not registered. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["Satellite", ...]:
        """Return all registered satellites."""
        return tuple(cls._registry.values())


Satellite.register("TERRA", "https://space.oscar.wmo.int/satellites/view/terra")
Satellite.register("AQUA", "https://space.oscar.wmo.int/satellites/view/aqua")
Satellite.register("NOAA-20", "https://space.oscar.wmo.int/satellites/view/noaa-20")
Satellite.register("NOAA-21", "https://space.oscar.wmo.int/satellites/view/noaa-21")
Satellite.register("SNPP", "https://space.oscar.wmo.int/satellites/view/snpp")
Satellite.register("GOES-16", "https://space.oscar.wmo.int/satellites/view/goes-16")
Satellite.register("GOES-18", "https://space.oscar.wmo.int/satellites/view/goes-18")
Satellite.register("GOES-19", "https://space.oscar.wmo.int/satellites/view/goes-19")
Satellite.register(
    "SENTINEL-3A", "https://space.oscar.wmo.int/satellites/view/sentinel-3a"
)
Satellite.register(
    "SENTINEL-3B", "https://space.oscar.wmo.int/satellites/view/sentinel-3b"
)


# Collections (frozensets) for specific constellations:
VIIRS_CONSTELLATION = frozenset([Satellite.SNPP, Satellite.NOAA_20, Satellite.NOAA_21])
MODIS_CONSTELLATION = frozenset([Satellite.TERRA, Satellite.AQUA])
GOES_CONSTELLATION = frozenset(
    [Satellite.GOES_16, Satellite.GOES_18, Satellite.GOES_19]
)
SENTINEL_3_CONSTELLATION = frozenset([Satellite.SENTINEL_3A, Satellite.SENTINEL_3B])


@attrs.frozen
class BandType:
    """An extensible categorization of spectral bands.

    Plugins can register new band types::

        THERMAL = BandType.register("Thermal")
    """

    name: str

    _registry: ClassVar[Dict[str, "BandType"]] = {}

    # explicit type stub for mypy
    VISIBLE: ClassVar["BandType"]
    NEAR_INFRARED: ClassVar["BandType"]
    SHORTWAVE_INFRARED: ClassVar["BandType"]
    INFRARED: ClassVar["BandType"]
    DAY_NIGHT: ClassVar["BandType"]

    def __repr__(self) -> str:
        prop = self.name.replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        return f"BandType.{prop}"

    @classmethod
    def register(cls, name: str) -> "BandType":
        """Register a new band type or return an existing one."""
        if name in cls._registry:
            return cls._registry[name]

        instance = cls(name=name)
        cls._registry[name] = instance

        prop_name = name.replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        setattr(cls, prop_name, instance)
        return instance

    @classmethod
    def get(cls, name: str) -> "BandType":
        """Retrieve a registered band type by name."""
        if name not in cls._registry:
            raise KeyError(
                f"BandType '{name}' is not registered. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["BandType", ...]:
        """Return all registered band types."""
        return tuple(cls._registry.values())


BandType.register("Visible")
BandType.register("Near-Infrared")
BandType.register("Shortwave Infrared")
BandType.register("Infrared")
BandType.register("Day/Night")


@attrs.frozen
class Band:
    """Base spectral band type."""

    name: str
    band_type: BandType
    central_wavelength: float
    bandwidth: float


@attrs.frozen
class Channel:
    """A spectral channel binding an instrument band to a specific channel ID and resolution.

    Attributes:
        c_id: The channel identifier (e.g. "1", "M1", "Oa01").
        instrument: The instrument this channel belongs to.
        band: The spectral band definition.
        resolution: The spatial resolution in meters at nadir.
    """

    c_id: str
    instrument: Instrument
    band: Band
    resolution: int


@attrs.frozen
class Product:
    """A specific data product produced by an instrument, containing a subset of channels.

    Products are automatically added to a central registry on creation.
    Plugins can instantiate new products and they will be discoverable via
    ``Product.get()`` and ``Product.all()``.

    Attributes:
        name: The canonical name or pattern of the product.
        instrument: The instrument that generated this product.
        supported_satellites: Satellites that emit this product.
        channels: A tuple of specific Channels available in this product.
    """

    name: str
    instrument: Instrument
    supported_satellites: FrozenSet[Satellite]
    channels: tuple[Channel, ...]

    _registry: ClassVar[Dict[str, "Product"]] = {}

    def __attrs_post_init__(self) -> None:
        Product._registry[self.name] = self

    def __repr__(self) -> str:
        return f"Product({self.name!r})"

    @classmethod
    def get(cls, name: str) -> "Product":
        """Retrieve a registered product by name."""
        if name not in cls._registry:
            raise KeyError(
                f"Product '{name}' is not registered. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["Product", ...]:
        """Return all registered products."""
        return tuple(cls._registry.values())


# ==========================================
# ABI Channels (Module-level singletons)
# ==========================================

ABI_BAND_1 = Channel(
    c_id="1",
    instrument=Instrument.ABI,
    band=Band(
        name="Blue", band_type=BandType.VISIBLE, central_wavelength=0.47, bandwidth=0.04
    ),
    resolution=1000,
)
ABI_BAND_2 = Channel(
    c_id="2",
    instrument=Instrument.ABI,
    band=Band(
        name="Red", band_type=BandType.VISIBLE, central_wavelength=0.64, bandwidth=0.10
    ),
    resolution=500,
)
ABI_BAND_3 = Channel(
    c_id="3",
    instrument=Instrument.ABI,
    band=Band(
        name="Veggie",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.86,
        bandwidth=0.04,
    ),
    resolution=1000,
)
ABI_BAND_4 = Channel(
    c_id="4",
    instrument=Instrument.ABI,
    band=Band(
        name="Cirrus",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.38,
        bandwidth=0.03,
    ),
    resolution=2000,
)
ABI_BAND_5 = Channel(
    c_id="5",
    instrument=Instrument.ABI,
    band=Band(
        name="Snow/Ice",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.61,
        bandwidth=0.06,
    ),
    resolution=1000,
)
ABI_BAND_6 = Channel(
    c_id="6",
    instrument=Instrument.ABI,
    band=Band(
        name="Cloud particle size",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=2.26,
        bandwidth=0.05,
    ),
    resolution=2000,
)
ABI_BAND_7 = Channel(
    c_id="7",
    instrument=Instrument.ABI,
    band=Band(
        name="Shortwave window",
        band_type=BandType.INFRARED,
        central_wavelength=3.90,
        bandwidth=0.20,
    ),
    resolution=2000,
)
ABI_BAND_8 = Channel(
    c_id="8",
    instrument=Instrument.ABI,
    band=Band(
        name="Upper-level water vapor",
        band_type=BandType.INFRARED,
        central_wavelength=6.15,
        bandwidth=0.90,
    ),
    resolution=2000,
)
ABI_BAND_9 = Channel(
    c_id="9",
    instrument=Instrument.ABI,
    band=Band(
        name="Midlevel water vapor",
        band_type=BandType.INFRARED,
        central_wavelength=7.00,
        bandwidth=0.40,
    ),
    resolution=2000,
)
ABI_BAND_10 = Channel(
    c_id="10",
    instrument=Instrument.ABI,
    band=Band(
        name="Lower-level water vapor",
        band_type=BandType.INFRARED,
        central_wavelength=7.40,
        bandwidth=0.20,
    ),
    resolution=2000,
)
ABI_BAND_11 = Channel(
    c_id="11",
    instrument=Instrument.ABI,
    band=Band(
        name="Cloud-top phase",
        band_type=BandType.INFRARED,
        central_wavelength=8.50,
        bandwidth=0.40,
    ),
    resolution=2000,
)
ABI_BAND_12 = Channel(
    c_id="12",
    instrument=Instrument.ABI,
    band=Band(
        name="Ozone",
        band_type=BandType.INFRARED,
        central_wavelength=9.70,
        bandwidth=0.20,
    ),
    resolution=2000,
)
ABI_BAND_13 = Channel(
    c_id="13",
    instrument=Instrument.ABI,
    band=Band(
        name="Clean longwave window",
        band_type=BandType.INFRARED,
        central_wavelength=10.3,
        bandwidth=0.50,
    ),
    resolution=2000,
)
ABI_BAND_14 = Channel(
    c_id="14",
    instrument=Instrument.ABI,
    band=Band(
        name="Longwave window",
        band_type=BandType.INFRARED,
        central_wavelength=11.2,
        bandwidth=0.80,
    ),
    resolution=2000,
)
ABI_BAND_15 = Channel(
    c_id="15",
    instrument=Instrument.ABI,
    band=Band(
        name="Dirty longwave window",
        band_type=BandType.INFRARED,
        central_wavelength=12.3,
        bandwidth=1.00,
    ),
    resolution=2000,
)
ABI_BAND_16 = Channel(
    c_id="16",
    instrument=Instrument.ABI,
    band=Band(
        name="CO2 longwave",
        band_type=BandType.INFRARED,
        central_wavelength=13.3,
        bandwidth=0.60,
    ),
    resolution=2000,
)

ABI_CHANNELS = (
    ABI_BAND_1,
    ABI_BAND_2,
    ABI_BAND_3,
    ABI_BAND_4,
    ABI_BAND_5,
    ABI_BAND_6,
    ABI_BAND_7,
    ABI_BAND_8,
    ABI_BAND_9,
    ABI_BAND_10,
    ABI_BAND_11,
    ABI_BAND_12,
    ABI_BAND_13,
    ABI_BAND_14,
    ABI_BAND_15,
    ABI_BAND_16,
)

# ==========================================
# VIIRS Channels (Module-level singletons)
# ==========================================

VIIRS_M1 = Channel(
    c_id="M1",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M1", band_type=BandType.VISIBLE, central_wavelength=0.412, bandwidth=0.020
    ),
    resolution=750,
)
VIIRS_M2 = Channel(
    c_id="M2",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M2", band_type=BandType.VISIBLE, central_wavelength=0.445, bandwidth=0.018
    ),
    resolution=750,
)
VIIRS_M3 = Channel(
    c_id="M3",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M3", band_type=BandType.VISIBLE, central_wavelength=0.488, bandwidth=0.020
    ),
    resolution=750,
)
VIIRS_M4 = Channel(
    c_id="M4",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M4", band_type=BandType.VISIBLE, central_wavelength=0.555, bandwidth=0.020
    ),
    resolution=750,
)
VIIRS_M5 = Channel(
    c_id="M5",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M5",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.672,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M6 = Channel(
    c_id="M6",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M6",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.746,
        bandwidth=0.015,
    ),
    resolution=750,
)
VIIRS_M7 = Channel(
    c_id="M7",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M7",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.865,
        bandwidth=0.039,
    ),
    resolution=750,
)
VIIRS_M8 = Channel(
    c_id="M8",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M8",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.240,
        bandwidth=0.020,
    ),
    resolution=750,
)
VIIRS_M9 = Channel(
    c_id="M9",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M9",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.378,
        bandwidth=0.015,
    ),
    resolution=750,
)
VIIRS_M10 = Channel(
    c_id="M10",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M10",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.610,
        bandwidth=0.060,
    ),
    resolution=750,
)
VIIRS_M11 = Channel(
    c_id="M11",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M11",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=2.250,
        bandwidth=0.050,
    ),
    resolution=750,
)
VIIRS_M12 = Channel(
    c_id="M12",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M12",
        band_type=BandType.INFRARED,
        central_wavelength=3.700,
        bandwidth=0.180,
    ),
    resolution=750,
)
VIIRS_M13 = Channel(
    c_id="M13",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M13",
        band_type=BandType.INFRARED,
        central_wavelength=4.050,
        bandwidth=0.155,
    ),
    resolution=750,
)
VIIRS_M14 = Channel(
    c_id="M14",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M14",
        band_type=BandType.INFRARED,
        central_wavelength=8.550,
        bandwidth=0.300,
    ),
    resolution=750,
)
VIIRS_M15 = Channel(
    c_id="M15",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M15",
        band_type=BandType.INFRARED,
        central_wavelength=10.763,
        bandwidth=1.000,
    ),
    resolution=750,
)
VIIRS_M16 = Channel(
    c_id="M16",
    instrument=Instrument.VIIRS,
    band=Band(
        name="M16",
        band_type=BandType.INFRARED,
        central_wavelength=12.013,
        bandwidth=0.950,
    ),
    resolution=750,
)
VIIRS_I1 = Channel(
    c_id="I1",
    instrument=Instrument.VIIRS,
    band=Band(
        name="I1", band_type=BandType.VISIBLE, central_wavelength=0.640, bandwidth=0.080
    ),  # approx based on 0.60-0.68 range
    resolution=375,
)
VIIRS_I2 = Channel(
    c_id="I2",
    instrument=Instrument.VIIRS,
    band=Band(
        name="I2",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.865,
        bandwidth=0.039,
    ),  # approx based on 0.845-0.884
    resolution=375,
)
VIIRS_I3 = Channel(
    c_id="I3",
    instrument=Instrument.VIIRS,
    band=Band(
        name="I3",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.610,
        bandwidth=0.060,
    ),  # approx based on 1.58-1.64
    resolution=375,
)
VIIRS_I4 = Channel(
    c_id="I4",
    instrument=Instrument.VIIRS,
    band=Band(
        name="I4",
        band_type=BandType.INFRARED,
        central_wavelength=3.740,
        bandwidth=0.380,
    ),  # approx 3.55-3.93
    resolution=375,
)
VIIRS_I5 = Channel(
    c_id="I5",
    instrument=Instrument.VIIRS,
    band=Band(
        name="I5",
        band_type=BandType.INFRARED,
        central_wavelength=11.450,
        bandwidth=1.900,
    ),  # approx 10.5-12.4
    resolution=375,
)
VIIRS_DNB = Channel(
    c_id="DNB",
    instrument=Instrument.VIIRS,
    band=Band(
        name="DNB",
        band_type=BandType.DAY_NIGHT,
        central_wavelength=0.700,
        bandwidth=0.400,
    ),  # approx 0.5-0.9
    resolution=750,
)

VIIRS_CHANNELS = (
    VIIRS_M1,
    VIIRS_M2,
    VIIRS_M3,
    VIIRS_M4,
    VIIRS_M5,
    VIIRS_M6,
    VIIRS_M7,
    VIIRS_M8,
    VIIRS_M9,
    VIIRS_M10,
    VIIRS_M11,
    VIIRS_M12,
    VIIRS_M13,
    VIIRS_M14,
    VIIRS_M15,
    VIIRS_M16,
    VIIRS_I1,
    VIIRS_I2,
    VIIRS_I3,
    VIIRS_I4,
    VIIRS_I5,
    VIIRS_DNB,
)

# ==========================================
# MODIS Channels (Module-level singletons)
# ==========================================

MODIS_BAND_1 = Channel(
    c_id="1",
    instrument=Instrument.MODIS,
    band=Band(
        name="1", band_type=BandType.VISIBLE, central_wavelength=0.645, bandwidth=0.050
    ),
    resolution=250,
)
MODIS_BAND_2 = Channel(
    c_id="2",
    instrument=Instrument.MODIS,
    band=Band(
        name="2",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.858,
        bandwidth=0.035,
    ),
    resolution=250,
)
MODIS_BAND_3 = Channel(
    c_id="3",
    instrument=Instrument.MODIS,
    band=Band(
        name="3", band_type=BandType.VISIBLE, central_wavelength=0.469, bandwidth=0.020
    ),
    resolution=500,
)
MODIS_BAND_4 = Channel(
    c_id="4",
    instrument=Instrument.MODIS,
    band=Band(
        name="4", band_type=BandType.VISIBLE, central_wavelength=0.555, bandwidth=0.020
    ),
    resolution=500,
)
MODIS_BAND_5 = Channel(
    c_id="5",
    instrument=Instrument.MODIS,
    band=Band(
        name="5",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=1.240,
        bandwidth=0.020,
    ),
    resolution=500,
)
MODIS_BAND_6 = Channel(
    c_id="6",
    instrument=Instrument.MODIS,
    band=Band(
        name="6",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.640,
        bandwidth=0.024,
    ),
    resolution=500,
)
MODIS_BAND_7 = Channel(
    c_id="7",
    instrument=Instrument.MODIS,
    band=Band(
        name="7",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=2.130,
        bandwidth=0.050,
    ),
    resolution=500,
)
MODIS_BAND_8 = Channel(
    c_id="8",
    instrument=Instrument.MODIS,
    band=Band(
        name="8", band_type=BandType.VISIBLE, central_wavelength=0.412, bandwidth=0.015
    ),
    resolution=1000,
)
MODIS_BAND_9 = Channel(
    c_id="9",
    instrument=Instrument.MODIS,
    band=Band(
        name="9", band_type=BandType.VISIBLE, central_wavelength=0.443, bandwidth=0.010
    ),
    resolution=1000,
)
MODIS_BAND_10 = Channel(
    c_id="10",
    instrument=Instrument.MODIS,
    band=Band(
        name="10", band_type=BandType.VISIBLE, central_wavelength=0.488, bandwidth=0.010
    ),
    resolution=1000,
)
MODIS_BAND_11 = Channel(
    c_id="11",
    instrument=Instrument.MODIS,
    band=Band(
        name="11", band_type=BandType.VISIBLE, central_wavelength=0.531, bandwidth=0.010
    ),
    resolution=1000,
)
MODIS_BAND_12 = Channel(
    c_id="12",
    instrument=Instrument.MODIS,
    band=Band(
        name="12", band_type=BandType.VISIBLE, central_wavelength=0.551, bandwidth=0.010
    ),
    resolution=1000,
)
MODIS_BAND_13h = Channel(
    c_id="13h",
    instrument=Instrument.MODIS,
    band=Band(
        name="13h",
        band_type=BandType.VISIBLE,
        central_wavelength=0.667,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_13l = Channel(
    c_id="13l",
    instrument=Instrument.MODIS,
    band=Band(
        name="13l",
        band_type=BandType.VISIBLE,
        central_wavelength=0.667,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_14h = Channel(
    c_id="14h",
    instrument=Instrument.MODIS,
    band=Band(
        name="14h",
        band_type=BandType.VISIBLE,
        central_wavelength=0.678,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_14l = Channel(
    c_id="14l",
    instrument=Instrument.MODIS,
    band=Band(
        name="14l",
        band_type=BandType.VISIBLE,
        central_wavelength=0.678,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_15 = Channel(
    c_id="15",
    instrument=Instrument.MODIS,
    band=Band(
        name="15", band_type=BandType.VISIBLE, central_wavelength=0.748, bandwidth=0.010
    ),
    resolution=1000,
)
MODIS_BAND_16 = Channel(
    c_id="16",
    instrument=Instrument.MODIS,
    band=Band(
        name="16",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.870,
        bandwidth=0.015,
    ),
    resolution=1000,
)
MODIS_BAND_17 = Channel(
    c_id="17",
    instrument=Instrument.MODIS,
    band=Band(
        name="17",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.905,
        bandwidth=0.030,
    ),
    resolution=1000,
)
MODIS_BAND_18 = Channel(
    c_id="18",
    instrument=Instrument.MODIS,
    band=Band(
        name="18",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.936,
        bandwidth=0.010,
    ),
    resolution=1000,
)
MODIS_BAND_19 = Channel(
    c_id="19",
    instrument=Instrument.MODIS,
    band=Band(
        name="19",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.940,
        bandwidth=0.050,
    ),
    resolution=1000,
)
MODIS_BAND_20 = Channel(
    c_id="20",
    instrument=Instrument.MODIS,
    band=Band(
        name="20",
        band_type=BandType.INFRARED,
        central_wavelength=3.750,
        bandwidth=0.180,
    ),
    resolution=1000,
)
MODIS_BAND_21 = Channel(
    c_id="21",
    instrument=Instrument.MODIS,
    band=Band(
        name="21",
        band_type=BandType.INFRARED,
        central_wavelength=3.959,
        bandwidth=0.060,
    ),
    resolution=1000,
)
MODIS_BAND_22 = Channel(
    c_id="22",
    instrument=Instrument.MODIS,
    band=Band(
        name="22",
        band_type=BandType.INFRARED,
        central_wavelength=3.959,
        bandwidth=0.060,
    ),
    resolution=1000,
)
MODIS_BAND_23 = Channel(
    c_id="23",
    instrument=Instrument.MODIS,
    band=Band(
        name="23",
        band_type=BandType.INFRARED,
        central_wavelength=4.050,
        bandwidth=0.060,
    ),
    resolution=1000,
)
MODIS_BAND_24 = Channel(
    c_id="24",
    instrument=Instrument.MODIS,
    band=Band(
        name="24",
        band_type=BandType.INFRARED,
        central_wavelength=4.515,
        bandwidth=0.165,
    ),
    resolution=1000,
)
MODIS_BAND_25 = Channel(
    c_id="25",
    instrument=Instrument.MODIS,
    band=Band(
        name="25",
        band_type=BandType.INFRARED,
        central_wavelength=4.515,
        bandwidth=0.067,
    ),
    resolution=1000,
)
MODIS_BAND_26 = Channel(
    c_id="26",
    instrument=Instrument.MODIS,
    band=Band(
        name="26",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=1.375,
        bandwidth=0.030,
    ),
    resolution=1000,
)
MODIS_BAND_27 = Channel(
    c_id="27",
    instrument=Instrument.MODIS,
    band=Band(
        name="27",
        band_type=BandType.INFRARED,
        central_wavelength=6.715,
        bandwidth=0.360,
    ),
    resolution=1000,
)
MODIS_BAND_28 = Channel(
    c_id="28",
    instrument=Instrument.MODIS,
    band=Band(
        name="28",
        band_type=BandType.INFRARED,
        central_wavelength=7.325,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_29 = Channel(
    c_id="29",
    instrument=Instrument.MODIS,
    band=Band(
        name="29",
        band_type=BandType.INFRARED,
        central_wavelength=8.550,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_30 = Channel(
    c_id="30",
    instrument=Instrument.MODIS,
    band=Band(
        name="30",
        band_type=BandType.INFRARED,
        central_wavelength=9.730,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_31 = Channel(
    c_id="31",
    instrument=Instrument.MODIS,
    band=Band(
        name="31",
        band_type=BandType.INFRARED,
        central_wavelength=11.030,
        bandwidth=0.500,
    ),
    resolution=1000,
)
MODIS_BAND_32 = Channel(
    c_id="32",
    instrument=Instrument.MODIS,
    band=Band(
        name="32",
        band_type=BandType.INFRARED,
        central_wavelength=12.020,
        bandwidth=0.500,
    ),
    resolution=1000,
)
MODIS_BAND_33 = Channel(
    c_id="33",
    instrument=Instrument.MODIS,
    band=Band(
        name="33",
        band_type=BandType.INFRARED,
        central_wavelength=13.335,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_34 = Channel(
    c_id="34",
    instrument=Instrument.MODIS,
    band=Band(
        name="34",
        band_type=BandType.INFRARED,
        central_wavelength=13.635,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_35 = Channel(
    c_id="35",
    instrument=Instrument.MODIS,
    band=Band(
        name="35",
        band_type=BandType.INFRARED,
        central_wavelength=13.935,
        bandwidth=0.300,
    ),
    resolution=1000,
)
MODIS_BAND_36 = Channel(
    c_id="36",
    instrument=Instrument.MODIS,
    band=Band(
        name="36",
        band_type=BandType.INFRARED,
        central_wavelength=14.235,
        bandwidth=0.300,
    ),
    resolution=1000,
)

MODIS_CHANNELS = (
    MODIS_BAND_1,
    MODIS_BAND_2,
    MODIS_BAND_3,
    MODIS_BAND_4,
    MODIS_BAND_5,
    MODIS_BAND_6,
    MODIS_BAND_7,
    MODIS_BAND_8,
    MODIS_BAND_9,
    MODIS_BAND_10,
    MODIS_BAND_11,
    MODIS_BAND_12,
    MODIS_BAND_13h,
    MODIS_BAND_13l,
    MODIS_BAND_14h,
    MODIS_BAND_14l,
    MODIS_BAND_15,
    MODIS_BAND_16,
    MODIS_BAND_17,
    MODIS_BAND_18,
    MODIS_BAND_19,
    MODIS_BAND_20,
    MODIS_BAND_21,
    MODIS_BAND_22,
    MODIS_BAND_23,
    MODIS_BAND_24,
    MODIS_BAND_25,
    MODIS_BAND_26,
    MODIS_BAND_27,
    MODIS_BAND_28,
    MODIS_BAND_29,
    MODIS_BAND_30,
    MODIS_BAND_31,
    MODIS_BAND_32,
    MODIS_BAND_33,
    MODIS_BAND_34,
    MODIS_BAND_35,
    MODIS_BAND_36,
)

# ==========================================
# OLCI Channels (Module-level singletons)
# ==========================================

OLCI_BAND_Oa01 = Channel(
    c_id="Oa01",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa01", band_type=BandType.VISIBLE, central_wavelength=0.4, bandwidth=0.015
    ),
    resolution=300,
)
OLCI_BAND_Oa02 = Channel(
    c_id="Oa02",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa02",
        band_type=BandType.VISIBLE,
        central_wavelength=0.4125,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa03 = Channel(
    c_id="Oa03",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa03",
        band_type=BandType.VISIBLE,
        central_wavelength=0.4425,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa04 = Channel(
    c_id="Oa04",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa04", band_type=BandType.VISIBLE, central_wavelength=0.49, bandwidth=0.01
    ),
    resolution=300,
)
OLCI_BAND_Oa05 = Channel(
    c_id="Oa05",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa05", band_type=BandType.VISIBLE, central_wavelength=0.51, bandwidth=0.01
    ),
    resolution=300,
)
OLCI_BAND_Oa06 = Channel(
    c_id="Oa06",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa06", band_type=BandType.VISIBLE, central_wavelength=0.56, bandwidth=0.01
    ),
    resolution=300,
)
OLCI_BAND_Oa07 = Channel(
    c_id="Oa07",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa07", band_type=BandType.VISIBLE, central_wavelength=0.62, bandwidth=0.01
    ),
    resolution=300,
)
OLCI_BAND_Oa08 = Channel(
    c_id="Oa08",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa08",
        band_type=BandType.VISIBLE,
        central_wavelength=0.665,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa09 = Channel(
    c_id="Oa09",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa09",
        band_type=BandType.VISIBLE,
        central_wavelength=0.67375,
        bandwidth=0.0075,
    ),
    resolution=300,
)
OLCI_BAND_Oa10 = Channel(
    c_id="Oa10",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa10",
        band_type=BandType.VISIBLE,
        central_wavelength=0.68125,
        bandwidth=0.0075,
    ),
    resolution=300,
)
OLCI_BAND_Oa11 = Channel(
    c_id="Oa11",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa11",
        band_type=BandType.VISIBLE,
        central_wavelength=0.70875,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa12 = Channel(
    c_id="Oa12",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa12",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.75375,
        bandwidth=0.0075,
    ),
    resolution=300,
)
OLCI_BAND_Oa13 = Channel(
    c_id="Oa13",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa13",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.76125,
        bandwidth=0.0025,
    ),
    resolution=300,
)
OLCI_BAND_Oa14 = Channel(
    c_id="Oa14",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa14",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.764375,
        bandwidth=0.00375,
    ),
    resolution=300,
)
OLCI_BAND_Oa15 = Channel(
    c_id="Oa15",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa15",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.7675,
        bandwidth=0.0025,
    ),
    resolution=300,
)
OLCI_BAND_Oa16 = Channel(
    c_id="Oa16",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa16",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.77875,
        bandwidth=0.015,
    ),
    resolution=300,
)
OLCI_BAND_Oa17 = Channel(
    c_id="Oa17",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa17",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.865,
        bandwidth=0.02,
    ),
    resolution=300,
)
OLCI_BAND_Oa18 = Channel(
    c_id="Oa18",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa18",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.885,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa19 = Channel(
    c_id="Oa19",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa19",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.9,
        bandwidth=0.01,
    ),
    resolution=300,
)
OLCI_BAND_Oa20 = Channel(
    c_id="Oa20",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa20",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.94,
        bandwidth=0.02,
    ),
    resolution=300,
)
OLCI_BAND_Oa21 = Channel(
    c_id="Oa21",
    instrument=Instrument.OLCI,
    band=Band(
        name="Oa21",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=1.02,
        bandwidth=0.04,
    ),
    resolution=300,
)

OLCI_CHANNELS = (
    OLCI_BAND_Oa01,
    OLCI_BAND_Oa02,
    OLCI_BAND_Oa03,
    OLCI_BAND_Oa04,
    OLCI_BAND_Oa05,
    OLCI_BAND_Oa06,
    OLCI_BAND_Oa07,
    OLCI_BAND_Oa08,
    OLCI_BAND_Oa09,
    OLCI_BAND_Oa10,
    OLCI_BAND_Oa11,
    OLCI_BAND_Oa12,
    OLCI_BAND_Oa13,
    OLCI_BAND_Oa14,
    OLCI_BAND_Oa15,
    OLCI_BAND_Oa16,
    OLCI_BAND_Oa17,
    OLCI_BAND_Oa18,
    OLCI_BAND_Oa19,
    OLCI_BAND_Oa20,
    OLCI_BAND_Oa21,
)

# ==========================================
# SLSTR Channels (Module-level singletons)
# ==========================================

SLSTR_BAND_S1 = Channel(
    c_id="S1",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S1",
        band_type=BandType.VISIBLE,
        central_wavelength=0.55427,
        bandwidth=0.01926,
    ),
    resolution=500,
)
SLSTR_BAND_S2 = Channel(
    c_id="S2",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S2",
        band_type=BandType.VISIBLE,
        central_wavelength=0.65947,
        bandwidth=0.01925,
    ),
    resolution=500,
)
SLSTR_BAND_S3 = Channel(
    c_id="S3",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S3",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=0.868,
        bandwidth=0.0206,
    ),
    resolution=500,
)
SLSTR_BAND_S4 = Channel(
    c_id="S4",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S4",
        band_type=BandType.NEAR_INFRARED,
        central_wavelength=1.3748,
        bandwidth=0.0208,
    ),
    resolution=500,
)
SLSTR_BAND_S5 = Channel(
    c_id="S5",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S5",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=1.6134,
        bandwidth=0.06068,
    ),
    resolution=500,
)
SLSTR_BAND_S6 = Channel(
    c_id="S6",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S6",
        band_type=BandType.SHORTWAVE_INFRARED,
        central_wavelength=2.2557,
        bandwidth=0.05015,
    ),
    resolution=500,
)
SLSTR_BAND_S7 = Channel(
    c_id="S7",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S7",
        band_type=BandType.INFRARED,
        central_wavelength=3.742,
        bandwidth=0.398,
    ),
    resolution=1000,
)
SLSTR_BAND_S8 = Channel(
    c_id="S8",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S8",
        band_type=BandType.INFRARED,
        central_wavelength=10.854,
        bandwidth=0.776,
    ),
    resolution=1000,
)
SLSTR_BAND_S9 = Channel(
    c_id="S9",
    instrument=Instrument.SLSTR,
    band=Band(
        name="S9",
        band_type=BandType.INFRARED,
        central_wavelength=12.0225,
        bandwidth=0.905,
    ),
    resolution=1000,
)
SLSTR_BAND_F1 = Channel(
    c_id="F1",
    instrument=Instrument.SLSTR,
    band=Band(
        name="F1",
        band_type=BandType.INFRARED,
        central_wavelength=3.742,
        bandwidth=0.398,
    ),
    resolution=1000,
)
SLSTR_BAND_F2 = Channel(
    c_id="F2",
    instrument=Instrument.SLSTR,
    band=Band(
        name="F2",
        band_type=BandType.INFRARED,
        central_wavelength=10.854,
        bandwidth=0.776,
    ),
    resolution=1000,
)

SLSTR_CHANNELS = (
    SLSTR_BAND_S1,
    SLSTR_BAND_S2,
    SLSTR_BAND_S3,
    SLSTR_BAND_S4,
    SLSTR_BAND_S5,
    SLSTR_BAND_S6,
    SLSTR_BAND_S7,
    SLSTR_BAND_S8,
    SLSTR_BAND_S9,
    SLSTR_BAND_F1,
    SLSTR_BAND_F2,
)

# ==========================================
# Products (Module-level singletons)
# ==========================================

# ABI Products
ABI_L1B_RADF = Product(
    name="ABI-L1b-RadF",
    instrument=Instrument.ABI,
    supported_satellites=frozenset(
        [Satellite.GOES_16, Satellite.GOES_18, Satellite.GOES_19]
    ),
    channels=ABI_CHANNELS,
)

ABI_L1B_RADC = Product(
    name="ABI-L1b-RadC",
    instrument=Instrument.ABI,
    supported_satellites=frozenset(
        [Satellite.GOES_16, Satellite.GOES_18, Satellite.GOES_19]
    ),
    channels=ABI_CHANNELS,
)

ABI_L1B_RADM = Product(
    name="ABI-L1b-RadM",
    instrument=Instrument.ABI,
    supported_satellites=frozenset(
        [Satellite.GOES_16, Satellite.GOES_18, Satellite.GOES_19]
    ),
    channels=ABI_CHANNELS,
)

# VIIRS S-NPP Products
VNP02IMG = Product(
    name="VNP02IMG",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.SNPP]),
    channels=(VIIRS_I1, VIIRS_I2, VIIRS_I3, VIIRS_I4, VIIRS_I5),
)

VNP03IMG = Product(
    name="VNP03IMG",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.SNPP]),
    channels=(),
)

VNP02MOD = Product(
    name="VNP02MOD",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.SNPP]),
    channels=(
        VIIRS_M1,
        VIIRS_M2,
        VIIRS_M3,
        VIIRS_M4,
        VIIRS_M5,
        VIIRS_M6,
        VIIRS_M7,
        VIIRS_M8,
        VIIRS_M9,
        VIIRS_M10,
        VIIRS_M11,
        VIIRS_M12,
        VIIRS_M13,
        VIIRS_M14,
        VIIRS_M15,
        VIIRS_M16,
    ),
)

VNP03MOD = Product(
    name="VNP03MOD",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.SNPP]),
    channels=(),
)

VNP02DNB = Product(
    name="VNP02DNB",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.SNPP]),
    channels=(VIIRS_DNB,),
)

VNP03DNB = Product(
    name="VNP03DNB",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.SNPP]),
    channels=(),
)

# VIIRS NOAA-20 Products
VJ102IMG = Product(
    name="VJ102IMG",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_20]),
    channels=(VIIRS_I1, VIIRS_I2, VIIRS_I3, VIIRS_I4, VIIRS_I5),
)

VJ103IMG = Product(
    name="VJ103IMG",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_20]),
    channels=(),
)

VJ102MOD = Product(
    name="VJ102MOD",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_20]),
    channels=(
        VIIRS_M1,
        VIIRS_M2,
        VIIRS_M3,
        VIIRS_M4,
        VIIRS_M5,
        VIIRS_M6,
        VIIRS_M7,
        VIIRS_M8,
        VIIRS_M9,
        VIIRS_M10,
        VIIRS_M11,
        VIIRS_M12,
        VIIRS_M13,
        VIIRS_M14,
        VIIRS_M15,
        VIIRS_M16,
    ),
)

VJ103MOD = Product(
    name="VJ103MOD",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_20]),
    channels=(),
)

VJ102DNB = Product(
    name="VJ102DNB",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_20]),
    channels=(VIIRS_DNB,),
)

VJ103DNB = Product(
    name="VJ103DNB",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_20]),
    channels=(),
)

# VIIRS NOAA-21 Products
VJ202IMG = Product(
    name="VJ202IMG",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_21]),
    channels=(VIIRS_I1, VIIRS_I2, VIIRS_I3, VIIRS_I4, VIIRS_I5),
)

VJ203IMG = Product(
    name="VJ203IMG",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_21]),
    channels=(),
)

VJ202MOD = Product(
    name="VJ202MOD",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_21]),
    channels=(
        VIIRS_M1,
        VIIRS_M2,
        VIIRS_M3,
        VIIRS_M4,
        VIIRS_M5,
        VIIRS_M6,
        VIIRS_M7,
        VIIRS_M8,
        VIIRS_M9,
        VIIRS_M10,
        VIIRS_M11,
        VIIRS_M12,
        VIIRS_M13,
        VIIRS_M14,
        VIIRS_M15,
        VIIRS_M16,
    ),
)

VJ203MOD = Product(
    name="VJ203MOD",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_21]),
    channels=(),
)

VJ202DNB = Product(
    name="VJ202DNB",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_21]),
    channels=(VIIRS_DNB,),
)

VJ203DNB = Product(
    name="VJ203DNB",
    instrument=Instrument.VIIRS,
    supported_satellites=frozenset([Satellite.NOAA_21]),
    channels=(),
)

# MODIS Products
MODIS_02QKM = Product(
    name="MOD02QKM",
    instrument=Instrument.MODIS,
    supported_satellites=frozenset([Satellite.TERRA]),
    channels=(MODIS_BAND_1, MODIS_BAND_2),
)

MODIS_02HKM = Product(
    name="MOD02HKM",
    instrument=Instrument.MODIS,
    supported_satellites=frozenset([Satellite.TERRA]),
    channels=(
        MODIS_BAND_1,
        MODIS_BAND_2,
        MODIS_BAND_3,
        MODIS_BAND_4,
        MODIS_BAND_5,
        MODIS_BAND_6,
        MODIS_BAND_7,
    ),
)

MODIS_021KM = Product(
    name="MOD021KM",
    instrument=Instrument.MODIS,
    supported_satellites=frozenset([Satellite.TERRA]),
    channels=MODIS_CHANNELS,
)

MYDIS_02QKM = Product(
    name="MYD02QKM",
    instrument=Instrument.MODIS,
    supported_satellites=frozenset([Satellite.AQUA]),
    channels=(MODIS_BAND_1, MODIS_BAND_2),
)

MYDIS_02HKM = Product(
    name="MYD02HKM",
    instrument=Instrument.MODIS,
    supported_satellites=frozenset([Satellite.AQUA]),
    channels=(
        MODIS_BAND_1,
        MODIS_BAND_2,
        MODIS_BAND_3,
        MODIS_BAND_4,
        MODIS_BAND_5,
        MODIS_BAND_6,
        MODIS_BAND_7,
    ),
)

MYDIS_021KM = Product(
    name="MYD021KM",
    instrument=Instrument.MODIS,
    supported_satellites=frozenset([Satellite.AQUA]),
    channels=MODIS_CHANNELS,
)

# Sentinel-3 Products
SENTINEL_3_OLCI_1_EFR_NRT = Product(
    name="sentinel-3-olci-1-efr-nrt",
    instrument=Instrument.OLCI,
    supported_satellites=frozenset([Satellite.SENTINEL_3A, Satellite.SENTINEL_3B]),
    channels=OLCI_CHANNELS,
)

SENTINEL_3_OLCI_1_EFR_NTC = Product(
    name="sentinel-3-olci-1-efr-ntc",
    instrument=Instrument.OLCI,
    supported_satellites=frozenset([Satellite.SENTINEL_3A, Satellite.SENTINEL_3B]),
    channels=OLCI_CHANNELS,
)

SENTINEL_3_SLSTR_1_RBT_NRT = Product(
    name="sentinel-3-slstr-1-rbt-nrt",
    instrument=Instrument.SLSTR,
    supported_satellites=frozenset([Satellite.SENTINEL_3A, Satellite.SENTINEL_3B]),
    channels=SLSTR_CHANNELS,
)

SENTINEL_3_SLSTR_1_RBT_NTC = Product(
    name="sentinel-3-slstr-1-rbt-ntc",
    instrument=Instrument.SLSTR,
    supported_satellites=frozenset([Satellite.SENTINEL_3A, Satellite.SENTINEL_3B]),
    channels=SLSTR_CHANNELS,
)
