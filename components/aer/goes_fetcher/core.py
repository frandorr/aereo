from aer.temporal import TimeRange
from aer.spectral import Instrument, Satellite
import attrs

GOES_CONSTELLATION = frozenset(
    [Satellite.get("GOES-16"), Satellite.get("GOES-18"), Satellite.get("GOES-19")]
)

# ==========================================
# Domain Queries
# ==========================================


@attrs.frozen
class GOESSearchQuery:
    """A search query targeting specific conditions on a GOES ABI instrument."""

    time_range: TimeRange
    satellite: Satellite = attrs.field(
        validator=attrs.validators.in_(GOES_CONSTELLATION)
    )
    instrument: Instrument = attrs.field(
        default=attrs.Factory(lambda: Instrument.get("ABI"))
    )
