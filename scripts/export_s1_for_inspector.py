"""Run (or re-run) the S1 policies on a few seeds and export them for the router inspector.

Exports B0, B1_5d, B1_15d and the hindsight Oracle (optionally B0_spec) on the S1 setup
(30-day missions from 47.0N 6.5W, 40 km grid, replan every 6 h) and writes an export file plus,
optionally, the HTML page. Extra policies (S2 ...) can be added without code changes::

    python3 scripts/export_s1_for_inspector.py --seeds 101 102 103 \
        --extra horizon.sim.policies_ens:inspector_policies --html outputs/inspector.html

``--extra module:factory`` imports ``factory(ctx)`` which returns ``{name: policy}``; ``ctx`` has
``grid, coast, polar, hold, pm, wx, truth, T, start, seed, replan_s``. ``--only`` limits the
policies (the oracle is always run: it is the regret reference). To append policies to an
earlier export without re-running it, export them with ``--only <names> --out new.json.gz`` and
merge with ``scripts/build_inspector.py --results <dir>``.
"""

import argparse
import importlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from horizon.geo.coast import build_basin_coast
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.polar.synthetic import SyntheticPolarParams
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    HoldAtPointPolicy,
    OraclePolicy,
    best_climatological_point,
    run_mission,
)
from horizon.viz import RecordingPolicy, SeedRun, export_backtest, save_export, write_inspector
from horizon.weather.synthetic import SyntheticWeather

ROOT = Path(__file__).resolve().parents[1]
EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0
T = 30 * DAY
START = (-6.5, 47.0)
SPEC_POINT = (-15.0, 50.0)
REPLAN_S = 6 * 3600.0
_PP = SyntheticPolarParams()
POLAR_FACTS = {"derate_kn": _PP.derate_start_kn, "cutout_kn": _PP.cutout_kn,
               "twa_opt_deg": _PP.twa_opt_deg, "cap_kw": _PP.cap_kw}
INFO = {
    "B0": {"label": "B0 hold at best fixed point",
           "description": "Transit to the climatologically best point, then station-keep."},
    "B0_spec": {"label": "B0 hold at spec point 50N 15W",
                "description": "Station-keep at the spec indicative zone."},
    "B1_5d": {"label": "B1 deterministic MPC, 5 d", "params": {"horizon_days": 5}},
    "B1_15d": {"label": "B1 deterministic MPC, 15 d", "params": {"horizon_days": 15}},
    "Oracle": {"label": "Hindsight oracle (DP on truth)",
               "description": "Not causal: upper bound J_hind of the regret."},
}


def b0_point(grid, coast, pm, start_xy):
    """B0 hold point: reuse outputs/S1_results.json if present, else train on seeds 1-3."""
    f = ROOT / "outputs" / "S1_results.json"
    if f.exists():
        b = json.loads(f.read_text())["B0_point"]
        return grid.to_xy(b["lon"], b["lat"])
    train = [SyntheticWeather(grid, EPOCH, T, seed=s).truth(dt_s=3 * 3600.0) for s in (1, 2, 3)]
    bx, by, _ = best_climatological_point(train, pm, coast, start_xy)
    return bx, by


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103])
    ap.add_argument("--out", default="outputs/inspector_data.json.gz")
    ap.add_argument("--html", default=None, help="also build this HTML page")
    ap.add_argument("--with-spec", action="store_true", help="also run B0_spec")
    ap.add_argument("--only", nargs="+", default=None, help="restrict to these policy names")
    ap.add_argument("--extra", action="append", default=[], help="module:factory (repeatable)")
    ap.add_argument("--wind-dt-h", type=float, default=3.0)
    a = ap.parse_args()

    grid = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = build_basin_coast(40e3)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    pm = EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))
    sx, sy = grid.to_xy(*START)
    bx, by = b0_point(grid, coast, pm, (sx, sy))
    extras = [getattr(importlib.import_module(m), f)
              for m, f in (e.split(":") for e in a.extra)]
    blon, blat = grid.to_lonlat(bx, by)

    runs = []
    for seed in a.seeds:
        t0 = time.perf_counter()
        wx = SyntheticWeather(grid, EPOCH, T, seed=seed)
        truth = wx.truth(dt_s=3600.0)
        pols = {"B0": HoldAtPointPolicy(bx, by),
                "B1_5d": DeterministicMPCPolicy(polar, hold, coast, horizon_days=5.0),
                "B1_15d": DeterministicMPCPolicy(polar, hold, coast, horizon_days=15.0)}
        if a.with_spec:
            pols["B0_spec"] = HoldAtPointPolicy(*grid.to_xy(*SPEC_POINT))
        ctx = SimpleNamespace(grid=grid, coast=coast, polar=polar, hold=hold, pm=pm, wx=wx,
                              truth=truth, T=T, start=START, seed=seed, replan_s=REPLAN_S)
        for fac in extras:
            pols.update(fac(ctx))
        if a.only:
            pols = {n: p for n, p in pols.items() if n in a.only}
        pols["Oracle"] = OraclePolicy(truth, polar, hold, coast, T)
        order = ["Oracle", *pols.keys() - {"Oracle"}]  # oracle first (cheap, reference)
        rec = {n: RecordingPolicy(pols[n]) for n in order}
        res = {n: run_mission(rec[n], wx, truth, START, T, pm, coast, replan_s=REPLAN_S)
               for n in order}
        res = {n: res[n] for n in ["Oracle", *[k for k in pols if k != "Oracle"]]}
        runs.append(SeedRun(seed, truth, res, wx, {n: rec[n].records for n in res}))
        print(f"seed {seed}: " + ", ".join(f"{n} {r.energy_kwh[-1] / 1e3:.0f} MWh"
                                           for n, r in res.items())
              + f"  [{time.perf_counter() - t0:.0f} s]", flush=True)

    markers = [{"name": "B0 point", "lon": float(blon), "lat": float(blat)}]
    if a.with_spec:
        markers.append({"name": "B0_spec point", "lon": SPEC_POINT[0], "lat": SPEC_POINT[1]})
    data = export_backtest(
        runs, coast, reference="Oracle", title="HORIZON S1 router inspector",
        wind_dt_s=a.wind_dt_h * 3600.0, policy_info=INFO, markers=markers, start_lonlat=START,
        params={"grid_km": 40, "replan_h": REPLAN_S / 3600.0, "plan_dt_h": 3,
                "start": "47.0N 6.5W", "weather": "synthetic",
                "polar": {"kind": "synthetic (hypotheses)", **POLAR_FACTS},
                "stencil_arcs": 21, "oracle_dt_h": 3, "n_seeds": len(a.seeds)})
    out = save_export(data, a.out)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
    if a.html:
        h = write_inspector(data, a.html)
        print(f"wrote {h} ({h.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
