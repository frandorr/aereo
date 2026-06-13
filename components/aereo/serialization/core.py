"""Serialize / deserialize ``ExtractionTask`` for cross-network transport.

Each task is written as a pair of files inside a destination directory:

* ``task_assets.parquet`` – GeoParquet of the task's ``assets`` GeoDataFrame.
* ``task_meta.json``       – JSON with profile, grid config, patches, URI, AOI,
  and task context.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import shapely.wkt
from aereo.grid import ExtractionPatch
from shapely.geometry.base import BaseGeometry
from aereo.interfaces import AereoPlugin, ExtractionTask
from aereo.pipeline import ExtractionJob

logger = logging.getLogger(__name__)


class TaskSerializer:
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

    EXTRACT_KEY = "extract"
    GRID_CONFIG_KEY = "grid_config"
    PATCH_CONFIG_KEY = "patch_config"
    PATCHES_KEY = "patches"
    OUTPUT_URI_KEY = "output_uri"
    URI_KEY = "uri"  # legacy key for backward-compatible deserialization
    AOI_WKT_KEY = "aoi_wkt"
    TASK_CONTEXT_KEY = "task_context"
    JOB_NAME_KEY = "job_name"
    DERIVATIVE_KEY = "derivative"
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

        def serialize_plugin(plugin: AereoPlugin | None) -> dict[str, Any] | None:
            if plugin is None:
                return None
            return {
                "__plugin_class__": f"{type(plugin).__module__}.{type(plugin).__name__}",
                "config": plugin.model_dump(mode="json"),
            }

        # ExtractConfig → dicts with class paths
        extract_meta = {
            "read": serialize_plugin(task.extract.read),
            "preprocess": [serialize_plugin(p) for p in task.extract.preprocess],
            "reproject": serialize_plugin(task.extract.reproject),
            "postprocess": [serialize_plugin(p) for p in task.extract.postprocess],
            "write": serialize_plugin(task.extract.write),
        }

        # Metadata → JSON
        meta: dict[str, Any] = {
            self.EXTRACT_KEY: extract_meta,
            self.GRID_CONFIG_KEY: task.grid_config.model_dump(mode="json"),
            self.PATCH_CONFIG_KEY: task.patch_config.model_dump(mode="json"),
            self.PATCHES_KEY: patches_meta,
            self.OUTPUT_URI_KEY: task.output_uri,
            self.AOI_WKT_KEY: task.aoi.wkt if task.aoi is not None else None,
            self.TASK_CONTEXT_KEY: dict(task.task_context),
            self.JOB_NAME_KEY: task.job.name,
            self.DERIVATIVE_KEY: task.job.derivative,
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

        def deserialize_plugin(
            plugin_data: dict[str, Any] | None,
        ) -> AereoPlugin | None:
            if not plugin_data:
                return None
            cls_path = plugin_data["__plugin_class__"]
            config = plugin_data["config"]
            module_name, class_name = cls_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            return cls.model_validate(config)

        # Reconstruct ExtractConfig
        extract_data = meta[self.EXTRACT_KEY]

        from aereo.interfaces.core import (
            BatchWriter,
            ExtractConfig,
            Processor,
            Reader,
            Reprojector,
            Writer,
        )

        extract = ExtractConfig(
            read=cast(Reader, deserialize_plugin(extract_data["read"])),
            preprocess=[
                cast(Processor, deserialize_plugin(p))
                for p in extract_data["preprocess"]
            ],
            reproject=cast(
                Reprojector | None, deserialize_plugin(extract_data["reproject"])
            ),
            postprocess=[
                cast(Processor, deserialize_plugin(p))
                for p in extract_data["postprocess"]
            ],
            write=cast(
                Writer | BatchWriter | None,
                deserialize_plugin(extract_data["write"]),
            ),
        )

        # Reconstruct the parent ExtractionJob from serialized metadata.
        target_aoi_wkt = meta.get(self.TARGET_AOI_WKT_KEY)
        target_aoi = (
            shapely.wkt.loads(target_aoi_wkt) if target_aoi_wkt is not None else None
        )
        job = ExtractionJob.model_validate(
            {
                "name": meta.get(self.JOB_NAME_KEY, "default"),
                "derivative": meta.get(self.DERIVATIVE_KEY),
                "grid_config": meta[self.GRID_CONFIG_KEY],
                "patch_config": meta[self.PATCH_CONFIG_KEY],
                "output_uri": meta.get(self.OUTPUT_URI_KEY, meta.get(self.URI_KEY)),
                "search": None,
                "extract": extract,
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
