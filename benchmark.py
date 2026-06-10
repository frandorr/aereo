import time
import rasterio

uri = "/tmp/03_sentinel2_msi_extraction/loc-442D587L/date-20240102/profile-default/loc-442D587L_start-20240102T141709_end-20240102T141709_profile-default_collection-sentinel-2-l2a_variable-B04_res-10000m_desc-B04.tif"

print("Starting open...")
t0 = time.time()
with rasterio.open(uri) as src:
    t1 = time.time()
    print(f"Open took: {t1 - t0:.4f}s")

    ds_factor = 10
    out_shape = (int(src.height / ds_factor), int(src.width / ds_factor))
    t2 = time.time()
    data = src.read(1, out_shape=out_shape)
    t3 = time.time()
    print(f"Read took: {t3 - t2:.4f}s")
