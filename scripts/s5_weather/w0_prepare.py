"""Dump the year of hourly 40 km ERA5 wind (u,v) to a single memmap-able .npy + masks."""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
g, arc, sea, land, env, tws, ph = setup()
n = arc.n_hours
uv = np.lib.format.open_memmap(OUT / "uv_2015.npy", mode="w+", dtype=np.float32, shape=(n, *g.shape, 2))
for m in range(12):
    lo, hi = int(arc._offset[m]), int(arc._offset[m + 1])
    uv[lo:hi] = arc.hours(lo, hi)
uv.flush()
lon, lat = g.lonlat_mesh()
np.savez(OUT / "masks.npz", sea=sea, land=land, outside=arc.outside, lon=lon, lat=lat)
print(n, sea.sum())
