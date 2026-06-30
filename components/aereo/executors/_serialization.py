"""Internal serialization helpers for remote executors.

Each task is written as a pair of files inside a destination directory:

* ``task_assets.parquet`` – GeoParquet of the task's ``assets`` GeoDataFrame.
* ``task_meta.json``       – JSON with job configuration, including reader,
  writer, and optional step callables and kwargs.

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

        task.assets.to_parquet(dest_dir / self.ASSETS_NAME)

        job = task.job
        meta: dict[str, Any] = {
            "id": task.id,
            "task_context": task.task_context,
            "aoi_wkt": (
                cast(BaseGeometry, task.aoi).wkt if task.aoi is not None else None
            ),
            "job": {
                "name": job.name,
                "grid_dist": job.grid_dist,
                "output_uri": job.output_uri,
                "overwrite": job.overwrite,
                "target_aoi_wkt": (
                    cast(BaseGeometry, job.target_aoi).wkt
                    if job.target_aoi is not None
                    else None
                ),
                "resolution": job.resolution,
                "margin": job.margin,
                "read": PluginSerializer.dumps(job.read),
                "read_kwargs": job.read_kwargs,
                "preprocess": PluginSerializer.dumps(job.preprocess),
                "preprocess_kwargs": job.preprocess_kwargs,
                "reproject": PluginSerializer.dumps(job.reproject),
                "reproject_kwargs": job.reproject_kwargs,
                "reproject_mode": job.reproject_mode,
                "postprocess": PluginSerializer.dumps(job.postprocess),
                "postprocess_kwargs": job.postprocess_kwargs,
                "write": PluginSerializer.dumps(job.write),
                "write_kwargs": job.write_kwargs,
            },
        }
        (dest_dir / self.META_NAME).write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )

        logger.debug(
            "task_serialized dest_dir=%s n_assets=%d",
            dest_dir,
            len(task.assets),
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

        job_meta = meta["job"]
        target_aoi_wkt = job_meta.get("target_aoi_wkt")
        target_aoi = (
            shapely.wkt.loads(target_aoi_wkt) if target_aoi_wkt is not None else None
        )

        aoi_wkt = meta.get("aoi_wkt")
        aoi = shapely.wkt.loads(aoi_wkt) if aoi_wkt is not None else None

        from aereo.pipeline import ExtractionJob

        job = ExtractionJob.model_validate(
            {
                "name": job_meta.get("name", "default"),
                "grid_dist": job_meta["grid_dist"],
                "output_uri": job_meta["output_uri"],
                "overwrite": job_meta.get("overwrite", False),
                "target_aoi": target_aoi,
                "resolution": job_meta.get("resolution"),
                "margin": job_meta.get("margin"),
                "read": cast(Reader, PluginSerializer.loads(job_meta["read"])),
                "read_kwargs": job_meta.get("read_kwargs"),
                "preprocess": PluginSerializer.loads(job_meta.get("preprocess")),
                "preprocess_kwargs": job_meta.get("preprocess_kwargs"),
                "reproject": PluginSerializer.loads(job_meta.get("reproject")),
                "reproject_kwargs": job_meta.get("reproject_kwargs"),
                "reproject_mode": job_meta.get("reproject_mode"),
                "postprocess": PluginSerializer.loads(job_meta.get("postprocess")),
                "postprocess_kwargs": job_meta.get("postprocess_kwargs"),
                "write": cast(Writer, PluginSerializer.loads(job_meta["write"])),
                "write_kwargs": job_meta.get("write_kwargs"),
            }
        )

        return ExtractionTask(
            id=meta.get("id", "remote-task"),
            assets=assets,  # type: ignore[arg-type]
            job=job,
            aoi=aoi,
            task_context=meta.get("task_context", {}),
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
