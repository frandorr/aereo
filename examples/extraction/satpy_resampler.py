# %%
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from aer.client import AerClient
from aer.grid import GridDefinition
from aer.interfaces import AerProfile, GridConfig
from aer.search_earthaccess import earthaccess_download_wrapper

# --- Configuration ---
DATE_START = datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc)
DATE_END = datetime(2026, 4, 3, 0, 0, tzinfo=timezone.utc)

# Shared AOI — path relative to this script so it works regardless of CWD
try:
    geojson_path = Path(__file__).parent / ".." / "data" / "chocon.geojson"
except NameError:
    geojson_path = Path().resolve() / "examples" / "data" / "chocon.geojson"

gdf = gpd.read_file(geojson_path)
aoi = gdf.geometry.iloc[0]

grid = GridDefinition(d=50000)

cells = grid.generate_grid_cells(aoi)

from satpy.scene import Scene

# %%
cells[0].area_def(resolution=371)


def _geobox_to_pyresample_yaml(geobox, area_id: str) -> str:
    """Construct a pyresample-compatible YAML string from an odc-geo GeoBox."""
    crs = geobox.crs
    if crs is None:
        raise ValueError(f"Cannot convert GeoBox to pyresample YAML: GeoBox has no CRS")
    epsg_code = crs.to_epsg()
    if epsg_code is None:
        raise ValueError(
            f"Cannot convert GeoBox to pyresample YAML: CRS {geobox.crs} has no EPSG code"
        )
    ll = geobox.extent.boundingbox
    units = "degrees" if crs.geographic else "m"
    return (
        f"{area_id}:\n"
        f"  description: Area defined for {area_id} in EPSG:{epsg_code}\n"
        f"  projection:\n"
        f"    EPSG: {epsg_code}\n"
        f"  shape:\n"
        f"    height: {geobox.shape.y}\n"
        f"    width: {geobox.shape.x}\n"
        f"  area_extent:\n"
        f"    lower_left_xy: [{ll.left}, {ll.bottom}]\n"
        f"    upper_right_xy: [{ll.right}, {ll.top}]\n"
        f"    units: {units}\n"
    )


# %%
import numpy as np
from odc.geo.crs import CRS
from odc.geo.geobox import GeoBox
from pyresample.area_config import load_area_from_string
from pyresample.geometry import SwathDefinition

scn = Scene(
    [
        "/root/repos/aer/VJ202IMG.A2026092.1754.021.2026093001440.nc",
        "/root/repos/aer/VJ203IMG.A2026092.1754.021.2026093000615.nc",
    ],
    reader="viirs_l1b",
)

import numpy as np
from pyresample.area_config import load_area_from_string
from pyresample.geometry import SwathDefinition

# --- 1. Load & compute ---
scn.load(["I01", "i_lat", "i_lon"], calibration="reflectance")
scn = scn.compute()

scn_cropped = scn.copy()  # Start with a copy of the original scene to modify

# --- 2. Crop to AOI bounds in WGS84 (degrees) ---
aoi_wgs84 = gdf.to_crs(epsg=4326).geometry.iloc[0]
bounds = aoi_wgs84.bounds  # (min_lon, min_lat, max_lon, max_lat)

lat = scn["i_lat"].values
lon = scn["i_lon"].values

row_mask = (lat >= bounds[1]) & (lat <= bounds[3])
col_mask = (lon >= bounds[0]) & (lon <= bounds[2])

rows = np.where(row_mask.any(axis=1))[0]
cols = np.where(col_mask.any(axis=0))[0]

if rows.size == 0 or cols.size == 0:
    raise ValueError("AOI does not overlap the swath")

row_slice = slice(rows[0], rows[-1] + 1)
col_slice = slice(cols[0], cols[-1] + 1)

# --- 3. Build a new SwathDefinition from the cropped geolocation ---
cropped_lat = scn["i_lat"][row_slice, col_slice]
cropped_lon = scn["i_lon"][row_slice, col_slice]
cropped_swath = SwathDefinition(lons=cropped_lon, lats=cropped_lat)

# --- 4. Replace I01 with the cropped version + new area metadata ---
cropped_i01 = scn["I01"][row_slice, col_slice]
cropped_i01.attrs["area"] = cropped_swath
scn_cropped["I01"] = cropped_i01

# Optional: free memory
del scn_cropped["i_lat"], scn_cropped["i_lon"]


# # 1. Build a single EPSG:4326 GeoBox covering the full AOI
# gdf_4326 = gdf.to_crs(epsg=4326)
# bounds = gdf_4326.total_bounds  # (min_lon, min_lat, max_lon, max_lat)

# # VIIRS I-band is ~371 m. In degrees that's roughly 0.0033°.
# # Pick a resolution close to native (e.g., 0.003° ≈ 333 m)
# res_deg = 0.003
# geobox_4326 = GeoBox.from_bbox(
#     bounds, crs=CRS("EPSG:4326"), resolution=res_deg, tight=True
# )

# area_yaml_4326 = _geobox_to_pyresample_yaml(geobox_4326, "aoi_4326")
# area_4326 = load_area_from_string(area_yaml_4326, "aoi_4326")

# # 2. Load and resample the whole swath to the 4326 grid (expensive step, done once)
# scn.load(["I01", "i_lat", "i_lon"], calibration="reflectance")
# scn_4326 = scn.resample(
#     area_4326, datasets=["I01"], resampler="nearest", reduce_data=True
# ).compute()

# Optional memory save
# del scn["i_lat"], scn["i_lon"]


# Optional memory save: drop the raw lat/lon if you don't need them as output
# del scn["i_lat"], scn["i_lon"]


# %%
import time

import matplotlib.pyplot as plt

for cell in cells:
    area_yaml = _geobox_to_pyresample_yaml(cell.area_def(resolution=371), "test_area")
    target_area = load_area_from_string(area_yaml, "test_area")
    start_time = time.time()
    # original_resampleed = scn.resample(
    #     target_area, datasets=["I01"], resampler="nearest"
    # ).compute()
    print(f"Original resampling took {time.time() - start_time:.2f} seconds")
    start_time = time.time()
    resampled = scn_cropped.resample(
        target_area, datasets=["I01"], resampler="nearest"
    ).compute()
    print(f"Resampling cropped scene took {time.time() - start_time:.2f} seconds")

    # print(f"Plotting took {time.time() - start_time:.2f} seconds")
    # print(resampled["I01"] == original_resampleed["I01"])
    # print(resampled["I01"].shape, original_resampleed["I01"].shape)
    resampled["I01"].plot()
    plt.show()


# %%
s3_path = "/tmp/03_multi_constellation_extraction/S3A_OL_1_EFR____20260402T140649_20260402T140949_20260403T144214_0179_138_010_3600_PS1_O_NT_004/S3A_OL_1_EFR____20260402T140649_20260402T140949_20260403T144214_0179_138_010_3600_PS1_O_NT_004.SEN3"
import glob
from pathlib import Path

from satpy.scene import Scene

all_files = glob.glob(s3_path + "/*.nc")
# Only include files that satpy's olci_l1b reader actually recognises
_known_basenames = {"geo_coordinates.nc", "tie_geometries.nc", "instrument_data.nc", "tie_meteo.nc", "qualityFlags.nc"}
all_files = [f for f in all_files if Path(f).name in _known_basenames or Path(f).name.endswith("_radiance.nc")]
# print(all_files)
scn = Scene(all_files, reader="olci_l1b")
scn.available_dataset_names()
scn.load(["Oa08"])
