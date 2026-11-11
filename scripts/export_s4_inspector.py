"""Export the year-long Experiment-A runs (outputs/s4_runs/A_*) to the router inspector.

Usage: ``python3 scripts/export_s4_inspector.py [--days 365] [--out FILE]`` (default
outputs/s4_inspector/year.json.gz), then ``python3 scripts/build_inspector.py --results
outputs/s4_inspector --out outputs/inspector_S4.html``. Exports seed 1 of each policy
(+ Oracle_REF_H = reference, B0). Client data stays local (git-ignored).
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_s3_backtest as R  # noqa: E402

from horizon.sim.simulator import MissionResult  # noqa: E402
from horizon.viz import SeedRun, export_backtest, save_export  # noqa: E402
from horizon.weather.forecast_model import ERA5ForecastWeather  # noqa: E402

RUNS = {"Oracle_REF_H": "A_OracleH", "B0": "A_B0", "B1_5d_REF": "A_B1_REF_s1",
        "B1c_5d_REF": "A_B1c_REF_s1", "ENS_REF": "A_ENS_REF_s1"}
INFO = {
    "Oracle_REF_H": {"label": "Hindsight (15 d truth DP + refiner)",
                     "description": "Not causal. Rolling 15 d truth look-ahead + clim. terminal."},
    "B0": {"label": "B0 hold at best fixed point",
           "description": "Station-keep at the annual best point."},
    "B1_5d_REF": {"label": "B1 5 d + refiner"},
    "B1c_5d_REF": {"label": "B1 5 d + refiner + clim. terminal"},
    "ENS_REF": {"label": "Ensemble 10 d (20 members, k 6) + refiner + clim. terminal"},
}


def load(d: Path, sim_dt_s=900.0) -> MissionResult:
    meta = json.loads((d / "meta.json").read_text())
    n_seg = len(meta["bounds"]) - 1
    if not (d / "summary.json").exists():  # partial run (tests): committed segments only
        n_seg = len(list(d.glob("seg_*.json")))
    parts = [np.load(d / f"seg_{k:04d}.npz") for k in range(n_seg)]
    st = json.loads((d / f"seg_{n_seg - 1:04d}.json").read_text())["state"]
    cat = {k: np.concatenate([z[k] for z in parts]) for k in
           ("x", "y", "power_kw", "heading_deg", "speed_ms")}
    xs, ys = np.concatenate([cat["x"], [st["x"]]]), np.concatenate([cat["y"], [st["y"]]])
    n = cat["power_kw"].size
    e = np.concatenate([[0.0], np.cumsum(cat["power_kw"] * sim_dt_s / 3600.0)])
    return xs, ys, n, cat, e, np.concatenate([z["replans"] for z in parts]), st


def main():
    warnings.filterwarnings("ignore", category=UserWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=365.0)
    ap.add_argument("--out", default=str(ROOT / "outputs/s4_inspector/year.json.gz"))
    ap.add_argument("--wind-budget-mb", type=float, default=6.0)
    a = ap.parse_args()
    ctx = R.Ctx()
    epoch = np.datetime64("2015-01-01T00:00:00", "s")
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, a.days * 86400.0, seed=1)
    truth = wx.truth(dt_s=3 * 3600.0)
    res = {}
    for name, dirn in RUNS.items():
        xs, ys, n, cat, e, rp, st = load(ROOT / "outputs/s4_runs" / dirn)
        lon, lat = ctx.grid.to_lonlat(xs, ys)
        res[name] = MissionResult(
            900.0 * np.arange(n + 1), xs, ys, np.asarray(lon), np.asarray(lat), cat["power_kw"], e,
            cat["heading_deg"], cat["speed_ms"], rp, 0, 900.0, int(st["guard_interventions"]),
            tuple(tuple(v) for v in st["guard_events"]), float(st["min_margin_m"]))
    start = tuple(float(v) for v in res["B0"].lon[:1].tolist() + res["B0"].lat[:1].tolist())
    sr = SeedRun(1, truth, res, wx, {}, label="2015 year, seed 1")
    data = export_backtest(
        [sr], ctx.coast, reference="Oracle_REF_H", title="HORIZON S4: median fleet ship, 2015",
        policy_info=INFO, start_lonlat=start, polar=ctx.polar, weather_kind="era5",
        era5_mask=~ctx.outside, forecast_error=False, wind_budget_mb=a.wind_budget_mb,
        params={"year": 2015, "start": "annual best offshore point", "forecast": "S4 v2 (latency)"})
    p = save_export(data, a.out)
    print(p, p.stat().st_size / 1e6, "MB")


if __name__ == "__main__":
    main()
