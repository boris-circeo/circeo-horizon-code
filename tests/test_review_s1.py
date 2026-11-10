"""Independent-review regression tests for Sprint 1 (causality, true-frame winds, energy)."""

import numpy as np
from pyproj import Geod
from scipy.interpolate import RegularGridInterpolator

from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope, envelope_lookup
from horizon.sim import DeterministicMPCPolicy, DirectPowerModel, EnvelopePowerModel, run_mission
from horizon.weather.synthetic import Storm, SyntheticParams, SyntheticWeather

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0


def test_control_forecast_ignores_future_truth():
    """Control forecast at t does not change if storms born after t + foresight, the regime
    index after t and the truth noise after t are altered."""
    grid = Grid.from_bbox(-45, 5, 35, 65, 80e3)
    iss = 4 * DAY
    a = SyntheticWeather(grid, EPOCH, 12 * DAY, seed=3)
    b = SyntheticWeather(grid, EPOCH, 12 * DAY, seed=3)
    b.storms = [s for s in b.storms if s.t0_s <= iss + 3 * DAY]
    b._nao[b._nao_t > iss + 3600] = 99.0
    b._truth_noise()[int(iss / 3600) + 2:] = 55.0
    fa, fb = a.forecast(iss, 5 * DAY, 2), b.forecast(iss, 5 * DAY, 2)
    assert np.array_equal(fa.uv[0], fb.uv[0])


def test_storm_circulation_is_cyclonic_in_true_frame_far_from_centre():
    grid = Grid.from_bbox(-45, 5, 35, 65, 80e3)
    p = SyntheticParams(genesis_rate_per_day=0.0, noise_sigma_ms=0.0)
    w = SyntheticWeather(grid, EPOCH, 6 * DAY, params=p, seed=1)
    lon0, lat0 = -40.0, 60.0  # large grid convergence
    gx, gy = grid.to_xy(lon0, lat0)
    w.storms = [Storm(0.0, 5 * DAY, 25.0, 800e3, np.tile([gx, gy], (40, 1)), np.zeros((40, 2)))]
    uv = w._to_true(w._render_storms(w.storms, np.array([2 * DAY])))[0]
    geod = Geod(ellps="WGS84")
    # (azimuth of the sample from the centre, sign of u, sign of v) for counter-clockwise flow
    for az, su, sv in ((0, -1, 0), (90, 0, 1), (180, 1, 0), (270, 0, -1)):
        lo, la, _ = geod.fwd(lon0, lat0, az, 400e3)
        j, i = (int(round(a)) for a in grid.index_of(*grid.to_xy(lo, la)))
        u, v = uv[j, i]
        assert (su == 0 or u * su > 5.0) and (sv == 0 or v * sv > 5.0)


def test_mission_energy_matches_independent_recomputation():
    """Energy of a closed-loop mission recomputed from the logged track only (geodesic
    velocities, scipy interpolation of the truth, envelope lookup)."""
    grid = Grid.from_bbox(-12, 4, 38, 54, 40e3)
    sea = CoastModel(grid, np.full(grid.shape, 1e6, np.float32))
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    env = build_envelope(polar)
    pm = EnvelopePowerModel(env, fallback=DirectPowerModel(polar, hold))
    t_end = 4 * DAY
    wx = SyntheticWeather(grid, EPOCH, t_end, seed=7)
    truth = wx.truth(3600.0)
    pol = DeterministicMPCPolicy(polar, hold, sea, horizon_days=2.0)
    r = run_mission(pol, wx, truth, (-4.0, 46.0), t_end, pm, sea)
    az, _, dist = Geod(ellps="WGS84").inv(r.lon[:-1], r.lat[:-1], r.lon[1:], r.lat[1:])
    ve, vn = dist / r.sim_dt_s * np.sin(np.radians(az)), dist / r.sim_dt_s * np.cos(np.radians(az))
    f = RegularGridInterpolator((truth.times_s, grid.y, grid.x), truth.uv, bounds_error=False,
                                fill_value=None)
    tm = r.t_s[:-1] + 0.5 * r.sim_dt_s
    uv = f(np.column_stack([tm, 0.5 * (r.y[:-1] + r.y[1:]), 0.5 * (r.x[:-1] + r.x[1:])]))
    p = np.empty(tm.size)
    for k, (u, v) in enumerate(uv):
        tws = np.hypot(u, v)
        q = envelope_lookup(env.reward, env.axes, tws, -(ve[k] * u + vn[k] * v) / tws,
                            (ve[k] * v - vn[k] * u) / tws)
        p[k] = q if np.isfinite(q) else pm.fallback.power_kw(u, v, ve[k], vn[k])
    e = p.sum() * r.sim_dt_s / 3600.0
    assert abs(e / r.energy_kwh[-1] - 1.0) < 1e-3
