"""Benchmark of the backward DP (DES-860 §7.4): warm timings on synthetic wind, 2 cores."""

import time

import numpy as np

from horizon.dp import build_stencil, solve_dp
from horizon.geo.coast import CoastModel, build_basin_coast
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.weather.fields import WindField

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")


def synth_wind(grid, n, dt):
    X, Y = grid.xy_mesh()
    t = dt * np.arange(n + 1)
    uv = np.empty((n + 1, grid.ny, grid.nx, 2), np.float32)
    for k, tk in enumerate(t):
        s = 9 + 5 * np.sin(X / 6e5 + tk / 8e4) * np.cos(Y / 5e5)
        d = np.radians(250 + 80 * np.sin(Y / 7e5 - tk / 1e5))
        uv[k, ..., 0], uv[k, ..., 1] = -s * np.sin(d), -s * np.cos(d)
    return WindField(grid, EPOCH, t, uv)


def run(label, grid, coast, n, dt, polar, hold, max_span=1):
    wind = synth_wind(grid, n, dt)
    t0 = time.perf_counter()
    st = build_stencil(grid, dt, max_span=max_span)
    t_st = time.perf_counter() - t0
    solve_dp(wind, 0.0, 1, dt, polar, hold, coast, stencil=st)  # JIT warm-up
    t0 = time.perf_counter()
    res = solve_dp(wind, 0.0, n, dt, polar, hold, coast, stencil=st)
    t = time.perf_counter() - t0
    n_arcs = int(np.count_nonzero(np.isfinite(res.V[0]))) * st.n_arcs * n
    print(f"{label:34s} grid {grid.ny}x{grid.nx} K={st.n_arcs} n={n}: stencil {t_st:5.2f} s, "
          f"DP {t:6.3f} s ({n_arcs / t / 1e6:6.1f} M arcs/s)")


def main():
    polar, hold = synthetic_polar(), hold_power_curve(synthetic_polar())
    g = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = CoastModel(g, np.full(g.shape, 1e6, np.float32))  # open sea: worst case
    for n in (40, 104):
        run(f"basin 40 km, 3 h, {n} steps", g, coast, n, 3 * 3600.0, polar, hold)
    for ms in (1, 2, 3):  # macro arcs, 15 d, single scenario (default span 2)
        run(f"basin 40 km, 3 h, 120 steps, span {ms}", g, coast, 120, 3 * 3600.0, polar, hold, ms)
    # 10 km, 1 h, 48 steps on a 1000x1000 km subdomain
    c10 = build_basin_coast(10e3)
    sub = Grid(c10.grid.crs_wkt, -500e3, -500e3, 10e3, 101, 101)
    lon, lat = sub.lonlat_mesh()
    cs = CoastModel(sub, c10.sdf_at_lonlat(lon, lat).astype(np.float32))
    cs = CoastModel(sub, np.where(np.isfinite(cs.sdf), cs.sdf, 1e6).astype(np.float32))
    run("subdomain 1000 km, 10 km, 1 h", sub, cs, 48, 3600.0, polar, hold)
    run("full basin 10 km, 1 h", c10.grid, c10, 48, 3600.0, polar, hold)


if __name__ == "__main__":
    main()
