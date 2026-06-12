"""Built-in batch writer plugins for the AEREO pipeline.

This module provides batch writer plugins that receive the entire patch map
and are responsible for their own iteration, compute scheduling, and memory
management.
"""

from __future__ import annotations

from typing import Any, Mapping, cast

import pandas as pd
from dask.base import compute
from dask.delayed import delayed
import xarray as xr
from aereo.interfaces import BatchWriter, ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from pydantic import Field
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
        job_name: Optional EOIDS job name forwarded to ``WriteGeoTIFF``.
            When omitted, the job name is taken from ``task.job.name``.
        rio_params: Rasterio write options forwarded to ``WriteGeoTIFF``.
        dask_scheduler: Dask scheduler passed to ``dask.compute()`` (e.g.
            ``"threads"``, ``"processes"``, ``"synchronous"`` or ``"distributed"``).
            ``None`` lets Dask pick the default scheduler.
        dask_client: Optional pre-created ``distributed.Client`` to use when
            ``dask_scheduler="distributed"``.  When provided, the scheduler
            defaults to ``"distributed"`` if not already set.
        dask_compute_kwargs: Additional keyword arguments forwarded verbatim to
            ``dask.compute()``.  Useful for setting ``num_workers``,
            ``pool``, ``traverse``, etc.
    """

    job_name: str | None = None
    rio_params: dict[str, object] = {}
    dask_scheduler: str | None = None
    dask_client: Any | None = None
    dask_compute_kwargs: dict[str, Any] = Field(default_factory=dict)

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
            job_name=self.job_name,
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
        compute_kwargs = dict(self.dask_compute_kwargs)
        if self.dask_scheduler is not None:
            compute_kwargs["scheduler"] = self.dask_scheduler
        if self.dask_client is not None:
            compute_kwargs.setdefault("scheduler", "distributed")
            compute_kwargs["client"] = self.dask_client
        computed = compute(*delayed_artifacts, **compute_kwargs)

        # dask.compute() returns a tuple when multiple delayed objects are
        # passed, but returns the result directly for a single object.
        if not computed:
            return ArtifactSchema.empty_geodataframe()
        if not isinstance(computed, tuple):
            computed = (computed,)
        return cast(
            GeoDataFrame[ArtifactSchema],
            pd.concat(list(computed), ignore_index=True),
        )
