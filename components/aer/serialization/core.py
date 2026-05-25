"""Serialize / deserialize ``ExtractionTask`` for cross-network transport.

Each task is written as a pair of files inside a destination directory:

* ``task_assets.parquet`` – GeoParquet of the task's ``assets`` GeoDataFrame.
* ``task_meta.json``       – JSON with profile, grid config, cells, URI, AOI,
  and task context.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import shapely.wkt
from aer.grid import GridCell
from aer.interfaces import AerProfile, ExtractionTask, GridConfig

logger = logging.getLogger(__name__)


class TaskSerializer:
    """Serialize / deserialize :class:`ExtractionTask` for cross-network transport."""

    ASSETS_NAME = "task_assets.parquet"
    META_NAME = "task_meta.json"

    def serialize(self, task: ExtractionTask, dest_dir: Path) -> None:
        """Write *task* into *dest_dir* as GeoParquet + JSON.

        Args:
            task: The extraction task to persist.
            dest_dir: Directory that will hold ``task_assets.parquet`` and
                ``task_meta.json``.  Created automatically if it does not exist.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Assets → GeoParquet
        task.assets.to_parquet(dest_dir / self.ASSETS_NAME)

        # Grid cells → lightweight dicts
        grid_cells_meta: list[dict[str, Any]] = []
        for cell in task.grid_cells:
            grid_cells_meta.append(
                {
                    "cell_id": cell.id(),
                    "d": cell.D,
                    "is_primary": cell.is_primary,
                    "geom_wkt": cell.geom.wkt,
                }
            )

        # Metadata → JSON
        meta: dict[str, Any] = {
            "profile": task.profile.model_dump(mode="json"),
            "grid_config": task.grid_config.model_dump(mode="json"),
            "grid_cells": grid_cells_meta,
            "uri": task.uri,
            "aoi_wkt": task.aoi.wkt if task.aoi is not None else None,
            "task_context": dict(task.task_context),
        }
        (dest_dir / self.META_NAME).write_text(json.dumps(meta), encoding="utf-8")

        logger.debug(
            f"task_serialized dest_dir={dest_dir} n_assets={len(task.assets)} n_cells={len(task.grid_cells)}"
        )

    def deserialize(self, src_dir: Path) -> ExtractionTask:
        """Reconstruct an :class:`ExtractionTask` from *src_dir*.

        Args:
            src_dir: Directory previously produced by :meth:`serialize`.

        Returns:
            A fully reconstructed ``ExtractionTask``.
        """
        src_dir = Path(src_dir)

        assets = gpd.read_parquet(src_dir / self.ASSETS_NAME)

        meta = json.loads((src_dir / self.META_NAME).read_text(encoding="utf-8"))

        # Reconstruct Pydantic models
        profile = AerProfile.model_validate(meta["profile"])
        grid_config = GridConfig.model_validate(meta["grid_config"])

        # Reconstruct GridCell instances
        grid_cells: list[GridCell] = []
        for cell_meta in meta["grid_cells"]:
            geom = shapely.wkt.loads(cell_meta["geom_wkt"])
            grid_cells.append(
                GridCell(
                    d=cell_meta["d"],
                    geom=geom,  # type: ignore[arg-type]
                    is_primary=cell_meta["is_primary"],
                    cell_id=cell_meta["cell_id"],
                )
            )

        # Reconstruct optional AOI
        aoi = (
            shapely.wkt.loads(meta["aoi_wkt"]) if meta["aoi_wkt"] is not None else None
        )

        return ExtractionTask(
            assets=assets,  # type: ignore[arg-type]
            profile=profile,
            uri=meta["uri"],
            grid_cells=grid_cells,
            grid_config=grid_config,
            aoi=aoi,
            task_context=meta["task_context"],
        )
