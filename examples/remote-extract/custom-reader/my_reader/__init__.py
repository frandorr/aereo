"""Synthetic reader example for AEREO remote extraction.

This package demonstrates how a user drops a custom :class:`aereo.interfaces.Reader`
into the published ``aereo-extract-base`` image.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from aereo.interfaces import ExtractionTask, Reader


class SyntheticReader(Reader):
    """Reader that returns a synthetic dataset for any task.

    Useful for testing and as a template for custom readers that fetch data
    from private sources.
    """

    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        """Return a small synthetic raster dataset."""
        shape = (64, 64)
        data = np.random.default_rng(42).random(shape)
        return xr.Dataset(
            {
                "band": (["y", "x"], data),
            },
            coords={
                "y": np.linspace(0, 1, shape[0]),
                "x": np.linspace(0, 1, shape[1]),
            },
        )
