"""Built-in batch writer plugins for the AEREO pipeline.

This module provides batch writer plugins that receive the entire patch map
and are responsible for their own iteration, compute scheduling, and memory
management.
"""

from __future__ import annotations

from typing import Mapping, cast

import pandas as pd
from dask.base import compute
from dask.delayed import delayed
import xarray as xr
from aereo.interfaces import BatchWriter, ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class BatchWriteGeoTIFF(BatchWriter):
    """Writes every patch as a GeoTIFF, batching Dask compute across all patches.

    Instead of computing each patch's Dask graph individually (as the per-patch
    ``Writer`` path does), this writer builds a lazy ``dask.delayed`` task for
    each patch and then calls ``dask.compute()`` once on all of them.  Dask
    merges the graphs and schedules work across its thread/process pool,
    reducing overhead and improving throughput when many patches share
    upstream dependencies.

    Attributes:
        profile_name: EOIDS profile name forwarded to ``WriteGeoTIFF``.
        rio_params: Rasterio write options forwarded to ``WriteGeoTIFF``.
    """

    profile_name: str = "default"
    rio_params: dict[str, object] = {}

    def __call__(
        self,
        patches: Mapping[str, xr.Dataset],
        task: ExtractionTask,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *patches* to GeoTIFF files and return artifact metadata.

        Builds a lazy write task per patch, then calls ``dask.compute()``
        to evaluate them all in one graph.

        Args:
            patches: Mapping from ``patch.id`` to the dataset aligned to that
                patch's geobox.
            task: Extraction task containing the patches and configuration.

        Returns:
            GeoDataFrame of written artifacts with ``ArtifactSchema``.
        """
        from aereo.builtins.write import WriteGeoTIFF

        writer = WriteGeoTIFF(
            profile_name=self.profile_name,
            rio_params=dict(self.rio_params),
        )
        callbacks = task.task_context.get("callbacks", [])

        @delayed
        def _write_one(patch_id: str) -> GeoDataFrame[ArtifactSchema]:
            ds_patch = patches[patch_id]
            patch = next(p for p in task.patches if p.id == patch_id)
            patch_artifacts = writer(ds_patch, task, patch)
            for cb in callbacks:
                cb.on_patch_write_complete(task, patch, patch_artifacts)
            return patch_artifacts

        delayed_artifacts = [_write_one(p.id) for p in task.patches]
        computed = compute(*delayed_artifacts)

        if computed:
            return cast(
                GeoDataFrame[ArtifactSchema],
                pd.concat(list(computed), ignore_index=True),
            )
        return ArtifactSchema.empty_geodataframe()
