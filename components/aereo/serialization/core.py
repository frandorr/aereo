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
from aereo.grid import GridCell
from aereo.interfaces import AereoProfile, ExtractionTask, GridConfig

logger = logging.getLogger(__name__)


class TaskSerializer:
    """Serialize / deserialize :class:`ExtractionTask` for cross-network transport."""

    ASSETS_NAME = "task_assets.parquet"
    META_NAME = "task_meta.json"

    # JSON field keys for serialize / deserialize parity
    CELL_ID_KEY = "cell_id"
    D_KEY = "d"
    IS_PRIMARY_KEY = "is_primary"
    GEOM_WKT_KEY = "geom_wkt"
    PROFILE_KEY = "profile"
    GRID_CONFIG_KEY = "grid_config"
    GRID_CELLS_KEY = "grid_cells"
    URI_KEY = "uri"
    AOI_WKT_KEY = "aoi_wkt"
    TASK_CONTEXT_KEY = "task_context"

    def serialize(self, task: ExtractionTask, dest_dir: Path) -> None:
        """Write *task* into *dest_dir* as GeoParquet + JSON.

        Args:
            task: The extraction task to persist.
            dest_dir: Directory that will hold ``task_assets.parquet`` and
                ``task_meta.json``.  Created automatically if it does not exist.

        Returns:
            None

        Raises:
            OSError: If the destination directory cannot be created.
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
                    self.CELL_ID_KEY: cell.id(),
                    self.D_KEY: cell.D,
                    self.IS_PRIMARY_KEY: cell.is_primary,
                    self.GEOM_WKT_KEY: cell.geom.wkt,
                }
            )

        # Metadata → JSON
        meta: dict[str, Any] = {
            self.PROFILE_KEY: task.profile.model_dump(mode="json"),
            self.GRID_CONFIG_KEY: task.grid_config.model_dump(mode="json"),
            self.GRID_CELLS_KEY: grid_cells_meta,
            self.URI_KEY: task.uri,
            self.AOI_WKT_KEY: task.aoi.wkt if task.aoi is not None else None,
            self.TASK_CONTEXT_KEY: dict(task.task_context),
        }
        (dest_dir / self.META_NAME).write_text(
            json.dumps(meta, default=str), encoding="utf-8"
        )

        logger.debug(
            f"task_serialized dest_dir={dest_dir} n_assets={len(task.assets)} n_cells={len(task.grid_cells)}"
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

        # Reconstruct Pydantic models
        profile = AereoProfile.model_validate(meta[self.PROFILE_KEY])
        grid_config = GridConfig.model_validate(meta[self.GRID_CONFIG_KEY])

        # Reconstruct GridCell instances
        grid_cells: list[GridCell] = []
        for cell_meta in meta[self.GRID_CELLS_KEY]:
            geom = shapely.wkt.loads(cell_meta[self.GEOM_WKT_KEY])
            grid_cells.append(
                GridCell(
                    d=cell_meta[self.D_KEY],
                    geom=geom,  # type: ignore[arg-type]
                    is_primary=cell_meta[self.IS_PRIMARY_KEY],
                    cell_id=cell_meta[self.CELL_ID_KEY],
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
            profile=profile,
            uri=meta[self.URI_KEY],
            grid_cells=grid_cells,
            grid_config=grid_config,
            aoi=aoi,
            task_context=meta[self.TASK_CONTEXT_KEY],
        )
