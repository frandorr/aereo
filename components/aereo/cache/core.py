"""Per-task artifact-catalog cache for AEREO extraction tasks.

This module provides :class:`TaskResultCache`, which stores the artifact
GeoDataFrame produced by a single :class:`~aereo.interfaces.ExtractionTask`
as a small parquet file. When a task is run again with ``overwrite=False``,
the cache is checked first and, if present, its contents are returned without
re-executing the read/reproject/write pipeline.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import filelock
import geopandas as gpd
from aereo.executors._serialization import PluginSerializer
from aereo.interfaces import ExtractionTask
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame


def _geometry_to_wkt(geom: Any) -> str | None:
    """Return a WKT string for a Shapely geometry, or None."""
    if geom is None:
        return None
    return geom.wkt


def _model_dump(plugin: Any) -> dict[str, Any] | None:
    """Serialize a plugin callable to a JSON-compatible dict."""
    return PluginSerializer.dumps(plugin)


class TaskResultCache:
    """Cache artifact catalogs per extraction task.

    The cache is stored under ``<task.output_uri>/.aereo_cache/tasks/`` as
    ``<fingerprint>.parquet``. The fingerprint is a SHA-256 hash of a
    deterministic, JSON-serializable representation of everything that affects
    the task's output: job configuration, assets, patches, AOI, and task
    context.
    """

    _CACHE_DIR_NAME = ".aereo_cache"
    _TASKS_DIR_NAME = "tasks"

    def _cache_dir(self, task: ExtractionTask) -> Path:
        """Return the directory where a task's cache file is stored."""
        return (
            Path(task.output_uri).resolve()
            / self._CACHE_DIR_NAME
            / self._TASKS_DIR_NAME
        )

    def path(self, task: ExtractionTask) -> Path:
        """Return the cache file path for *task*."""
        return self._cache_dir(task) / f"{self.fingerprint(task)}.parquet"

    def fingerprint(self, task: ExtractionTask) -> str:
        """Compute a stable SHA-256 fingerprint for *task*.

        The fingerprint includes the full job configuration (including the
        extract pipeline), the assets, the patches, the AOI, and the task
        context. This ensures that changes to postprocessors, variables, or
        any other output-affecting setting invalidate the cache.
        """
        job = task.job

        job_data: dict[str, Any] = {
            "name": job.name,
            "grid_dist": job.grid_dist,
            "output_uri": job.output_uri,
            "target_aoi": _geometry_to_wkt(job.target_aoi),
            # overwrite is a runtime control, not an output characteristic.
            "read": _model_dump(job.read),
            "write": _model_dump(job.write),
        }

        assets_df = task.assets.copy()
        sort_cols = ["id"]
        assets_df = assets_df.sort_values(by=sort_cols, kind="mergesort").reset_index(
            drop=True
        )
        asset_cols = ["id", "collection", "start_time", "end_time"]
        if "channel_id" in assets_df.columns:
            asset_cols.append("channel_id")
        # Only keep columns we know are stable identifiers; ignore geometry and
        # hrefs, because signed URLs (e.g. Planetary Computer SAS tokens) change
        # on every search and would otherwise invalidate the cache each session.
        assets_data = cast(
            list[dict[str, Any]],
            assets_df[asset_cols].to_dict(orient="records"),  # pyright: ignore[reportCallIssue]
        )

        patches_data = [
            {
                "id": patch.id,
                "cell_geometry": _geometry_to_wkt(patch.cell_geometry),
                "resolution": patch.resolution,
                "margin": patch.margin,
                "padding": patch.padding,
                "conform_to": patch.conform_to,
            }
            for patch in sorted(task.patches, key=lambda p: p.id)
        ]

        task_context = dict(task.task_context)
        # Callbacks are injected at runtime and do not affect output.
        task_context.pop("callbacks", None)

        payload: dict[str, Any] = {
            "job": job_data,
            "assets": assets_data,
            "patches": patches_data,
            "aoi": _geometry_to_wkt(task.aoi),
            "task_context": task_context,
        }

        json_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(json_bytes).hexdigest()

    def load(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema] | None:
        """Load cached artifacts for *task* if they exist.

        Returns:
            The cached artifact GeoDataFrame, or ``None`` if no cache exists.
            The caller is responsible for schema validation, matching the
            behaviour of the rest of the pipeline.
        """
        cache_path = self.path(task)
        if not cache_path.exists():
            return None

        return cast(GeoDataFrame[ArtifactSchema], gpd.read_parquet(cache_path))

    def save(
        self, task: ExtractionTask, artifacts: GeoDataFrame[ArtifactSchema]
    ) -> None:
        """Save *artifacts* as the cache entry for *task*.

        Uses a file lock so that concurrent writers for the same task do not
        corrupt the cache file.
        """
        cache_path = self.path(task)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
        with filelock.FileLock(str(lock_path), timeout=60):
            artifacts.to_parquet(cache_path)
