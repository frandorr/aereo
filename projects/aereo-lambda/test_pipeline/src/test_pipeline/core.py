"""Synthetic pipeline plugins for AEREO Lambda integration testing.

These plugins require no network access and produce tiny, deterministic
GeoTIFF artifacts so the Lambda handler's S3 upload path can be exercised
end-to-end without relying on external data sources.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from aereo.eoids import build_eoids_path
from aereo.grid import ExtractionPatch
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import box


class TestReader:
    """Reader that returns a tiny synthetic xarray.Dataset."""

    __test__ = False
    width: int = 8
    height: int = 8

    def __init__(self, width: int = 8, height: int = 8) -> None:
        self.width = width
        self.height = height

    def __call__(self, task: ExtractionTask) -> xr.Dataset:
        """Return a synthetic dataset for testing.

        Args:
            task: Extraction task (unused, but required by the interface).

        Returns:
            A small xarray.Dataset tagged with start/end time attributes.
        """
        del task  # unused
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
    """Identity reprojector that maps every patch to the source dataset."""

    __test__ = False

    def __call__(
        self,
        ds: xr.Dataset,
        task: ExtractionTask,
    ) -> dict[str, xr.Dataset]:
        """Return the input dataset unchanged for every patch.

        Args:
            ds: Source dataset.
            task: Task containing the patches to reproject.

        Returns:
            Mapping from patch ID to the source dataset.
        """
        return {patch.id: ds for patch in task.patches}


class TestWriter:
    """Writer that creates an empty GeoTIFF file and returns artifact metadata."""

    __test__ = False

    def __call__(
        self,
        ds: xr.Dataset,
        task: ExtractionTask,
        patch: ExtractionPatch,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write a placeholder GeoTIFF and return artifact metadata.

        Args:
            ds: Dataset for the patch.
            task: Task providing the output URI and job metadata.
            patch: Patch being written.

        Returns:
            GeoDataFrame with one artifact row pointing at the written file.
        """
        start_time = ds.attrs.get("start_time")
        end_time = ds.attrs.get("end_time")
        out_path = build_eoids_path(
            local_dir=task.output_uri,
            job_name=task.job.name,
            resolution=patch.resolution,
            collections=["test"],
            variables=["band1"],
            cell_id=patch.id,
            start_time=start_time,
            end_time=end_time,
            suffix="tif",
        )
        out_path.write_bytes(b"")  # placeholder bytes; upload path only needs a file

        record: dict[str, Any] = {
            "id": f"{patch.id}_band1",
            "source_ids": ",".join(sorted({str(aid) for aid in task.assets["id"]})),
            "start_time": start_time,
            "end_time": end_time,
            "uri": str(out_path),
            "collection": "test",
            "geometry": box(*patch.cell_geometry.bounds),
            "grid_cell": patch.id,
            "grid_dist": patch.d,
            "cell_geometry": patch.cell_geometry,
            "cell_utm_crs": patch.utm_crs,
            "cell_utm_footprint": patch.utm_footprint,
        }
        gdf = gpd.GeoDataFrame([record], geometry="geometry", crs="EPSG:4326")
        return GeoDataFrame[ArtifactSchema](gdf)
