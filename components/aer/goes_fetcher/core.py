from aer.temporal import TimeRange
from aer.spectral import Instrument, GOES_CONSTELLATION
import attrs

# ==========================================
# Domain Queries
# ==========================================


@attrs.frozen
class GOESSearchQuery:
    """A search query targeting specific conditions on a GOES ABI instrument."""

    time_range: TimeRange
    satellite: GOES_CONSTELLATION
    instrument: Instrument = Instrument.ABI
