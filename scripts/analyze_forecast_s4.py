"""Sprint 4 diagnostics of the forecast error model: consistency, jumpiness, averaging floor,
winter/summer calibration, memory. Usage: python3 scripts/analyze_forecast_s4.py [--quick]"""
import resource
import sys
from pathlib import Path

import numpy as np

from horizon.geo.coast import build_basin_coast
from horizon.geo.grid import Grid
from horizon.weather.era5 import ERA5_BOX, ERA5Archive
from horizon.weather.forecast_model import (
    ERA5ForecastWeather,
    ForecastErrorParams,
    forecast_skill,
    issue_correlation,
)

D, H = 86400.0, 3600.0
quick = "--quick" in sys.argv
grid = Grid.from_bbox(*ERA5_BOX, 40e3)
arch = ERA5Archive(Path("/home/claude/circeo-horizon-data/era5-data"), grid)
arch.build_cache()
sea = (build_basin_coast(40e3, bbox=ERA5_BOX).sdf > 0) & ~arch.outside
EP = np.datetime64("2015-01-01T00:00:00")
mk = lambda P, seed=3: ERA5ForecastWeather(arch, grid, EP, 360 * D, params=P, seed=seed)  # noqa
new, old = mk(ForecastErrorParams()), mk(ForecastErrorParams.legacy())


def ctrl_err(wx, a, v_days):
    """control forecast error at valid times a + v_days [(T, n, 2)] sea cells."""
    ens = wx.forecast_cycle(a, max(v_days) * D, 1, dt_s=6 * H)
    idx = np.round(np.array(v_days) * 4).astype(int)
    tr = wx._truth_at(ens.times_s[idx])
    return (ens.uv[0, idx] - tr)[:, sea], tr[:, sea]


iss = (np.linspace(20, 330, 4 if quick else 12) * D)
print("== control error correlation, issue a vs a+6h, same valid time")
print("lead[d]  corr_sim  corr_analytic  corr_legacy  rms_change  ctrl_rmse  change/rmse")
for wx_name, wx in (("new", new), ("old", old)):
    for L in (0.5, 1, 2, 3, 5, 7):
        c, ch, r = [], [], []
        for a in iss:
            e1, _ = ctrl_err(wx, a, [L + 0.25])  # older issue, valid a + L + 6h
            e2, _ = ctrl_err(wx, a + 6 * H, [L])  # newer issue, same valid time
            c.append(np.sum(e1 * e2) / np.sqrt(np.sum(e1**2) * np.sum(e2**2)))
            ch.append(np.mean(np.sum((e2 - e1) ** 2, -1)))
            r.append(np.mean(np.sum(e2**2, -1)))
        an = issue_correlation(new.params, a, a + 6 * H, a + (L + 0.25) * D)
        print(f"{wx_name} {L:5.2f}  {np.mean(c):8.3f} {an:8.3f} rms_chg={np.sqrt(np.mean(ch)):.2f}"
              f"  ctrl_rmse={np.sqrt(np.mean(r)):.2f}"
              f"  ratio={np.sqrt(np.mean(ch) / np.mean(r)):.2f}")

print("== averaging N past issues (ens mean, M=10, 6h cycles back, newest lead 3 d): RMSE vs N")
V = 3 * D
for name, wx in (("new", new), ("old", old)):
    out = {N: [] for N in (1, 2, 4, 8, 16)}
    for a0 in iss[:: 1 if not quick else 2]:
        v = a0 + V
        fs = []
        for k in range(16):
            a = a0 - 6 * H * k
            ens = wx.forecast_cycle(a, v - a, 10, dt_s=6 * H)
            fs.append(ens.uv.mean(0)[-1][sea])
        tr = wx._truth_at(np.array([v]))[0][sea]
        for N in out:
            out[N].append(np.mean(np.sum((np.mean(fs[:N], 0) - tr) ** 2, -1)))
    print(name, {N: round(float(np.sqrt(np.mean(x))), 2) for N, x in out.items()})

print("== calibration winter (Dec-Feb issues) vs summer (Jun-Aug issues), M=10, 12 issues each")
for nm, days in (("winter", np.r_[np.linspace(3, 55, 6), np.linspace(335, 350, 4)]),
                 ("summer", np.linspace(160, 235, 10))):
    r = forecast_skill(new, days[:5 if quick else 10] * D + 43200.0, 10, 10, sea)
    for d in (1, 3, 5, 7, 10):
        print(f"{nm} D{d:2d} ctrl={r['control_rmse'][d]:.2f} mean={r['mean_rmse'][d]:.2f} "
              f"spread={r['spread'][d]:.2f} ratio={r['spread'][d] / r['mean_rmse'][d]:.2f}")

print("== memory 50 members, 15 d, 3 h")
nb = new.ensemble_nbytes(50, 15 * D)
rss = resource.getrusage(0).ru_maxrss / 1e3
print(f"uv array {nb / 1e6:.0f} MB; ru_maxrss before {rss:.0f} MB")
ens = new.forecast(100 * D, 15 * D, 50)
print(f"after: ru_maxrss {resource.getrusage(0).ru_maxrss / 1e3:.0f} MB, shape {ens.uv.shape}")
