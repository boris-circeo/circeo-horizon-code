"""Tests of the closed-loop simulator, policies and metrics (DES-860 §8.1-8.3)."""

import numpy as np
import pytest

from horizon.dp import build_stencil
from horizon.geo.coast import CoastModel, build_basin_coast
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    CausalityError,
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    ForecastProvider,
    HoldAtPointPolicy,
    OraclePolicy,
    best_climatological_point,
    mission_metrics,
    run_mission,
)
from horizon.sim.metrics import regret
from horizon.sim.simulator import sample_wind
from horizon.weather.fields import Ensemble, WindField
from horizon.weather.synthetic import SyntheticWeather

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0
START = (-4.0, 46.0)


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold(polar):
    return hold_power_curve(polar)


@pytest.fixture(scope="module")
def pm(polar, hold):
    return EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))


@pytest.fixture(scope="module")
def grid():
    return Grid.from_bbox(-12, 4, 38, 54, 40e3)


@pytest.fixture(scope="module")
def sea(grid):
    return CoastModel(grid, np.full(grid.shape, 1e6, np.float32))


class UniformWeather:
    """Stationary uniform wind (u, v) [m/s]; perfect forecast. Test double of SyntheticWeather."""

    def __init__(self, grid, u, v):
        self.grid, self.uv = grid, np.array([u, v], np.float32)
        self.issued = []

    def field(self, times):
        uv = np.broadcast_to(self.uv, (len(times),) + self.grid.shape + (2,)).copy()
        return WindField(self.grid, EPOCH, np.asarray(times, float), uv)

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        self.issued.append(issue_s)
        t = issue_s + dt_s * np.arange(int(round(horizon_s / dt_s)) + 1)
        f = self.field(t)
        return Ensemble(self.grid, EPOCH, issue_s, t, f.uv[None], np.ones(1))

    def truth(self, dt_s=3600.0, end_s=3 * DAY):
        return self.field(np.arange(0, end_s + 1, dt_s))


# ----------------------------------------------------------------------------- causality
def test_provider_refuses_future_forecast():
    wx = UniformWeather(Grid.from_bbox(-12, 4, 38, 54, 40e3), 10.0, 0.0)
    prov = ForecastProvider(wx, now_s=6 * 3600.0)
    prov.forecast(6 * 3600.0, 3 * 3600.0, 1)
    prov.forecast(0.0, 3 * 3600.0, 1)
    with pytest.raises(CausalityError):
        prov.forecast(6 * 3600.0 + 1.0, 3 * 3600.0, 1)


def test_cheating_policy_is_stopped(grid, sea, pm):
    class Cheater:
        def plan(self, t_s, x, y, provider):
            provider.forecast(t_s + 3600.0, 3 * 3600.0, 1)

    wx = UniformWeather(grid, 10.0, 0.0)
    with pytest.raises(CausalityError):
        run_mission(Cheater(), wx, wx.truth(), START, DAY, pm, sea)


def test_mpc_only_uses_past_issue_times(grid, sea, pm, polar, hold):
    wx = UniformWeather(grid, 10.0, 0.0)
    pol = DeterministicMPCPolicy(polar, hold, sea, horizon_days=1.0)
    res = run_mission(pol, wx, wx.truth(), START, DAY, pm, sea)
    assert list(res.replan_times_s) == [0.0, 6 * 3600.0, 12 * 3600.0, 18 * 3600.0]
    assert wx.issued == list(res.replan_times_s)


# ----------------------------------------------------------------------------- accounting
def test_hold_energy_is_power_times_time(grid, sea, pm):
    wx = UniformWeather(grid, 10.0, 0.0)
    x, y = grid.to_xy(*START)
    res = run_mission(HoldAtPointPolicy(x, y), wx, wx.truth(), START, 2 * DAY, pm, sea)
    p_hold = float(pm.power_kw(10.0, 0.0, 0.0, 0.0))
    assert res.energy_kwh[-1] == pytest.approx(p_hold * 48.0, rel=1e-9)
    assert mission_metrics(res).hold_fraction == 1.0
    assert mission_metrics(res).distance_km == pytest.approx(0.0, abs=1e-6)


def test_energy_is_integral_of_power(grid, sea, pm, polar, hold):
    wx = SyntheticWeather(grid, EPOCH, 3 * DAY, seed=5)
    tr = wx.truth()
    pol = DeterministicMPCPolicy(polar, hold, sea, horizon_days=1.0)
    res = run_mission(pol, wx, tr, START, 2 * DAY, pm, sea)
    assert res.energy_kwh[0] == 0.0
    assert np.allclose(np.diff(res.energy_kwh), res.power_kw * res.sim_dt_s / 3600.0)
    # independent recomputation on the track
    t = res.t_s
    tm, xm, ym = 0.5 * (t[1:] + t[:-1]), 0.5 * (res.x[1:] + res.x[:-1]), 0.5 * (
        res.y[1:] + res.y[:-1])
    u, v = sample_wind(tr, tm, xm, ym)
    ve, vn = res.speed_ms * np.sin(np.radians(res.heading_deg)), res.speed_ms * np.cos(
        np.radians(res.heading_deg))
    assert np.allclose(pm.power_kw(u, v, ve, vn), res.power_kw)
    # displacement consistent with commanded ground speed (grid-metre scale error < 4 %)
    path_km = np.hypot(np.diff(res.x), np.diff(res.y)).sum() / 1e3
    assert path_km == pytest.approx(mission_metrics(res).distance_km, rel=0.04)
    assert -500.0 <= res.power_kw.min() and res.power_kw.max() <= 3000.0


