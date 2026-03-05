from datetime import datetime, timedelta, timezone
import re
from typing import Any

import s3fs
import geopandas as gpd
from structlog import get_logger

from aer.plugin import plugin
from aer.search import SearchQuery

logger = get_logger()


def _parse_goes_filename(filename: str) -> dict[str, Any]:
    """Parse start and end times from a GOES-R filename.

    Example: OR_ABI-L1b-RadF-M6C01_G16_s202312312345678_e202312312354567_c202312312355432.nc
    """
    match = re.search(r"_s(\d{13})\d*_e(\d{13})\d*_c(\d{13})\d*\.nc", filename)
    if not match:
        return {}

    start_str = match.group(1)
    end_str = match.group(2)

    try:
        start_time = datetime.strptime(start_str, "%Y%j%H%M%S").replace(
            tzinfo=timezone.utc
        )
        end_time = datetime.strptime(end_str, "%Y%j%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return {}

    return {
        "start_time": start_time,
        "end_time": end_time,
    }


@plugin(name="goes_aws", category="search")
def search_goes_aws(query: SearchQuery) -> gpd.GeoDataFrame:
    """Search for GOES ABI products on AWS S3.

    This plugin traverses the NOAA GOES S3 buckets (noaa-goes16, noaa-goes17, etc.)
    by year/day/hour based on the requested time range.
    """
    fs = s3fs.S3FileSystem(anon=True)
    rows = []

    sat_to_bucket = {
        "GOES-16": "noaa-goes16",
        "GOES-17": "noaa-goes17",
        "GOES-18": "noaa-goes18",
        "GOES-19": "noaa-goes19",
    }

    # Generate hourly prefixes to scan
    search_start = query.time_range.start.replace(minute=0, second=0, microsecond=0)
    search_end = query.time_range.end

    current_hour = search_start
    hourly_steps = []
    while current_hour <= search_end:
        hourly_steps.append(current_hour)
        current_hour += timedelta(hours=1)

    for product in query.products:
        # Only support ABI L1b for now
        if not product.name.startswith("ABI-L1b-Rad"):
            continue

        for satellite in product.supported_satellites:
            bucket = sat_to_bucket.get(satellite.name)
            if not bucket:
                continue

            for h in hourly_steps:
                # AWS path: <product>/<year>/<day>/<hour>/
                prefix = f"{bucket}/{product.name}/{h.year}/{h.strftime('%j')}/{h.strftime('%H')}/"
                try:
                    files = fs.ls(prefix, detail=True)
                    for f_info in files:
                        f_path = f_info["name"]
                        if not f_path.endswith(".nc"):
                            continue

                        filename = f_path.split("/")[-1]
                        meta = _parse_goes_filename(filename)

                        if not meta:
                            continue

                        # Filter by exact time range
                        if (
                            meta["start_time"] > query.time_range.end
                            or meta["end_time"] < query.time_range.start
                        ):
                            continue

                        rows.append(
                            {
                                "product_name": product.name,
                                "granule_id": filename,
                                "concept_id": f"{satellite.name}_{product.name}",
                                "start_time": meta["start_time"],
                                "end_time": meta["end_time"],
                                "s3_url": f"s3://{f_path}",
                                "https_url": f"https://{bucket}.s3.amazonaws.com/{f_path.replace(bucket + '/', '')}",
                                "size_mb": f_info["size"] / (1024 * 1024),
                                "geometry": None,
                            }
                        )
                except Exception as e:
                    logger.debug(
                        "S3 prefix not found or error", prefix=prefix, error=str(e)
                    )

    if not rows:
        return gpd.GeoDataFrame(
            columns=[
                "product_name",
                "granule_id",
                "concept_id",
                "start_time",
                "end_time",
                "s3_url",
                "https_url",
                "size_mb",
                "geometry",
            ],
            geometry="geometry",
        )

    return gpd.GeoDataFrame(rows, geometry="geometry")
