"""Sprint-3 closed-loop backtest: real ERA5 truth (2015), BETA polar, ERA5-error forecasts.

Resumable: one pickle per (policy, mission) in ``outputs/s3_runs`` (skipped if present).
Usage: ``python3 scripts/run_s3_backtest.py [--time-only] [--members 10] [--only P ...]
[--missions M ...] [--ens-missions M ...]``. ERA5 data and caches are client-confidential: nothing
derived from them except aggregated results is written under ``outputs`` figures/json/md; the
per-run pickles hold trajectories only (git-ignored by outputs/s3_runs).
"""

import argparse
import pickle
import time
import warnings
from pathlib import Path

import numpy as np

from horizon.geo.coast import CoastModel, build_basin_coast, signed_distance
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve
from horizon.polar.beta import load_beta_polar
from horizon.polar.climatology import climatological_hold_power
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    FeasiblePowerModel,
    HoldAtPointPolicy,
    OraclePolicy,
    best_climatological_point,
    mission_metrics,
    run_mission,
)
from horizon.sim.policies_ens import EnsembleMPCPolicy
from horizon.sim.policies_refine import OracleRefinedPolicy, RefinedMPCPolicy
from horizon.viz import RecordingPolicy
from horizon.weather.era5 import ERA5_BOX, ERA5Archive
from horizon.weather.forecast_model import ERA5ForecastWeather

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "outputs" / "s3_runs"
CLIM = ROOT / "data" / "cache" / "s3"
POLAR_DIR = "/home/claude/circeo-horizon-data/power-polar"
ERA5_CACHE = ROOT / "data" / "cache" / "era5"
YEAR = 2015
DAY = 86400.0
T = 30 * DAY
START = (-6.5, 47.0)
REPLAN_S = 6 * 3600.0
MISSIONS = [
    "2015-01-01",
    "2015-01-15",
    "2015-02-01",
    "2015-02-15",
    "2015-03-01",
    "2015-10-01",
    "2015-10-15",
    "2015-11-01",
    "2015-11-15",
    "2015-12-01",
]
WINTER6 = ["2015-01-01", "2015-01-15", "2015-02-01", "2015-02-15", "2015-11-15", "2015-12-01"]
POLICIES = ["Oracle", "Oracle_REF", "B0", "B1_5d", "B1_5d_REF", "B1c_5d_REF", "ENS_g0",
            "ENS_g0_REF"]
ENS_POLICIES = ("ENS_g0", "ENS_g0_REF")
TERM_DAYS = 5.0


def mission_id(date: str) -> int:
    """Integer id used as 'seed' (MMDD)."""
    return int(date[5:7]) * 100 + int(date[8:10])


def touched_months(date: str) -> set[int]:
    t0 = np.datetime64(date)
    t1 = t0 + np.timedelta64(30, "D")
    return {int(str(t0)[5:7]), int(str(t1 - np.timedelta64(1, "s"))[5:7])}


class Ctx:
    """Everything shared across missions."""

    def __init__(self):
        warnings.filterwarnings("ignore", category=UserWarning)
        self.grid = Grid.from_bbox(*ERA5_BOX, 40e3)
        self.archive = ERA5Archive(ERA5_CACHE, self.grid, year=YEAR)
        self.outside = self.archive.outside
        c0 = build_basin_coast(40e3, bbox=ERA5_BOX)
        land = (c0.sdf < 0) | self.outside  # outside the ERA5 box = fake wind -> treat as land
        self.coast0 = c0
        self.coast = CoastModel(self.grid, signed_distance(self.grid, land))
        self.polar = load_beta_polar(POLAR_DIR)
        self.hold = hold_power_curve(self.polar)
        self.env = build_envelope(self.polar)
        self.pm = FeasiblePowerModel(
            EnvelopePowerModel(self.env, fallback=DirectPowerModel(self.polar, self.hold)))
        self._month_maps: dict[int, tuple[np.ndarray, int]] = {}

    # ---------------------------------------------------------------- climatology (per month)
    def month_map(self, m: int):
        """(sum over 3-hourly samples of hold power [kW], n_samples) for 2015 month ``m``."""
        if m not in self._month_maps:
            f = CLIM / f"hold_sum_{YEAR}_{m:02d}.npz"
            if f.exists():
                z = np.load(f)
                self._month_maps[m] = (z["s"], int(z["n"]))
            else:
                h0 = int(self.archive._offset[m - 1])
                h1 = int(self.archive._offset[m])
                uv = self.archive.hours(h0, h1)[::3]
                from horizon.weather.fields import WindField

                wf = WindField(
                    self.grid, self.archive.start, np.arange(uv.shape[0]) * 3 * 3600.0, uv
                )
                p = climatological_hold_power(wf, self.env).astype(np.float64)
                s = p * uv.shape[0]
                CLIM.mkdir(parents=True, exist_ok=True)
                np.savez(f, s=s, n=uv.shape[0])
                self._month_maps[m] = (s, uv.shape[0])
        return self._month_maps[m]

    def clim_hold_kw(self, exclude: set[int]) -> np.ndarray:
        """Climatological hold power [kW] over the 2015 months NOT in ``exclude``."""
        acc, n = 0.0, 0
        for m in range(1, 13):
            if m in exclude:
                continue
            s, k = self.month_map(m)
            acc = acc + s
            n += k
        return (acc / n).astype(np.float32)

    def b0_point(self, date: str):
        mean = self.clim_hold_kw(touched_months(date))
        sxy = self.grid.to_xy(*START)
        x, y, mk = best_climatological_point(
            [], self.pm, self.coast, sxy, mean_kw=mean, extra_mask=~self.outside
        )
        return x, y, mk


