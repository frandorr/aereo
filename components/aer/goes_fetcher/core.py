from aer.temporal import TimeRange
from aer.spectral import Instrument, Satellite, GOES_CONSTELLATION
import attrs

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
    instrument: Instrument = Instrument.ABI
