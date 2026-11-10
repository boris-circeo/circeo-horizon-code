"""Tests of the continuous refiner (DES-860 §4.10, §6.5, A.4) and its MPC wrapper."""

import numpy as np
import pytest

from horizon.dp import build_stencil, solve_dp
from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.refine import refine_plan, warm_start_from_path
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    ForecastProvider,
    run_mission,
)
from horizon.sim.policies_refine import RefinedMPCPolicy
from horizon.sim.simulator import _jacobian, sample_wind
from horizon.weather.fields import Ensemble, WindField

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
H = 3600.0


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold(polar):
    return hold_power_curve(polar)


@pytest.fixture(scope="module")
def env(polar):
    return build_envelope(polar)


@pytest.fixture(scope="module")
def pm(env, polar, hold):
    return EnvelopePowerModel(env, fallback=DirectPowerModel(polar, hold))


@pytest.fixture(scope="module")
def grid():
    return Grid.from_bbox(-12, 4, 38, 54, 40e3)


@pytest.fixture(scope="module")
def sea(grid):
    return CoastModel(grid, np.full(grid.shape, 1e6, np.float32))


def uniform_wind(grid, u, v, t_end=60 * H, dt=3 * H):
    t = np.arange(0, t_end + 1, dt)
    uv = np.broadcast_to(np.array([u, v], np.float32), (t.size,) + grid.shape + (2,)).copy()
    return WindField(grid, EPOCH, t, uv)


def varying_wind(grid, t_end=60 * H, dt=3 * H):
    X, Y = grid.xy_mesh()
    t = np.arange(0, t_end + 1, dt)
    uv = np.empty((t.size,) + grid.shape + (2,), np.float32)
    for k, tk in enumerate(t):
        s = 9 + 5 * np.sin(X / 6e5 + tk / 8e4) * np.cos(Y / 5e5)
        d = np.radians(250 + 80 * np.sin(Y / 7e5 - tk / 1e5))
        uv[k, ..., 0], uv[k, ..., 1] = -s * np.sin(d), -s * np.cos(d)
    return WindField(grid, EPOCH, t, uv)


def track_energy(wind, pm, grid, t0, dt, x, y):
    """Independent sim-style energy [kWh] of the straight-line track through nodes (x, y)."""
    jac = _jacobian(grid)
    e = 0.0
    for k in range(x.size - 1):
        j, i = (int(np.clip(a, 0, m - 1)) for a, m in zip(grid.index_of(x[k], y[k]), grid.shape,
                                                          strict=True))
        gv = np.linalg.solve(jac[j, i], [x[k + 1] - x[k], y[k + 1] - y[k]]) / dt
        f = (np.arange(4) + 0.5) / 4
        u, v = sample_wind(wind, t0 + dt * (k + f), x[k] + f * (x[k + 1] - x[k]),
                           y[k] + f * (y[k + 1] - y[k]))
        e += float(np.mean(pm.power_kw(u, v, gv[0], gv[1]))) * dt / 3600.0
    return e


def line(x0, y0, vx, vy, n, dt=1800.0):
    k = np.arange(n + 1) * dt
    return x0 + vx * k, y0 + vy * k


# ----------------------------------------------------------------------------- analytic optimum
def test_uniform_wind_reproduces_analytic_optimum(grid, sea, env, pm):
    """In a uniform steady wind the optimum is a constant velocity maximising the envelope."""
    u0 = 10.0
    wind = uniform_wind(grid, u0, 0.0)
    x0, y0 = grid.to_xy(-4.0, 44.0)
    n = 24
    # analytic: max over velocities of the tabulated reward at TWS = u0 (linear in TWS)
    k = u0 / env.dtws
    i = int(k)
    tab = (1 - (k - i)) * env.reward[i] + (k - i) * env.reward[i + 1]
    p_star = float(np.nanmax(tab))
    # due north at 3.6 m/s: inside the basin of the single-heading ridge (the reward is
    # max(direct, f_avail * E), flat on the mixing plateau below ~3.3 m/s: a local solver started
    # there has no gradient to find the ridge)
    warm = line(x0, y0, 0.0, 3.6, n)
    r = refine_plan(wind, x0, y0, 0.0, np.zeros(grid.shape), env, sea, warm, horizon_s=n * 1800.0,
                    margin_m=300e3)
    assert not r.used_warm_start and r.success
    e_star = p_star * n * 0.5
    assert r.energy_kwh == pytest.approx(e_star, rel=0.01)
    assert r.energy_kwh <= e_star * 1.005  # cannot beat the envelope maximum
    # independent sim-style evaluation of the returned track
    assert track_energy(wind, pm, grid, 0.0, 1800.0, r.x, r.y) == pytest.approx(e_star, rel=0.012)
    # smooth controls: constant velocity up to a small ripple
    v = np.hypot(r.ve, r.vn)
    assert np.abs(np.diff(r.ve)).max() < 0.1 and np.abs(np.diff(r.vn)).max() < 0.1
    assert v.min() > 0.5 * v.max() or v.max() < 1.0
    assert np.all(r.power_kw > 0.95 * p_star)


