"""Core per-task extraction pipeline execution.

Defines :func:`run_task`, the plain per-task pipeline that executes
read -> preprocess -> reproject -> postprocess -> write without caching,
callbacks, or failure-mode wrappers.
"""

from __future__ import annotations

from typing import cast

import geopandas as gpd
import pandas as pd
import xarray as xr

from aereo.interfaces import ExtractionTask
from aereo.interfaces.core import ExtractConfig
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


def _build_artifacts_gdf(
    artifacts: list[GeoDataFrame[ArtifactSchema]],
) -> GeoDataFrame[ArtifactSchema]:
    """Build a validated GeoDataFrame from a list of per-patch artifact frames.

    Args:
        artifacts: Per-patch artifact GeoDataFrames. If empty, an empty
            schema-valid frame is returned.

    Returns:
        A validated GeoDataFrame containing all artifacts.
    """
    if artifacts:
        gdf = gpd.GeoDataFrame(
            pd.concat(artifacts, ignore_index=True),
            geometry="geometry",
        )
    else:
        gdf = gpd.GeoDataFrame(
            columns=list(ArtifactSchema.to_schema().columns.keys()),
            geometry="geometry",
        )
    return cast(GeoDataFrame[ArtifactSchema], gdf)


def run_task(task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
    """Execute the extraction pipeline for a single task.

    Execution order:
        read -> preprocess -> reproject (per task) -> postprocess (per patch) -> write (per patch)

    Args:
        task: The extraction task to execute.

    Returns:
        A ``GeoDataFrame[ArtifactSchema]`` containing all extracted artifacts.

    Raises:
        ValueError: If the pipeline has no reader, or if a reprojector does not
            return a dataset for every patch.
    """
    extract: ExtractConfig = task.extract
    reader = extract.read
    reprojector = extract.reproject
    writer = extract.write
    pre_processors = extract.preprocess
    post_processors = extract.postprocess

    if reader is None:
        raise ValueError("Pipeline must contain a Reader stage.")

    ds = reader(task)

    for proc in pre_processors:
        ds = proc(ds)

    reprojected_map: dict[str, xr.Dataset] | None = None
    if reprojector is not None:
        reprojected_map = reprojector(ds, task)
        if set(reprojected_map) != {p.id for p in task.patches}:
            raise ValueError(
                "Reprojector did not return a dataset for every patch in the task."
            )

    artifacts: list[GeoDataFrame[ArtifactSchema]] = []
    for patch in task.patches:
        ds_patch = reprojected_map[patch.id] if reprojected_map is not None else ds

        for proc in post_processors:
            ds_patch = proc(ds_patch)

        if writer is not None:
            patch_artifacts = writer(ds_patch, task, patch)
            artifacts.append(patch_artifacts)

    return _build_artifacts_gdf(artifacts)
