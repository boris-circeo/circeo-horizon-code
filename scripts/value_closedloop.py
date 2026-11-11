"""Closed-loop test: B1c_5d_REF (climatological terminal) vs B1v_5d_REF (V_theta terminal).

30-day segments from the start of months NOT used to train the model of that month
(leave-month-out models from ``value_train.py``), seed-1 forecasts, same start position (the
B1c_5d_REF year-run position at the month start), climatology without the test month for both.
Usage: ``python3 scripts/value_closedloop.py [--months 3 7 10] [--target pol|hind]``.
Output: ``outputs/value/closedloop.json``; run directories ``outputs/value/cl/<policy>_mMM``.
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_s3_backtest as R  # noqa: E402

from horizon.polar.climatology import hold_power_vs_tws  # noqa: E402
from horizon.sim import DeterministicMPCPolicy  # noqa: E402
from horizon.sim.longrun import run_persistent  # noqa: E402
from horizon.sim.policies_refine import RefinedMPCPolicy  # noqa: E402
from horizon.value import TerminalFnMPCPolicy, ValueModel, ValueTerminal  # noqa: E402
from horizon.weather.forecast_model import ERA5ForecastWeather  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DAY = 86400.0


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, nargs="+", default=[3, 7, 10])
    ap.add_argument("--target", default="pol")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--days", type=float, default=30.0)
    a = ap.parse_args()
    ctx = R.Ctx()
    tws_ax, p_ax = hold_power_vs_tws(ctx.env)
    ok = np.isfinite(p_ax)
    out = ROOT / "outputs/value"
    res_f = out / f"closedloop_{a.target}.json"
    res = json.loads(res_f.read_text()) if res_f.exists() else {}
    for m in a.months:
        date = f"2015-{m:02d}-01"
        epoch = np.datetime64(f"{date}T00:00:00", "s")
        st = json.loads((ROOT / f"outputs/s4_runs/A_B1c_REF_s1/seg_{m - 2:04d}.json").read_text())
        start = tuple(float(v) for v in ctx.grid.to_lonlat(st["state"]["x"], st["state"]["y"]))
        clim = ctx.clim_hold_kw({m})
        model = ValueModel.load(ROOT / f"data/cache/value/models/vtheta_{a.target}_m{m:02d}.joblib")
        assert model.meta["holdout"] == m
        for name in ("B1c_5d_REF", "B1v_5d_REF"):
            key = f"{name}_m{m:02d}"
            if key in res:
                continue
            wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, a.days * DAY, seed=a.seed)
            if name.startswith("B1c"):
                base = DeterministicMPCPolicy(ctx.polar, ctx.hold, ctx.coast, horizon_days=5.0,
                                              terminal_clim_kw=clim, terminal_days=R.TERM_DAYS)
            else:
                vt = ValueTerminal(model, ctx.grid, clim, ctx.coast.sdf, epoch, tws_ax[ok],
                                   p_ax[ok])
                base = TerminalFnMPCPolicy(ctx.polar, ctx.hold, ctx.coast, horizon_days=5.0,
                                           terminal_fn=vt)
            pol = RefinedMPCPolicy(base)
            ctx.pm.n_clamped = 0
            t0 = time.perf_counter()
            r = run_persistent(pol, wx, start, ctx.pm, ctx.coast, out / "cl" / key,
                               duration_s=a.days * DAY, segments=a.days * DAY, tag=key,
                               log=lambda s, key=key: print(key, s, flush=True))
            e = r.energy_kwh
            res[key] = {"energy_kwh": e, "cf": e / (3000.0 * a.days * 24),
                        "guard": r.result.guard_interventions,
                        "coast_violations": r.result.coast_violations,
                        "dp_fallbacks": pol.n_dp_fallback, "wall_s": time.perf_counter() - t0,
                        "start": start}
            res_f.write_text(json.dumps(res, indent=1))
    for m in a.months:
        c, v = res.get(f"B1c_5d_REF_m{m:02d}"), res.get(f"B1v_5d_REF_m{m:02d}")
        if c and v:
            print(f"month {m}: B1c CF {c['cf']:.3f}  B1v CF {v['cf']:.3f}  "
                  f"dCF {v['cf'] - c['cf']:+.3f}")


if __name__ == "__main__":
    main()