# ----------------------------------------------------------------------------- vs DP warm start
def test_refined_objective_not_worse_and_energy_gain(grid, sea, polar, hold, env, pm):
    wind = varying_wind(grid)
    x0, y0 = grid.to_xy(-6.0, 46.0)
    st = build_stencil(grid, 3 * H)
    res = solve_dp(wind, 0.0, 8, 3 * H, polar, hold, sea, stencil=st)
    j0, i0 = (int(a) for a in np.round(grid.index_of(x0, y0)))
    x0, y0 = grid.x0 + i0 * grid.dx, grid.y0 + j0 * grid.dx
    n = 48
    warm = warm_start_from_path(res.path(j0, i0, 0), grid, 3 * H, 0.0, x0, y0, n, 1800.0)
    r = refine_plan(wind, x0, y0, 0.0, res.V[8].astype(float), env, sea, warm, horizon_s=n * 1800.0)
    assert r.objective_kwh >= r.warm_objective_kwh
    assert not r.used_warm_start
    e_dp = track_energy(wind, pm, grid, 0.0, 1800.0, *warm)
    e_ref = track_energy(wind, pm, grid, 0.0, 1800.0, r.x, r.y)
    assert e_ref > e_dp  # continuous velocities beat the DP stencil
    assert r.warm_energy_kwh == pytest.approx(e_dp, rel=0.02)  # spline surrogate ~ sim-style
    assert r.energy_kwh == pytest.approx(e_ref, rel=0.02)
    assert r.max_violation < 1e-3
    assert np.all(np.hypot(r.ve, r.vn) <= 8.0 + 1e-6)
    assert np.allclose(r.t_s, 1800.0 * np.arange(n + 1))


def test_fallback_on_solver_failure_returns_warm_start(grid, sea, env):
    wind = uniform_wind(grid, 10.0, 0.0)
    x0, y0 = grid.to_xy(-4.0, 44.0)
    warm = line(x0, y0, 0.0, 3.0, 8)
    r = refine_plan(wind, x0, y0, 0.0, np.zeros(grid.shape), env, sea, warm, horizon_s=8 * 1800.0,
                    ipopt_options={"ipopt.linear_solver": "no_such_solver"})
    assert r.used_warm_start and not r.success
    assert np.allclose(r.x, warm[0]) and np.allclose(r.y, warm[1])
    assert r.objective_kwh == pytest.approx(r.warm_objective_kwh)


def test_never_worse_than_warm_start_when_truncated(grid, sea, env):
    wind = varying_wind(grid)
    x0, y0 = grid.to_xy(-6.0, 46.0)
    warm = line(x0, y0, 2.0, 2.0, 24)
    r = refine_plan(wind, x0, y0, 0.0, np.zeros(grid.shape), env, sea, warm, horizon_s=24 * 1800.0,
                    max_iter=3)
    assert r.objective_kwh >= r.warm_objective_kwh - 1e-6


