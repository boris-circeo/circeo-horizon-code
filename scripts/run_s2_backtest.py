"""Sprint-2 closed-loop backtest: ensemble MPC (CVaR) and continuous refiner vs the S1 policies.

Resumable: one pickle per (policy, seed) in ``outputs/s2_runs`` (skipped if present). Policies
ENS_g0, ENS_g03, B1_5d_REF, ENS_g03_REF are new; B0/B0_spec/B1/Oracle of S1 are reused from
``outputs/S1_results.json`` (re-run only for the inspector seeds, with recording).
Usage: ``python3 scripts/run_s2_backtest.py [--members 12] [--seeds ...] [--time-only]``.
"""

import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np

from horizon.geo.coast import build_basin_coast
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    HoldAtPointPolicy,
    OraclePolicy,
    mission_metrics,
    run_mission,
)
from horizon.sim.policies_ens import EnsembleMPCPolicy
from horizon.sim.policies_refine import RefinedMPCPolicy
from horizon.viz import RecordingPolicy
from horizon.weather.synthetic import SyntheticWeather

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "outputs" / "s2_runs"
EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0
T = 30 * DAY
START = (-6.5, 47.0)
SPEC_POINT = (-15.0, 50.0)
REPLAN_S = 6 * 3600.0
NEW = ("ENS_g0", "ENS_g03", "B1_5d_REF", "ENS_g03_REF")
S1_REPRO = ("B0", "B0_spec", "B1_5d", "B1_15d")  # re-run (recorded) on inspector seeds only


def setup():
    grid = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = build_basin_coast(40e3)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    pm = EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))
    return grid, coast, polar, hold, pm


def make_policy(name, polar, hold, coast, grid, members, k):
    def ens(gamma):
        return EnsembleMPCPolicy(polar, hold, coast, horizon_days=15.0, n_members=members, k=k,
                                 gamma=gamma, alpha=0.2)
    if name == "ENS_g0":
        return ens(0.0)
    if name == "ENS_g03":
        return ens(0.3)
    if name == "B1_5d_REF":
        return RefinedMPCPolicy(DeterministicMPCPolicy(polar, hold, coast, horizon_days=5.0))
    if name == "ENS_g03_REF":
        return RefinedMPCPolicy(ens(0.3))
    if name == "B1_5d":
        return DeterministicMPCPolicy(polar, hold, coast, horizon_days=5.0)
    if name == "B1_15d":
        return DeterministicMPCPolicy(polar, hold, coast, horizon_days=15.0)
    raise KeyError(name)


def b0_xy(grid):
    b = json.loads((ROOT / "outputs" / "S1_results.json").read_text())["B0_point"]
    return grid.to_xy(b["lon"], b["lat"])


def run_one(name, seed, ctx, members, k, T_s=T):
    grid, coast, polar, hold, pm = ctx
    wx = SyntheticWeather(grid, EPOCH, T_s, seed=seed)
    truth = wx.truth(dt_s=3600.0)
    if name == "B0":
        pol = HoldAtPointPolicy(*b0_xy(grid))
    elif name == "B0_spec":
        pol = HoldAtPointPolicy(*grid.to_xy(*SPEC_POINT))
    elif name == "Oracle":
        pol = OraclePolicy(truth, polar, hold, coast, T_s)
    else:
        pol = make_policy(name, polar, hold, coast, grid, members, k)
    rec = RecordingPolicy(pol)
    t0 = time.perf_counter()
    res = run_mission(rec, wx, truth, START, T_s, pm, coast, replan_s=REPLAN_S)
    return res, rec.records, time.perf_counter() - t0, pol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=int, default=12)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103, 104, 105])
    ap.add_argument("--ens-g0-seeds", type=int, nargs="+", default=None)
    ap.add_argument("--inspector-seeds", type=int, nargs="+", default=[101, 102, 103])
    ap.add_argument("--only", nargs="+", default=None)
    a = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    ctx = setup()
    jobs = []
    for s in a.seeds:  # seed-major so that early seeds complete for all policies
        if s in a.inspector_seeds:
            jobs += [("Oracle", s), *[(n, s) for n in S1_REPRO]]
        for n in NEW:
            if n == "ENS_g0" and a.ens_g0_seeds is not None and s not in a.ens_g0_seeds:
                continue
            jobs.append((n, s))
    if a.only:
        jobs = [j for j in jobs if j[0] in a.only]
    for name, seed in jobs:
        f = RUNS / f"{name}_{seed}.pkl"
        if f.exists():
            continue
        res, records, dt, pol = run_one(name, seed, ctx, a.members, a.k)
        m = mission_metrics(res)
        extra = {}
        if hasattr(pol, "results"):
            rr = pol.results
            extra["refine_calls"] = len(rr)
        tmp = f.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"name": name, "seed": seed, "res": res, "records": records,
                         "metrics": m.__dict__, "wall_s": dt, "members": a.members, "k": a.k,
                         "coast_violations": res.coast_violations, "n_replans": res.n_replans,
                         "extra": extra}, fh)
        tmp.rename(f)
        print(f"{name} seed {seed}: {m.energy_kwh / 1e3:.1f} MWh [{dt:.0f} s]", flush=True)


if __name__ == "__main__":
    main()
