"""Build the ERA5 regridded cache and print monthly wind statistics over sea.

Usage: ``python3 scripts/prepare_era5.py [--grib-dir DIR] [--dx-km 40] [--force]``

The ERA5 files are client PROPRIETARY data: they are read from ``--grib-dir`` (outside the
repository); the cache goes to ``data/cache/era5/`` (git-ignored).
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from horizon.core.units import ms_to_kn
from horizon.geo.coast import build_basin_coast
from horizon.geo.grid import Grid
from horizon.weather.era5 import ERA5_BOX, ERA5Archive

DEFAULT_GRIB = "/home/claude/circeo-horizon-data/era5-data"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grib-dir", default=DEFAULT_GRIB)
    ap.add_argument("--dx-km", type=float, default=40.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    grid = Grid.from_bbox(*ERA5_BOX, a.dx_km * 1e3)
    arch = ERA5Archive(a.grib_dir, grid)
    print(f"grid {grid.ny} x {grid.nx} @ {a.dx_km:g} km, outside ERA5 box: "
          f"{100 * arch.frac_outside:.1f} % of cells (nearest-edge fill)")
    info = arch.build_cache(force=a.force, verbose=True)
    print(f"ingestion {info['seconds']:.1f} s, cache {info['bytes'] / 1e6:.0f} MB "
          f"in {arch.cache_dir}")
    coast = build_basin_coast(a.dx_km * 1e3, bbox=ERA5_BOX)
    sea = (coast.sdf > 0) & ~arch.outside
    print(f"sea cells: {sea.sum()} / {sea.size}")
    print("month  mean_TWS[m/s]  mean_TWS[kn]  frac 18-26 kn  frac > 35 kn")
    t0 = time.perf_counter()
    h = 0
    for m in range(1, 13):
        n = arch._hours[m - 1]
        uv = arch.hours(h, h + n)[:, sea]
        h += n
        kn = ms_to_kn(np.hypot(uv[..., 0], uv[..., 1]))
        print(f"{m:5d}  {kn.mean() / ms_to_kn(1.0):13.2f}  {kn.mean():12.2f}  "
              f"{100 * ((kn >= 18) & (kn <= 26)).mean():12.1f}%  {100 * (kn > 35).mean():10.2f}%")
    print(f"stats {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
