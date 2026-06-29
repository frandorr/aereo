"""Core per-task extraction pipeline execution.

Defines :func:`run_task`, the plain per-task pipeline that executes
read -> write without caching, callbacks, or failure-mode wrappers.
"""

from __future__ import annotations

from typing import cast

import geopandas as gpd
import pandas as pd

from aereo.interfaces import ExtractionTask
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
        read -> write (per patch)

    Args:
        task: The extraction task to execute.

    Returns:
        A ``GeoDataFrame[ArtifactSchema]`` containing all extracted artifacts.

    Raises:
        ValueError: If the pipeline has no reader.
    """
    reader = task.read
    writer = task.write

    if reader is None:
        raise ValueError("Pipeline must contain a Reader stage.")

    ds = reader(task)

    artifacts: list[GeoDataFrame[ArtifactSchema]] = []
    for patch in task.patches:
        if writer is not None:
            patch_artifacts = writer(ds, task, patch)
            artifacts.append(patch_artifacts)

    return _build_artifacts_gdf(artifacts)