# ----------------------------------------------------------------------------- coast, terminal
def test_coast_clearance_respected_when_pulled_to_shore(grid, env):
    xc = grid.to_xy(-4.0, 46.0)[0] + 250e3  # coast: land east of x = xc
    X, _ = grid.xy_mesh()
    coast = CoastModel(grid, (xc - X).astype(np.float32))
    wind = uniform_wind(grid, 8.0, 0.0)
    x0, y0 = grid.to_xy(-4.0, 46.0)
    n = 24
    pull = (X - x0) / 1e3 * 50.0  # +50 kWh per km eastwards: strong pull towards the coast
    warm = line(x0, y0, 3.0, 0.0, n)
    d_min = 20e3
    r = refine_plan(wind, x0, y0, 0.0, pull, env, coast, warm, horizon_s=n * 1800.0, d_min=d_min,
                    margin_m=200e3)
    xm = np.concatenate([r.x, 0.5 * (r.x[1:] + r.x[:-1])])
    ym = np.concatenate([r.y, 0.5 * (r.y[1:] + r.y[:-1])])
    assert coast.sdf_at(xm, ym).min() >= d_min - 50.0  # bilinear SDF, linear here: exact-ish
    assert r.x[-1] > warm[0][-1] + 30e3  # moved much closer to the coast than the warm start
    assert xc - r.x[-1] == pytest.approx(d_min, abs=3e3)  # constraint active at the end


def test_terminal_value_pulls_towards_high_value_region(grid, sea, env):
    wind = uniform_wind(grid, 10.0, 0.0)
    x0, y0 = grid.to_xy(-4.0, 44.0)
    X, Y = grid.xy_mesh()
    xt, yt = x0 + 120e3, y0 + 80e3
    blob = 2e5 * np.exp(-((X - xt) ** 2 + (Y - yt) ** 2) / (2 * 150e3**2))
    n = 16
    warm = line(x0, y0, 0.0, 0.0, n)  # warm start: stay put
    kw = dict(horizon_s=n * 1800.0, margin_m=300e3)
    r0 = refine_plan(wind, x0, y0, 0.0, np.zeros(grid.shape), env, sea, warm, **kw)
    r1 = refine_plan(wind, x0, y0, 0.0, blob, env, sea, warm, **kw)
    d0 = np.hypot(r0.x[-1] - xt, r0.y[-1] - yt)
    d1 = np.hypot(r1.x[-1] - xt, r1.y[-1] - yt)
    assert d1 < 0.6 * d0 and d1 < 60e3
    assert r1.terminal_kwh > r0.terminal_kwh
    # callable terminal field is equivalent to the array
    r2 = refine_plan(wind, x0, y0, 0.0, lambda x, y: 2e5 * np.exp(
        -((x - xt) ** 2 + (y - yt) ** 2) / (2 * 150e3**2)), env, sea, warm, **kw)
    assert np.hypot(r2.x[-1] - r1.x[-1], r2.y[-1] - r1.y[-1]) < 5e3


def test_timing_48h_at_30min(grid, sea, polar, hold, env):
    """96 stages: setup + solve within a loose bound (benchmark target 0.3-2 s)."""
    wind = varying_wind(grid)
    x0, y0 = grid.to_xy(-6.0, 46.0)
    st = build_stencil(grid, 3 * H)
    res = solve_dp(wind, 0.0, 16, 3 * H, polar, hold, sea, stencil=st)
    j0, i0 = (int(a) for a in np.round(grid.index_of(x0, y0)))
    x0, y0 = grid.x0 + i0 * grid.dx, grid.y0 + j0 * grid.dx
    warm = warm_start_from_path(res.path(j0, i0, 0), grid, 3 * H, 0.0, x0, y0, 96, 1800.0)
    r = refine_plan(wind, x0, y0, 0.0, res.V[16].astype(float), env, sea, warm)
    assert r.setup_time_s + r.solve_time_s < 15.0
    assert r.objective_kwh >= r.warm_objective_kwh


# ----------------------------------------------------------------------------- policy wrapper
class UniformWeather:
    def __init__(self, grid, u, v):
        self.grid, self.uv = grid, np.array([u, v], np.float32)

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        t = issue_s + dt_s * np.arange(int(round(horizon_s / dt_s)) + 1)
        uv = np.broadcast_to(self.uv, (t.size,) + self.grid.shape + (2,)).copy()
        return Ensemble(self.grid, EPOCH, issue_s, t, uv[None], np.ones(1))

    def truth(self, dt_s=3600.0, end_s=4 * 86400.0):
        t = np.arange(0, end_s + 1, dt_s)
        uv = np.broadcast_to(self.uv, (t.size,) + self.grid.shape + (2,)).copy()
        return WindField(self.grid, EPOCH, t, uv)


