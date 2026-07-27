"""Demo processor plugin: convert SAR backscatter to decibels."""

import numpy as np
import xarray as xr
from pydantic import ConfigDict, validate_call


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def to_db(ds: xr.Dataset, clip_min: float = 1e-6) -> xr.Dataset:
    """Convert linear backscatter (e.g. Sentinel-1 vv/vh) to decibels.

    Values at or below ``clip_min`` are clipped before the log to avoid
    ``-inf`` in the output.
    """
    return 10.0 * np.log10(ds.clip(min=clip_min))
