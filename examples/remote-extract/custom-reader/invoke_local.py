#!/usr/bin/env python3
"""Local invocation script for the custom-reader example.

Build and start the container first:

    cd examples/remote-extract/custom-reader
    docker compose up --build -d

Then run this script to send a direct extraction task to the local HTTP server.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import cast

import geopandas as gpd
import requests
from aereo.grid import ExtractionPatch
from aereo.interfaces import ExtractionTask
from aereo.pipeline import ExtractionJob
from aereo.schemas import AssetSchema
from aereo.executors._serialization import _TaskSerializer
from my_reader import SyntheticReader
from pandera.typing.geopandas import GeoDataFrame
from shapely.geometry import Polygon

URL = "http://localhost:8080/extract"
OUTPUT_PREFIX = "file:///tmp/aereo/output/job-001/0/"


def _make_task() -> ExtractionTask:
    from aereo.builtins.write import write_geotiff

    df = gpd.GeoDataFrame(
        {
            "id": ["asset_1"],
            "collection": ["synthetic"],
            "start_time": [datetime(2023, 1, 1, 12, 0)],
            "end_time": [datetime(2023, 1, 1, 12, 30)],
            "href": ["s3://bucket/key.tif"],
        },
        geometry=[Polygon([[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01]])],
        crs="EPSG:4326",
    )
    patch = ExtractionPatch(
        id="0U_0R",
        d=50_000,
        cell_geometry=Polygon([[0, 0], [0.005, 0], [0.005, 0.005], [0, 0.005]]),
        resolution=100.0,
        margin=0.0,
        padding=0,
    )
    job = ExtractionJob(
        name="custom-reader-job",
        grid_dist=50_000,
        output_uri="/tmp/aereo/output",
        read=SyntheticReader(),
        write=write_geotiff,
    )
    return ExtractionTask(
        assets=cast(GeoDataFrame[AssetSchema], df),
        job=job,
        patches=[patch],
        task_context={"job_id": "custom-reader-job", "chunk_id": 0},
    )


def main() -> int:
    task = _make_task()
    task_bytes = _TaskSerializer().serialize_to_bytes(task)

    payload = {
        "mode": "direct",
        "task": base64.b64encode(task_bytes).decode("ascii"),
        "output_prefix": OUTPUT_PREFIX,
        "job_id": task.task_context["job_id"],
        "chunk_id": task.task_context["chunk_id"],
    }

    print(f"POST {URL}")
    resp = requests.post(URL, json=payload, timeout=60)
    print(f"HTTP {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