def test_refined_policy_plan_and_closed_loop(grid, sea, polar, hold, pm):
    wx = UniformWeather(grid, 10.0, 0.0)
    base = DeterministicMPCPolicy(polar, hold, sea, horizon_days=3.0)
    pol = RefinedMPCPolicy(base)
    start = (-4.0, 46.0)
    x0, y0 = grid.to_xy(*start)
    plan = pol.plan(0.0, x0, y0, ForecastProvider(wx, 0.0, 2 * 86400.0))
    assert plan.dt_s == 1800.0 and plan.x.size == 96
    assert pol.last_refine is not None and not pol.last_refine.used_warm_start
    # the plan is a valid simulator input: closed loop, no coast violation, not worse than B1
    res_ref = run_mission(pol, wx, wx.truth(), start, 86400.0, pm, sea)
    res_b1 = run_mission(DeterministicMPCPolicy(polar, hold, sea, horizon_days=3.0), wx,
                         wx.truth(), start, 86400.0, pm, sea)
    assert res_ref.coast_violations == 0
    assert res_ref.energy_kwh[-1] >= 0.99 * res_b1.energy_kwh[-1]
    assert all(r.objective_kwh >= r.warm_objective_kwh - 1e-6 for r in pol.results)


def test_dense_coast_clearance_refiner_and_dp(grid, env):
    """Regression (S3): SDF >= d_min along the WHOLE path, not only at nodes/mid-points."""
    from horizon.geo.coast import CoastModel as _CM

    X, Y = grid.xy_mesh()
    cx, cy = grid.to_xy(-4.0, 46.0)
    cx, cy = cx + 260e3, cy + 40e3
    sdf = (np.hypot(X - cx, Y - cy) - 80e3).astype(np.float32)  # round island
    coast = _CM(grid, sdf)
    wind = uniform_wind(grid, 8.0, 0.0)
    x0, y0 = grid.to_xy(-4.0, 46.0)
    n = 24
    pull = -np.hypot(X - cx, Y - cy) / 1e3 * 50.0  # pulled towards the island
    warm = line(x0, y0, 3.0, 0.0, n)
    d_min = 20e3
    r = refine_plan(wind, x0, y0, 0.0, pull, env, coast, warm, horizon_s=n * 1800.0, d_min=d_min,
                    margin_m=200e3)
    xs = np.concatenate([np.linspace(a, b, 21) for a, b in zip(r.x[:-1], r.x[1:], strict=True)])
    ys = np.concatenate([np.linspace(a, b, 21) for a, b in zip(r.y[:-1], r.y[1:], strict=True)])
    assert coast.sdf_at(xs, ys).min() >= d_min - 50.0


def test_dp_arc_feasibility_dense_sampling():
    from horizon.dp.kernel import arc_feasibility
    from horizon.dp.stencil import build_stencil
    from horizon.geo.coast import CoastModel as _CM
    from horizon.geo.grid import Grid as _G

    g = _G.from_bbox(-12, 4, 38, 54, 40e3)
    X, Y = g.xy_mesh()
    cx, cy = g.to_xy(-4.0, 46.0)
    sdf = (np.hypot(X - cx, Y - cy) - 30e3).astype(np.float32)
    coast = _CM(g, sdf)
    st = build_stencil(g, 3 * 3600.0)
    d_min = 20e3
    ok = arc_feasibility(st.valid, st.di, st.dj, st.length_m, coast.sdf, g.x0, g.y0, g.dx, d_min)
    jj, ii, ss = np.nonzero(ok[:, :, 1:])
    rng = np.random.default_rng(0)
    for q in rng.choice(jj.size, 300, replace=False):
        j, i, s = jj[q], ii[q], ss[q] + 1
        f = np.linspace(0, 1, 81)
        x = g.x0 + (i + f * st.di[s]) * g.dx
        y = g.y0 + (j + f * st.dj[s]) * g.dx
        assert coast.sdf_at(x, y).min() >= d_min - 1.0
