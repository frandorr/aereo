"""Internal serialization helpers for remote executors.

Each task is written as a pair of files inside a destination directory:

* ``task_assets.parquet`` – GeoParquet of the task's ``assets`` GeoDataFrame.
* ``task_meta.json``       – JSON with profile, grid config, patches, URI, AOI,
  and task context.

These helpers are implementation details of the remote executors and are not
part of the public AEREO API.
"""

from __future__ import annotations

import importlib
import io
import json
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import shapely.wkt
from aereo.grid import ExtractionPatch
from shapely.geometry.base import BaseGeometry
from aereo.interfaces import ExtractionTask
from aereo.interfaces.core import (
    Reader,
    Writer,
)

logger = logging.getLogger(__name__)


class PluginSerializer:
    """Serialize / deserialize Callable / partial instances for task transport."""

    CLASS_KEY = "__plugin_class__"
    CONFIG_KEY = "config"

    @classmethod
    def dumps(cls, plugin: Any | None) -> dict[str, Any] | None:
        """Serialize a plugin (Callable or partial) to a JSON-safe dict.

        Args:
            plugin: Callable or partial instance to serialize, or ``None``.

        Returns:
            A dict with ``__plugin_class__`` and ``config`` keys, or ``None``.
        """
        if plugin is None:
            return None

        import functools

        if isinstance(plugin, functools.partial):
            func = plugin.func
            config = dict(plugin.keywords)
        else:
            func = plugin
            config = {}

        # If it's a class with a __call__, or function
        if hasattr(func, "__qualname__"):
            qualname = func.__qualname__
            module = func.__module__
        else:
            qualname = type(func).__name__
            module = type(func).__module__

        return {
            cls.CLASS_KEY: f"{module}.{qualname}",
            cls.CONFIG_KEY: config,
        }

    @classmethod
    def loads(cls, plugin_data: dict[str, Any] | None) -> Any | None:
        """Reconstruct a plugin Callable from its serialized dict.

        Args:
            plugin_data: Serialized plugin dict, or ``None``.

        Returns:
            A Callable instance, or ``None``.
        """
        import functools
        import inspect

        if not plugin_data:
            return None

        cls_path = plugin_data[cls.CLASS_KEY]
        config = plugin_data[cls.CONFIG_KEY]
        module_name, class_name = cls_path.rsplit(".", 1)
        module = importlib.import_module(module_name)

        parts = class_name.split(".")
        obj = module
        for part in parts:
            obj = getattr(obj, part)

        if not callable(obj):
            raise ImportError(f"Resolved target '{cls_path}' is not callable.")
        if inspect.isclass(obj):
            return obj(**config)
        if config:
            return functools.partial(obj, **config)
        return obj