def test_sample_wind_bilinear_and_time(grid):
    t = np.array([0.0, 3600.0])
    uv = np.zeros((2, grid.ny, grid.nx, 2), np.float32)
    uv[1, ..., 0] = 4.0
    uv[:, :, 1:, 1] = 2.0  # v = 2 for i >= 1
    w = WindField(grid, EPOCH, t, uv)
    x, y = grid.x0 + 0.5 * grid.dx, grid.y0 + 3 * grid.dx
    u_, v_ = sample_wind(w, 1800.0, x, y)
    assert (u_, v_) == pytest.approx((2.0, 1.0))


# ----------------------------------------------------------------------------- physics
def test_uniform_stationary_wind_mpc_oracle_analytic(grid, sea, pm, polar, hold):
    """Stationary uniform wind: B1 = oracle = best constant stencil arc repeated (<= 2 %)."""
    tws = float(polar.tws[np.argmin(abs(polar.tws - 10.0))])
    wx = UniformWeather(grid, tws, 0.0)
    T = 2 * DAY
    tr = wx.truth()
    j0, i0 = grid.index_of(*grid.to_xy(*START))
    start = grid.to_lonlat(grid.x0 + i0 * grid.dx, grid.y0 + j0 * grid.dx)  # cell centre
    st = build_stencil(grid, 3 * 3600.0)
    spd, hdg = st.length_m[j0, i0] / st.dt_s, np.radians(st.heading_deg[j0, i0])
    p_arcs = pm.power_kw(tws, 0.0, spd * np.sin(hdg), spd * np.cos(hdg))
    analytic = np.nanmax(p_arcs[st.valid[j0, i0]]) * T / 3600.0
    # the continuous optimum (any velocity, |v| <= 8 m/s) bounds it from above, within 3 %
    env = pm.env
    vp, vq = np.meshgrid(env.v_par_axis(), env.v_perp_axis(), indexing="ij")
    it = int(round((tws - env.tws0) / env.dtws))
    p_cont = np.nanmax(np.where(np.hypot(vp, vq) <= 8.0, env.reward[it], np.nan))
    assert analytic <= p_cont * T / 3600.0 * 1.001
    assert analytic >= 0.97 * p_cont * T / 3600.0
    j = {}
    for name, pol in (("b1", DeterministicMPCPolicy(polar, hold, sea, horizon_days=1.0)),
                      ("oracle", OraclePolicy(tr, polar, hold, sea, T))):
        j[name] = mission_metrics(run_mission(pol, wx, tr, start, T, pm, sea)).energy_kwh
    assert j["b1"] == pytest.approx(analytic, rel=0.02)
    assert j["oracle"] == pytest.approx(analytic, rel=0.02)
    assert j["b1"] <= analytic * 1.001 and j["oracle"] <= analytic * 1.001


def test_oracle_dominates_policies(grid, sea, pm, polar, hold):
    T = 4 * DAY
    wx = SyntheticWeather(grid, EPOCH, T, seed=7)
    tr = wx.truth()
    st = grid.to_xy(*START)
    energies = {}
    for name, pol in (("b0", HoldAtPointPolicy(*st)),
                      ("b1", DeterministicMPCPolicy(polar, hold, sea, horizon_days=2.0)),
                      ("oracle", OraclePolicy(tr, polar, hold, sea, T))):
        energies[name] = mission_metrics(run_mission(pol, wx, tr, START, T, pm, sea)).energy_kwh
    tol = 0.01 * energies["oracle"]  # sim integrates hourly truth at 15 min, DP at 3 h nodes
    assert energies["oracle"] + tol >= energies["b0"]
    assert energies["oracle"] + tol >= energies["b1"]
    assert regret(energies["oracle"], energies["b1"]) > -0.01


def test_no_coast_violation_and_reproducibility(polar, hold, pm):
    g = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = build_basin_coast(40e3)
    assert coast.grid == g
    T = 3 * DAY
    start = (-6.5, 47.0)
    out = []
    for _ in range(2):
        wx = SyntheticWeather(g, EPOCH, T, seed=101)
        pol = DeterministicMPCPolicy(polar, hold, coast, horizon_days=2.0)
        out.append(run_mission(pol, wx, wx.truth(), start, T, pm, coast))
    assert out[0].coast_violations == 0
    assert np.array_equal(out[0].energy_kwh, out[1].energy_kwh)
    assert np.array_equal(out[0].lon, out[1].lon)


def test_best_climatological_point(grid, sea, pm):
    t = np.array([0.0, 3 * 3600.0])
    uv = np.zeros((2, grid.ny, grid.nx, 2), np.float32)
    uv[..., 0] = 3.0
    uv[:, 20:23, 30:33, 0] = 10.0  # a windy patch
    tr = WindField(grid, EPOCH, t, uv)
    x, y, mean = best_climatological_point([tr], pm, sea, grid.to_xy(*START), sdf_min_m=50e3)
    j, i = grid.index_of(x, y)
    assert 20 <= j <= 22 and 30 <= i <= 32
    assert mean == pytest.approx(float(pm.power_kw(10.0, 0.0, 0.0, 0.0)))


def test_direct_power_model(polar, hold):
    dm = DirectPowerModel(polar, hold)
    # wind from the west (u > 0 toward east), heading north = beam reach, 4 m/s
    p = dm.power_kw(10.0, 0.0, 0.0, 4.0)
    assert p == pytest.approx(float(polar(10.0, 90.0, 4.0)))
    assert dm.power_kw(10.0, 0.0, 0.0, 0.0) == pytest.approx(
        float(np.interp(10.0, hold.tws, hold.p_hold)))