def make_policy(name, ctx, date, members, k, horizon_ens=10.0):
    pol, hold, coast = ctx.polar, ctx.hold, ctx.coast
    if name == "B0":
        x, y, _ = ctx.b0_point(date)
        return HoldAtPointPolicy(x, y)
    cl = ctx.clim_hold_kw(touched_months(date))

    def b1(clim=None):
        return DeterministicMPCPolicy(
            pol, hold, coast, horizon_days=5.0, terminal_clim_kw=clim, terminal_days=TERM_DAYS
        )

    def ens():
        return EnsembleMPCPolicy(
            pol,
            hold,
            coast,
            horizon_days=horizon_ens,
            n_members=members,
            k=k,
            gamma=0.0,
            alpha=0.2,
            terminal_clim_kw=cl,
            terminal_days=TERM_DAYS,
        )

    return {
        "B1_5d": lambda: b1(),
        "B1_5d_REF": lambda: RefinedMPCPolicy(b1()),
        "B1c_5d_REF": lambda: RefinedMPCPolicy(b1(cl)),
        "ENS_g0": ens,
        "ENS_g0_REF": lambda: RefinedMPCPolicy(ens()),
    }[name]()


def run_one(name, date, ctx, members, k, max_replans=None):
    epoch = np.datetime64(f"{date}T00:00:00", "s")
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, T, seed=mission_id(date))
    truth = wx.truth(dt_s=3600.0)
    if name == "Oracle":
        pol = OraclePolicy(truth, ctx.polar, ctx.hold, ctx.coast, T)
    elif name == "Oracle_REF":
        pol = OracleRefinedPolicy(truth, ctx.polar, ctx.hold, ctx.coast, T)
    else:
        pol = make_policy(name, ctx, date, members, k)
    rec = RecordingPolicy(pol)
    dur = T if max_replans is None else max_replans * REPLAN_S
    ctx.pm.n_clamped = 0
    t0 = time.perf_counter()
    res = run_mission(rec, wx, truth, START, dur, ctx.pm, ctx.coast, replan_s=REPLAN_S)
    return res, rec.records, time.perf_counter() - t0, pol, wx, truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=int, default=10)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--only", nargs="+", default=None)
    ap.add_argument("--missions", nargs="+", default=MISSIONS)
    ap.add_argument(
        "--ens-missions",
        nargs="+",
        default=None,
        help="restrict the ENS policies to these missions",
    )
    ap.add_argument("--time-only", action="store_true", help="time 2 replans per policy and exit")
    a = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    ctx = Ctx()
    names = a.only or POLICIES
    if a.time_only:
        from horizon.sim.simulator import ForecastProvider

        date = "2015-01-01"
        epoch = np.datetime64(f"{date}T00:00:00", "s")
        wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, T, seed=mission_id(date))
        x, y = ctx.grid.to_xy(*START)
        for n in names:
            if n in ("Oracle", "B0"):
                continue
            pol = make_policy(n, ctx, date, a.members, a.k)
            ts = []
            for t in (0.0, 6 * 3600.0, 12 * 3600.0):
                t0 = time.perf_counter()
                pol.plan(t, x, y, ForecastProvider(wx, t, T))
                ts.append(time.perf_counter() - t0)
            print(
                f"{n}: replans {[round(v, 1) for v in ts]} s -> ~{np.mean(ts) * 120:.0f} s/mission",
                flush=True,
            )
        return
    for date in a.missions:  # mission-major: complete missions first
        for n in names:
            if n in ENS_POLICIES and a.ens_missions is not None and date not in a.ens_missions:
                continue
            f = RUNS / f"{n}_{date}.pkl"
            if f.exists():
                continue
            res, records, dt, pol, wx, _ = run_one(n, date, ctx, a.members, a.k)
            m = mission_metrics(res)
            sdf_out = ctx.coast.sdf_at(res.x, res.y)
            j, i = ctx.grid.index_of(res.x, res.y)
            j = np.clip(j.astype(int), 0, ctx.grid.ny - 1)
            i = np.clip(i.astype(int), 0, ctx.grid.nx - 1)
            near_outside = ctx.outside[j, i]
            extra = {
                "outside_steps": int(near_outside.sum()),
                "min_sdf_km": float(np.nanmin(sdf_out) / 1e3),
                "wrapped_requests": wx.n_wrapped_requests,
                "clamped_power_steps": int(ctx.pm.n_clamped),
            }
            if hasattr(pol, "results"):
                extra["refine_calls"] = len(pol.results)
            if n == "B0":
                extra["b0_lonlat"] = [float(v) for v in ctx.grid.to_lonlat(*pol.target)]
            tmp = f.with_suffix(".tmp")
            with open(tmp, "wb") as fh:
                pickle.dump(
                    {
                        "name": n,
                        "date": date,
                        "res": res,
                        "records": records,
                        "metrics": m.__dict__,
                        "wall_s": dt,
                        "members": a.members,
                        "k": a.k,
                        "coast_violations": res.coast_violations,
                        "n_replans": res.n_replans,
                        "extra": extra,
                    },
                    fh,
                )
            tmp.rename(f)
            print(
                f"{n} {date}: {m.energy_kwh / 1e3:.1f} MWh [{dt:.0f} s] viol "
                f"{res.coast_violations} outside {extra['outside_steps']}",
                flush=True,
            )


if __name__ == "__main__":
    main()
