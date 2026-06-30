"""Synthetic pipeline plugins for AEREO Lambda integration testing.

These plugins require no network access and produce tiny, deterministic
GeoTIFF artifacts so the Lambda handler's S3 upload path can be exercised
end-to-end without relying on external data sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine
import xarray as xr


class TestReader:
    """Reader that returns a tiny synthetic xarray.Dataset."""

    __test__ = False
    width: int = 8
    height: int = 8

    def __init__(self, width: int = 8, height: int = 8) -> None:
        self.width = width
        self.height = height

    def __call__(
        self,
        files: list[str],
        assets: Any | None = None,
        **kwargs: Any,
    ) -> xr.Dataset:
        """Return a synthetic dataset for testing.

        Args:
            files: Source filenames (ignored).
            assets: Optional asset metadata (ignored).
            **kwargs: Additional reader kwargs (ignored).

        Returns:
            A small xarray.Dataset tagged with start/end time attributes.
        """
        del files, assets, kwargs  # unused
        data = np.arange(self.width * self.height, dtype=np.float32).reshape(
            self.height, self.width
        )
        ds = xr.Dataset(
            {"band1": (["y", "x"], data)},
            coords={
                "x": (["x"], np.linspace(0, self.width - 1, self.width)),
                "y": (["y"], np.linspace(0, self.height - 1, self.height)),
            },
        )
        ds.attrs["start_time"] = pd.Timestamp("2024-01-01T00:00:00Z")
        ds.attrs["end_time"] = pd.Timestamp("2024-01-01T00:00:00Z")
        return ds


class TestReprojector:
    """Identity reprojector compatible with the new Reprojector protocol."""

    __test__ = False

    def __call__(self, ds: xr.Dataset, **kwargs: Any) -> xr.Dataset:
        """Return the input dataset unchanged.

        Args:
            ds: Source dataset.
            **kwargs: Additional reproject kwargs (ignored).

        Returns:
            The same dataset.
        """
        del kwargs  # unused
        return ds


class TestWriter:
    """Writer that creates a tiny valid GeoTIFF file and returns its path."""

    __test__ = False
    width: int = 8
    height: int = 8

    def __call__(
        self,
        ds: xr.Dataset,
        path: str | Path,
        **kwargs: Any,
    ) -> str:
        """Write a tiny valid GeoTIFF and return the written path.

        Args:
            ds: Dataset to write (used for time attributes only).
            path: Destination path.
            **kwargs: Additional writer kwargs (ignored).

        Returns:
            The path that was written.
        """
        del ds, kwargs  # unused
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = np.zeros((self.height, self.width), dtype=np.float32)
        transform = Affine.identity() * Affine.scale(1, -1)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype=data.dtype,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data, 1)
        return str(path)
