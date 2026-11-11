"""Sprint-4 persistent (up to 365 d) run of one policy with monthly checkpoints (resumable).

Usage: ``python3 scripts/run_s4_year.py --policy B1c_5d_REF --days 365 --out outputs/s4_runs/X
[--start offshore|lorient|LON,LAT] [--epoch 2015-01-01] [--segments month|SECONDS]``.
Kill it at any time and start it again with the same arguments: it resumes from the last
committed month (see :mod:`horizon.sim.longrun`). Policies: B0, B1_5d, B1_5d_REF, B1c_5d_REF,
Oracle (full-mission 3 h DP, hindsight), Oracle_REF (full-mission DP + refiner), Oracle_REF_H
(rolling-horizon hindsight + refiner + climatological terminal; approximate bound). ERA5 is
client-confidential: only trajectories and aggregated metrics are written (git-ignored under
outputs/s4_runs).
"""

import argparse
import json
import resource
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_s3_backtest as R  # noqa: E402

from horizon.geo.coast import port_corridor  # noqa: E402
from horizon.sim import (  # noqa: E402
    DeterministicMPCPolicy,
    HoldAtPointPolicy,
    OraclePolicy,
    best_climatological_point,
)
from horizon.sim.longrun import run_persistent  # noqa: E402
from horizon.sim.policies_ens import EnsembleMPCPolicy  # noqa: E402
from horizon.sim.policies_refine import (  # noqa: E402
    OracleHorizonRefinedPolicy,
    OracleRefinedPolicy,
    RefinedMPCPolicy,
)
from horizon.weather.forecast_model import ERA5ForecastWeather, ForecastErrorParams  # noqa: E402

LORIENT = (-3.4, 47.7)


def build(policy, ctx, wx, clim, horizon_h_days=15.0, members=20, k=6):
    pol, hold, coast = ctx.polar, ctx.hold, ctx.coast

    def b1(c=None):
        return DeterministicMPCPolicy(pol, hold, coast, horizon_days=5.0, terminal_clim_kw=c,
                                      terminal_days=R.TERM_DAYS)

    if policy == "B1_5d":
        return b1()
    if policy == "B1_5d_REF":
        return RefinedMPCPolicy(b1())
    if policy == "B1c_5d_REF":
        return RefinedMPCPolicy(b1(clim))
    if policy == "ENS_REF":
        return RefinedMPCPolicy(EnsembleMPCPolicy(
            pol, hold, coast, horizon_days=10.0, n_members=members, k=k, gamma=0.0, alpha=0.2,
            terminal_clim_kw=clim, terminal_days=R.TERM_DAYS))
    if policy == "Oracle_REF_H":
        return OracleHorizonRefinedPolicy(wx, pol, hold, coast, horizon_days=horizon_h_days,
                                          terminal_clim_kw=clim, terminal_days=R.TERM_DAYS)
    if policy == "Oracle_REF":  # full-mission hindsight DP + refiner (30 d tests only)
        return OracleRefinedPolicy(wx.truth(dt_s=3600.0), pol, hold, coast, wx.duration_s)
    if policy == "Oracle":
        truth = wx.truth(dt_s=3600.0)
        return OraclePolicy(truth, pol, hold, coast, wx.duration_s)
    raise SystemExit(f"unknown policy {policy}")


def main():
    warnings.filterwarnings("ignore", category=UserWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--days", type=float, default=365.0)
    ap.add_argument("--epoch", default="2015-01-01")
    ap.add_argument("--start", default="offshore")
    ap.add_argument("--out", required=True)
    ap.add_argument("--segments", default="month")
    ap.add_argument("--horizon-days", type=float, default=15.0, help="Oracle_REF_H look-ahead")
    ap.add_argument("--ramp-km", type=float, default=40.0)
    ap.add_argument("--seed", type=int, default=1, help="forecast-error seed")
    ap.add_argument("--members", type=int, default=20)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--legacy", action="store_true", help="ForecastErrorParams.legacy()")
    ap.add_argument("--stop-after", type=int, default=None, help="(tests) stop after N segments")
    a = ap.parse_args()
    ctx = R.Ctx()
    seg = "month" if a.segments == "month" else float(a.segments)
    clim = ctx.clim_hold_kw(set())  # annual climatology (same-year leakage, as the B0 point)
    if a.start == "lorient":
        start = LORIENT
        ctx.coast = port_corridor(ctx.coast, *LORIENT, ramp_m=a.ramp_km * 1e3)
    elif a.start == "offshore":
        sxy = ctx.grid.to_xy(*R.START)
        x, y, _ = best_climatological_point([], ctx.pm, ctx.coast, sxy, mean_kw=clim,
                                            extra_mask=~ctx.outside)
        start = tuple(float(v) for v in ctx.grid.to_lonlat(x, y))
    else:
        start = tuple(float(v) for v in a.start.split(","))
    print(f"start lon/lat {start[0]:.3f} {start[1]:.3f}", flush=True)
    epoch = np.datetime64(f"{a.epoch}T00:00:00", "s")
    params = ForecastErrorParams.legacy() if a.legacy else ForecastErrorParams()
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, a.days * 86400.0, params=params,
                             seed=a.seed)
    pol = (HoldAtPointPolicy(*ctx.grid.to_xy(*start)) if a.policy == "B0"
           else build(a.policy, ctx, wx, clim, a.horizon_days, a.members, a.k))
    ctx.pm.n_clamped = 0
    t0 = time.perf_counter()
    r = run_persistent(pol, wx, start, ctx.pm, ctx.coast, a.out, duration_s=a.days * 86400.0,
                       segments=seg, tag=f"{a.policy}|{a.epoch}|{a.days}|{a.start}",
                       stop_after_segments=a.stop_after, log=lambda s: print(s, flush=True))
    res = r.result
    wall = time.perf_counter() - t0
    out = {"policy": a.policy, "seed": a.seed, "legacy": a.legacy, "days": a.days, "start": start,
           "energy_mwh": r.energy_kwh / 1e3, "guard_interventions": res.guard_interventions,
           "coast_violations": res.coast_violations,
           "min_margin_km": res.min_margin_m / 1e3, "wall_s": wall,
           "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
           "wrapped_requests": wx.n_wrapped_requests, "resumed_from": r.resumed_from,
           "n_dp_fallback": getattr(pol, "n_dp_fallback", None)}
    print(json.dumps(out, indent=1), flush=True)
    (Path(a.out) / "run_info.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
