"""Benchmark of the continuous refiner (DES-860 §7.2): 48 h at 30 min warm-started from a DP path.

For N random (start, date) cases on the synthetic weather: B1 DP (3 h, 5 d) on the control
forecast, refine the first 48 h (96 stages), report solve time, iterations, energy gain vs the DP
path (same envelope power model, evaluated sim-style on the forecast wind and on the truth).
"""

import argparse
import time

import numpy as np

from horizon.geo.coast import build_basin_coast
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.refine import refine_plan, warm_start_from_path
from horizon.sim import DeterministicMPCPolicy, DirectPowerModel, EnvelopePowerModel
from horizon.sim.simulator import _jacobian, sample_wind
from horizon.weather.synthetic import SyntheticWeather

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0


def track_energy(wind, pm, grid, t0, dt, x, y):
    """Sim-style energy [kWh] of the straight-line track through nodes (x, y)."""
    jac = _jacobian(grid)
    e = 0.0
    for k in range(x.size - 1):
        j, i = (int(np.clip(a, 0, m - 1)) for a, m in zip(grid.index_of(x[k], y[k]), grid.shape,
                                                          strict=True))
        gv = np.linalg.solve(jac[j, i], [x[k + 1] - x[k], y[k + 1] - y[k]]) / dt
        sub = 4
        ts = t0 + dt * (k + (np.arange(sub) + 0.5) / sub)
        f = (np.arange(sub) + 0.5) / sub
        u, v = sample_wind(wind, ts, x[k] + f * (x[k + 1] - x[k]), y[k] + f * (y[k + 1] - y[k]))
        e += float(np.mean(pm.power_kw(u, v, gv[0], gv[1]))) * dt / 3600.0
    return e


def main(n_cases=20, seed=7, T=30 * DAY):
    rng = np.random.default_rng(seed)
    coast = build_basin_coast(40e3)
    grid = coast.grid
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    env = build_envelope(polar)
    pm = EnvelopePowerModel(env, fallback=DirectPowerModel(polar, hold))
    wx = SyntheticWeather(grid, EPOCH, T, seed=101)
    truth = wx.truth()
    pol = DeterministicMPCPolicy(polar, hold, coast, horizon_days=5.0)
    lon, lat = grid.lonlat_mesh()
    ok = (coast.sdf > 150e3) & (lon > -30) & (lon < 0) & (lat > 40) & (lat < 58)
    cells = np.argwhere(ok)
    rows = []
    for c in range(n_cases):
        t0 = float(rng.integers(0, 20) * 6 * 3600.0)
        j, i = cells[rng.integers(len(cells))]
        x0, y0 = grid.x0 + i * grid.dx, grid.y0 + j * grid.dx
        ens = wx.forecast(t0, 5 * DAY, 1)
        from horizon.dp import solve_dp
        res = solve_dp(ens.member(0), t0, 40, 3 * 3600.0, polar, hold, coast, stencil=pol._stencil)
        path = res.path(j, i, 0)
        n = 96
        warm = warm_start_from_path(path, grid, 3 * 3600.0, t0, x0, y0, n, 1800.0)
        w1 = wx.forecast(t0, 48 * 3600.0, 1, dt_s=3600.0).member(0)
        term = res.V[16].astype(float)
        t1 = time.perf_counter()
        r = refine_plan(w1, x0, y0, t0, term, env, coast, warm, max_iter=200)
        wall = time.perf_counter() - t1
        e_w = track_energy(w1, pm, grid, t0, 1800.0, *warm)
        e_r = track_energy(w1, pm, grid, t0, 1800.0, r.x, r.y)
        tw = track_energy(truth, pm, grid, t0, 1800.0, *warm)
        tr = track_energy(truth, pm, grid, t0, 1800.0, r.x, r.y)
        rows.append((wall, r.setup_time_s, r.solve_time_s, r.iterations, r.used_warm_start,
                     r.status, e_w, e_r, tw, tr, r.objective_kwh - r.warm_objective_kwh,
                     r.max_violation))
        print(f"case {c:2d} {r.status:28s} it={r.iterations:3d} setup={r.setup_time_s:5.2f}s "
              f"solve={r.solve_time_s:5.2f}s warmfb={r.used_warm_start!s:5} "
              f"E_dp={e_w:8.0f} E_ref={e_r:8.0f} ({100 * (e_r - e_w) / abs(e_w):+5.1f}%) "
              f"obj gain={rows[-1][10]:7.0f} truth gain={tr - tw:7.0f} vio={r.max_violation:.1e}")
    a = np.array([[float(v) if not isinstance(v, str) else 0 for v in r] for r in rows])
    print(f"\nmedian solve {np.median(a[:, 2]):.2f} s, setup {np.median(a[:, 1]):.2f} s, "
          f"iters median {np.median(a[:, 3]):.0f}; fallback rate {a[:, 4].mean():.0%}")
    print(f"mean energy gain on forecast: {np.mean(a[:, 7] - a[:, 6]):.0f} kWh "
          f"({100 * np.mean((a[:, 7] - a[:, 6]) / np.abs(a[:, 6])):.1f}%); "
          f"on truth: {np.mean(a[:, 9] - a[:, 8]):.0f} kWh")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    main(ap.parse_args().n)