class _TaskSerializer:
    """Serialize / deserialize :class:`ExtractionTask` for cross-network transport."""

    ASSETS_NAME = "task_assets.parquet"
    META_NAME = "task_meta.json"

    # JSON field keys for serialize / deserialize parity
    CELL_ID_KEY = "cell_id"
    D_KEY = "d"
    GEOM_WKT_KEY = "geom_wkt"
    RESOLUTION_KEY = "resolution"
    MARGIN_KEY = "margin"
    PADDING_KEY = "padding"
    CONFORM_TO_KEY = "conform_to"

    READ_KEY = "read"
    WRITE_KEY = "write"
    GRID_DIST_KEY = "grid_dist"
    PATCHES_KEY = "patches"
    OUTPUT_URI_KEY = "output_uri"
    URI_KEY = "uri"  # legacy key for backward-compatible deserialization
    AOI_WKT_KEY = "aoi_wkt"
    TASK_CONTEXT_KEY = "task_context"
    JOB_NAME_KEY = "job_name"
    TARGET_AOI_WKT_KEY = "target_aoi_wkt"

    def serialize(self, task: ExtractionTask, dest_dir: Path) -> None:
        """Write *task* into *dest_dir* as GeoParquet + JSON.

        Args:
            task: The extraction task to persist.
            dest_dir: Directory that will hold ``task_assets.parquet`` and
                ``task_meta.json``.  Created automatically if it does not exist.

        Raises:
            OSError: If the destination directory cannot be created.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Assets → GeoParquet
        task.assets.to_parquet(dest_dir / self.ASSETS_NAME)

        # Patches → lightweight dicts
        patches_meta: list[dict[str, Any]] = [
            {
                self.CELL_ID_KEY: patch.id,
                self.D_KEY: patch.d,
                self.GEOM_WKT_KEY: patch.cell_geometry.wkt,
                self.RESOLUTION_KEY: patch.resolution,
                self.MARGIN_KEY: patch.margin,
                self.PADDING_KEY: patch.padding,
                self.CONFORM_TO_KEY: patch.conform_to,
            }
            for patch in task.patches
        ]

        # Metadata → JSON
        meta: dict[str, Any] = {
            self.READ_KEY: PluginSerializer.dumps(task.read),
            self.WRITE_KEY: PluginSerializer.dumps(task.write),
            self.GRID_DIST_KEY: task.grid_dist,
            self.PATCHES_KEY: patches_meta,
            self.OUTPUT_URI_KEY: task.output_uri,
            self.AOI_WKT_KEY: task.aoi.wkt if task.aoi is not None else None,
            self.TASK_CONTEXT_KEY: dict(task.task_context),
            self.JOB_NAME_KEY: task.job.name,
            self.TARGET_AOI_WKT_KEY: (
                cast(BaseGeometry, task.job.target_aoi).wkt
                if task.job.target_aoi is not None
                else None
            ),
        }
        (dest_dir / self.META_NAME).write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )

        logger.debug(
            "task_serialized dest_dir=%s n_assets=%d n_patches=%d",
            dest_dir,
            len(task.assets),
            len(task.patches),
        )

    def deserialize(self, src_dir: Path) -> ExtractionTask:
        """Reconstruct an :class:`ExtractionTask` from *src_dir*.

        Args:
            src_dir: Directory previously produced by :meth:`serialize`.

        Returns:
            A fully reconstructed ``ExtractionTask``.

        Raises:
            FileNotFoundError: If the source directory or required files are missing.
            json.JSONDecodeError: If ``task_meta.json`` is malformed.
            ValidationError: If the stored metadata fails Pydantic validation.
        """
        src_dir = Path(src_dir)

        assets = gpd.read_parquet(src_dir / self.ASSETS_NAME)

        meta = json.loads((src_dir / self.META_NAME).read_text(encoding="utf-8"))

        # Reconstruct the parent ExtractionJob from serialized metadata.
        target_aoi_wkt = meta.get(self.TARGET_AOI_WKT_KEY)
        target_aoi = (
            shapely.wkt.loads(target_aoi_wkt) if target_aoi_wkt is not None else None
        )
        from aereo.pipeline import ExtractionJob

        job = ExtractionJob.model_validate(
            {
                "name": meta.get(self.JOB_NAME_KEY, "default"),
                "grid_dist": meta[self.GRID_DIST_KEY],
                "output_uri": meta.get(self.OUTPUT_URI_KEY, meta.get(self.URI_KEY)),
                "read": cast(Reader, PluginSerializer.loads(meta[self.READ_KEY])),
                "write": cast(
                    Writer | None, PluginSerializer.loads(meta[self.WRITE_KEY])
                ),
                "target_aoi": target_aoi,
            }
        )

        # Reconstruct ExtractionPatch instances
        patches: list[ExtractionPatch] = []
        for patch_meta in meta[self.PATCHES_KEY]:
            geom = shapely.wkt.loads(patch_meta[self.GEOM_WKT_KEY])
            patches.append(
                ExtractionPatch(
                    id=patch_meta[self.CELL_ID_KEY],
                    d=patch_meta[self.D_KEY],
                    cell_geometry=geom,  # type: ignore[arg-type]
                    resolution=patch_meta[self.RESOLUTION_KEY],
                    margin=patch_meta[self.MARGIN_KEY],
                    padding=patch_meta[self.PADDING_KEY],
                    conform_to=patch_meta.get(self.CONFORM_TO_KEY),
                )
            )

        # Reconstruct optional AOI
        aoi = (
            shapely.wkt.loads(meta[self.AOI_WKT_KEY])
            if meta[self.AOI_WKT_KEY] is not None
            else None
        )

        return ExtractionTask(
            assets=assets,  # type: ignore[arg-type]
            job=job,
            patches=patches,
            aoi=aoi,
            task_context=meta[self.TASK_CONTEXT_KEY],
        )

    def serialize_to_bytes(self, task: ExtractionTask) -> bytes:
        """Serialize *task* to an in-memory zip of GeoParquet + JSON.

        Args:
            task: The extraction task to serialize.

        Returns:
            Bytes containing a zip archive with ``task_assets.parquet`` and
            ``task_meta.json``.
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            with tempfile.TemporaryDirectory() as tmpdir:
                task_dir = Path(tmpdir)
                self.serialize(task, task_dir)
                zf.write(task_dir / self.ASSETS_NAME, self.ASSETS_NAME)
                zf.write(task_dir / self.META_NAME, self.META_NAME)
        return buffer.getvalue()

    def deserialize_from_bytes(self, data: bytes) -> ExtractionTask:
        """Reconstruct an :class:`ExtractionTask` from a zip byte payload.

        Args:
            data: Bytes previously produced by :meth:`serialize_to_bytes`.

        Returns:
            A fully reconstructed ``ExtractionTask``.
        """
        buffer = io.BytesIO(data)
        with tempfile.TemporaryDirectory() as tmpdir:
            task_dir = Path(tmpdir)
            with zipfile.ZipFile(buffer, "r") as zf:
                zf.extractall(task_dir)
            return self.deserialize(task_dir)
