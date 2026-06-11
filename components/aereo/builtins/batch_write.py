"""Built-in batch writer plugins for the AEREO pipeline.

This module provides batch writer plugins that receive the entire patch map
and are responsible for their own iteration, compute scheduling, and memory
management.
"""

from __future__ import annotations

from typing import Mapping, cast

import pandas as pd
import xarray as xr
from aereo.interfaces import BatchWriter, ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


class BatchWriteGeoTIFF(BatchWriter):
    """Writes every patch as a GeoTIFF, releasing each from memory after write."""

    def __call__(
        self,
        patches: Mapping[str, xr.Dataset],
        task: ExtractionTask,
    ) -> GeoDataFrame[ArtifactSchema]:
        """Write *patches* to GeoTIFF files and return artifact metadata.

        Args:
            patches: Mapping from ``patch.id`` to the dataset aligned to that
                patch's geobox.
            task: Extraction task containing the patches and configuration.

        Returns:
            GeoDataFrame of written artifacts with ``ArtifactSchema``.
        """
        from aereo.builtins.write import WriteGeoTIFF

        writer = WriteGeoTIFF()
        artifacts: list[GeoDataFrame[ArtifactSchema]] = []

        callbacks = task.task_context.get("callbacks", [])

        for patch in task.patches:
            ds_patch = patches[patch.id]
            patch_artifacts = writer(ds_patch, task, patch)
            artifacts.append(patch_artifacts)

            # Fire on_patch_write_complete callbacks
            for cb in callbacks:
                cb.on_patch_write_complete(task, patch, patch_artifacts)

            # Explicitly drop lazy graph reference for this patch.
            ds_patch.close()

        if artifacts:
            return cast(
                GeoDataFrame[ArtifactSchema],
                pd.concat(artifacts, ignore_index=True),
            )
        return ArtifactSchema.empty_geodataframe()
