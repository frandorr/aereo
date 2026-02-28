import earthaccess
import pandas as pd
from typing import Any

from aer.temporal import TimeRange
from aer.spectral import Product


def search_earthaccess(
    products: list[Product], time_range: TimeRange, **kwargs: Any
) -> pd.DataFrame:
    """
    Search for earthaccess data given a list of Products and a TimeRange.
    Returns a pandas DataFrame with the search results.

    Args:
        products: A list of spectral Products to search for (uses product.name).
        time_range: The TimeRange representing start and end time.
        **kwargs: Additional parameters passed directly to earthaccess.search_data.

    Returns:
        A pd.DataFrame containing product name, start time, end time, s3 urls, and sizes.
    """
    temporal = (
        time_range.start.strftime("%Y-%m-%d %H:%M:%S"),
        time_range.end.strftime("%Y-%m-%d %H:%M:%S"),
    )

    short_names = [p.name for p in products]

    results = earthaccess.search_data(
        short_name=short_names, temporal=temporal, **kwargs
    )

    if not results:
        return pd.DataFrame(
            columns=[
                "product_name",
                "granule_id",
                "concept_id",
                "start_time",
                "end_time",
                "s3_url",
                "https_url",
                "size_mb",
            ]
        )

    rows = []
    for granule in results:
        meta = granule.get("meta", {})
        umm = granule.get("umm", {})

        # Get data links
        direct_links = granule.data_links(access="direct")
        external_links = granule.data_links(access="external")

        s3_url = direct_links[0] if direct_links else None
        https_url = external_links[0] if external_links else None

        # Temporal extents
        temporal_ext = umm.get("TemporalExtent", {})
        range_dt = temporal_ext.get("RangeDateTime", {})
        start_time = range_dt.get("BeginningDateTime")
        end_time = range_dt.get("EndingDateTime")

        # Determine exact product name from UMM metadata
        coll_ref = umm.get("CollectionReference", {})
        extracted_product_name = coll_ref.get("ShortName")

        rows.append(
            {
                "product_name": extracted_product_name,
                "granule_id": meta.get("native-id"),
                "concept_id": meta.get("concept-id"),
                "start_time": pd.to_datetime(start_time) if start_time else None,
                "end_time": pd.to_datetime(end_time) if end_time else None,
                "s3_url": s3_url,
                "https_url": https_url,
                "size_mb": granule.size(),
            }
        )

    return pd.DataFrame(rows)
