import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import box
import numpy as np

fig, ax = plt.subplots()

# Simulate bounds
left, bottom, right, top = 0, 0, 10000, 10000
extent = [left, right, bottom, top]

# Simulate data
data = np.random.rand(100, 100)

# Simulate imshow with origin=upper
ax.imshow(data, cmap="gray", extent=extent, origin="upper")

# Simulate geopandas overlay
footprint = box(left, bottom, right, top)
gs = gpd.GeoSeries([footprint])

try:
    gs.plot(ax=ax, facecolor="none", edgecolor="red", linestyle="--", linewidth=2)
    plt.savefig("test.png")
    print("Plot successful")
except Exception:
    import traceback

    traceback.print_exc()
