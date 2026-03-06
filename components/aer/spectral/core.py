from typing import FrozenSet, ClassVar, Dict, Optional
import attrs


@attrs.frozen
class Instrument:
    """An extensible registry of instruments."""

    name: str
    url: Optional[str] = None
    _registry: ClassVar[Dict[str, "Instrument"]] = {}

    def __repr__(self) -> str:
        return f"Instrument.{self.name.replace('-', '_').upper()}"

    @classmethod
    def register(cls, name: str, url: Optional[str] = None) -> "Instrument":
        if name in cls._registry:
            return cls._registry[name]
        instance = cls(name=name, url=url)
        cls._registry[name] = instance
        setattr(cls, name.replace("-", "_").upper(), instance)
        return instance

    @classmethod
    def get(cls, name: str) -> "Instrument":
        if name not in cls._registry:
            raise KeyError(
                f"Instrument '{name}' is not registered. Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["Instrument", ...]:
        return tuple(cls._registry.values())


@attrs.frozen
class Satellite:
    """An extensible registry of satellites."""

    name: str
    url: Optional[str] = None
    _registry: ClassVar[Dict[str, "Satellite"]] = {}

    def __repr__(self) -> str:
        return f"Satellite.{self.name.replace('-', '_').upper()}"

    @classmethod
    def register(cls, name: str, url: Optional[str] = None) -> "Satellite":
        if name in cls._registry:
            return cls._registry[name]
        instance = cls(name=name, url=url)
        cls._registry[name] = instance
        setattr(cls, name.replace("-", "_").upper(), instance)
        return instance

    @classmethod
    def get(cls, name: str) -> "Satellite":
        if name not in cls._registry:
            raise KeyError(
                f"Satellite '{name}' is not registered. Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["Satellite", ...]:
        return tuple(cls._registry.values())


@attrs.frozen
class BandType:
    """An extensible categorization of spectral bands."""

    name: str
    _registry: ClassVar[Dict[str, "BandType"]] = {}

    def __repr__(self) -> str:
        prop = self.name.replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        return f"BandType.{prop}"

    @classmethod
    def register(cls, name: str) -> "BandType":
        if name in cls._registry:
            return cls._registry[name]
        instance = cls(name=name)
        cls._registry[name] = instance
        prop_name = name.replace(" ", "_").replace("/", "_").replace("-", "_").upper()
        setattr(cls, prop_name, instance)
        return instance

    @classmethod
    def get(cls, name: str) -> "BandType":
        if name not in cls._registry:
            raise KeyError(
                f"BandType '{name}' is not registered. Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["BandType", ...]:
        return tuple(cls._registry.values())


# Pre-register BandTypes
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
    """A spectral channel binding an instrument band to a specific channel ID and resolution."""

    c_id: str
    instrument: Instrument
    band: Band
    resolution: int


@attrs.frozen
class Product:
    """A specific data product produced by an instrument, containing a subset of channels."""

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
        if name not in cls._registry:
            raise KeyError(
                f"Product '{name}' is not registered. Available: {list(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def all(cls) -> tuple["Product", ...]:
        return tuple(cls._registry.values())
