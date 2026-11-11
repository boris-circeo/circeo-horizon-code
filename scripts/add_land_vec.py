"""Add ``map.land_vec`` (vector land) to an existing inspector export, in place or to ``--out``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from horizon.geo.grid import Grid  # noqa: E402
from horizon.viz.export import _export_land_vec, load_export, save_export  # noqa: E402
from horizon.weather.era5 import ERA5_BOX  # noqa: E402


def main() -> None:
    """Inject vector land into an export file that lacks it."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = load_export(a.export)
    g = d["map"]["grid"]
    grid = Grid.from_bbox(*ERA5_BOX, g["dx_km"] * 1e3)
    if (grid.nx, grid.ny) != (g["nx"], g["ny"]) or abs(grid.x0 / 1e3 - g["x0_km"]) > 1e-3:
        raise SystemExit("export grid differs from the ERA5-box grid")
    lv = _export_land_vec(grid)
    d["map"]["land_vec"] = lv
    p = save_export(d, a.out or a.export)
    print(p, int(np.sum(lv["n"])), "vertices")


if __name__ == "__main__":
    main()
