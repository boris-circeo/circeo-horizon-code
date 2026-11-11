"""Sprint 5 test-environment realism: manoeuvre losses, forecast knobs, truth-polar error."""

import numpy as np
import pytest
from test_forecast_model import archive, grid  # noqa: F401  (fixtures)
from test_longrun import DAY, H, make

from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import DirectPowerModel, EnvelopePowerModel, ManoeuvreModel, run_mission
from horizon.sim.longrun import RunInterrupted, run_persistent
from horizon.sim.manoeuvre import apply_manoeuvre_losses, detect_manoeuvres
from horizon.sim.truth_models import make_power_model, perturb_polar
from horizon.weather.forecast_model import ERA5ForecastWeather, ForecastErrorParams

M = ManoeuvreModel()
EPOCH = np.datetime64("2015-01-01T00:00:00")


@pytest.fixture(scope="module")
def polar_fx():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold_fx(polar_fx):
    return hold_power_curve(polar_fx)


@pytest.fixture(scope="module")
def pm_fx(polar_fx, hold_fx):
    return EnvelopePowerModel(build_envelope(polar_fx),
                              fallback=DirectPowerModel(polar_fx, hold_fx))


@pytest.fixture(scope="module")
def sea_grid():
    return Grid.from_bbox(-12, 4, 38, 54, 40e3)


def _kinds(psi, tws=10.0, wind_from=0.0, prev=None, moving=None):
    psi = np.asarray(psi, float)
    wd = np.radians(wind_from)  # wind FROM wind_from -> blows toward wind_from + 180
    u = np.full(psi.size, -tws * np.sin(wd))
    v = np.full(psi.size, -tws * np.cos(wd))
    mv = np.ones(psi.size, bool) if moving is None else moving
    return detect_manoeuvres(psi, u, v, mv, M, prev)


def test_detect_tack_gybe_turn():
    # wind from north (0 deg): heading 45 -> 315 crosses head-to-wind = tack
    k, _ = _kinds([45, 45, 315, 315])
    assert list(k) == [0, 0, 1, 0]
    # heading 135 -> 225 crosses dead downwind = gybe (and the reverse)
    k, _ = _kinds([135, 225, 225, 135])
    assert list(k) == [0, 2, 0, 2]
    # beam reach 90 -> 150: 60 deg turn, same side: large turn; 90 -> 110: nothing
    k, _ = _kinds([90, 150, 170])
    assert list(k) == [0, 3, 0]
    # steady course: nothing; counted exactly once per event
    k, _ = _kinds([60, 60, 60, 60])
    assert k.sum() == 0


def test_detect_hold_resets_and_carry():
    mv = np.array([True, False, True, True])
    k, prev = _kinds([45, 315, 315, 45], moving=mv)  # the flip around the hold is not charged
    assert list(k) == [0, 0, 0, 1]
    assert prev is not None
    # state carried across segments gives the same result as one piece
    ka, pa = _kinds([45, 45], prev=None)
    kb, _ = _kinds([315, 315], prev=pa)
    assert list(ka) + list(kb) == [0, 0, 1, 0]


def test_wind_shift_through_ship_axis_is_a_manoeuvre():
    # constant heading 45, wind from 90 -> wind from 0 -> from 300: crosses head-to-wind side
    psi = np.full(3, 45.0)
    wd = np.radians([20.0, 20.0, 80.0])  # wind from 20 (port) then 80 (starboard of heading 45)
    u, v = -10 * np.sin(wd), -10 * np.cos(wd)
    k, _ = detect_manoeuvres(psi, u, v, np.ones(3, bool), M)
    assert list(k) == [0, 0, 1]


def test_loss_amount():
    p = np.array([1000.0, 1000.0, 1000.0, -200.0])
    kind = np.array([0, 1, 3, 1], np.int8)
    q = apply_manoeuvre_losses(p, kind, 900.0, M)
    assert q[0] == 1000.0
    assert q[1] == pytest.approx(1000.0 - 0.7 * 240 / 900 * 1000.0)
    assert q[2] == pytest.approx(1000.0 - 0.7 * 120 / 900 * 1000.0)
    assert q[3] == -200.0  # a cost is not relieved
    m2 = ManoeuvreModel(tau_scale=2.5, fixed_kwh=10.0)
    q2 = apply_manoeuvre_losses(p, kind, 900.0, m2)
    assert q2[1] == pytest.approx(1000.0 - 0.7 * 600 / 900 * 1000.0 - 10 * 3600 / 900)


def test_off_is_bit_identical_and_on_costs(sea_grid, polar_fx, hold_fx, pm_fx, tmp_path):
    start = (-4.0, 46.0)
    wx, sea, pol = make(sea_grid, polar_fx, hold_fx)
    ref = run_mission(pol, wx, wx.truth(), start, 3 * DAY, pm_fx, sea)
    wx, sea, pol = make(sea_grid, polar_fx, hold_fx)
    off = run_persistent(pol, wx, start, pm_fx, sea, tmp_path / "off", segments=12 * H,
                         manoeuvre=ManoeuvreModel(enabled=False))
    np.testing.assert_array_equal(off.result.power_kw, ref.power_kw)
    wx, sea, pol = make(sea_grid, polar_fx, hold_fx)
    none = run_persistent(pol, wx, start, pm_fx, sea, tmp_path / "none", segments=12 * H)
    np.testing.assert_array_equal(none.result.power_kw, ref.power_kw)
    assert none.result.manoeuvre_kind is None
    # ON: never more energy, manoeuvres counted consistently, kill/resume identical
    wx, sea, pol = make(sea_grid, polar_fx, hold_fx)
    on = run_persistent(pol, wx, start, pm_fx, sea, tmp_path / "on", segments=12 * H,
                        manoeuvre=M)
    assert on.energy_kwh <= off.energy_kwh + 1e-9
    kinds = on.result.manoeuvre_kind
    n = int((kinds > 0).sum())
    assert n == sum(m.n_tack + m.n_gybe + m.n_turn for m in on.segments)
    assert (on.energy_kwh < off.energy_kwh) == (n > 0)
    wx, sea, pol = make(sea_grid, polar_fx, hold_fx)
    d = tmp_path / "on_int"
    with pytest.raises(RunInterrupted):
        run_persistent(pol, wx, start, pm_fx, sea, d, segments=12 * H, stop_after_segments=2,
                       manoeuvre=M)
    wx, sea, pol = make(sea_grid, polar_fx, hold_fx)
    res = run_persistent(pol, wx, start, pm_fx, sea, d, segments=12 * H, manoeuvre=M)
    np.testing.assert_array_equal(res.result.power_kw, on.result.power_kw)
    np.testing.assert_array_equal(res.result.manoeuvre_kind, kinds)
    # an ON run must not resume an OFF directory
    with pytest.raises(ValueError):
        run_persistent(pol, wx, start, pm_fx, sea, tmp_path / "off", segments=12 * H,
                       manoeuvre=M)


# ------------------------------------------------------------------------------ forecast knobs
def test_perfect_forecast_equals_truth(archive, grid):  # noqa: F811
    for params in (ForecastErrorParams.with_knobs(perfect=True),
                   ForecastErrorParams.with_knobs(error_scale=0.0)):
        wx = ERA5ForecastWeather(archive, grid, EPOCH, 20 * DAY, params=params, seed=3)
        ens = wx.forecast(2 * DAY + 3 * H, 3 * DAY, 4, dt_s=3 * H)
        tr = wx.truth(dt_s=3 * H, start_s=float(ens.times_s[0]), end_s=float(ens.times_s[-1]))
        assert ens.uv.shape[0] == 4
        for k in range(4):
            np.testing.assert_allclose(ens.uv[k], tr.uv, atol=1e-5)


def test_error_scale_default_is_identity_and_scales(archive, grid):  # noqa: F811
    base = ERA5ForecastWeather(archive, grid, EPOCH, 20 * DAY, seed=3)
    same = ERA5ForecastWeather(archive, grid, EPOCH, 20 * DAY, seed=3,
                               params=ForecastErrorParams.with_knobs(error_scale=1.0))
    a = base.forecast(2 * DAY, 3 * DAY, 2, dt_s=6 * H)
    b = same.forecast(2 * DAY, 3 * DAY, 2, dt_s=6 * H)
    np.testing.assert_array_equal(a.uv, b.uv)
    err = {}
    for s in (0.5, 1.0, 2.0):
        w = ERA5ForecastWeather(archive, grid, EPOCH, 20 * DAY, seed=3,
                                params=ForecastErrorParams.with_knobs(error_scale=s))
        e = w.forecast(2 * DAY, 3 * DAY, 1, dt_s=6 * H)
        tr = w.truth(dt_s=6 * H, start_s=float(e.times_s[0]), end_s=float(e.times_s[-1]))
        err[s] = float(np.sqrt(np.mean((e.uv[0] - tr.uv) ** 2)))
    assert err[0.5] < err[1.0] < err[2.0]


def test_knob_helper_and_latency(archive, grid):  # noqa: F811
    p = ForecastErrorParams.with_knobs(latency_h=0.0, consistency=False, spread_factor=0.6,
                                       season_amp=0.0)
    assert (p.latency_ens_h, p.issue_consistency, p.spread_factor, p.season_amp) == (
        0.0, False, 0.6, 0.0)
    w0 = ERA5ForecastWeather(archive, grid, EPOCH, 20 * DAY, params=p, seed=1)
    w12 = ERA5ForecastWeather(archive, grid, EPOCH, 20 * DAY, seed=1,
                              params=ForecastErrorParams.with_knobs(latency_h=12.0))
    t = 5 * DAY + 1 * H
    assert w0.analysis_time(t) == 5 * DAY
    assert w12.analysis_time(t) == 4 * DAY + 12 * H


# ---------------------------------------------------------------------------------- polar error
def test_truth_polar_options():
    pol = synthetic_polar()
    same = make_power_model(pol)
    sc = make_power_model(pol, scale=0.9)
    u, v = np.array([0.0] * 3), np.array([-10.0, -10.0, -14.0])  # wind from north
    ve, vn = np.array([4.0, 3.0, 5.0]), np.array([0.5, -2.0, -1.0])
    p0 = np.asarray(same.power_kw(u, v, ve, vn))
    p1 = np.asarray(sc.power_kw(u, v, ve, vn))
    pos = p0 > 50
    assert pos.any()
    np.testing.assert_allclose(p1[pos], 0.9 * p0[pos], rtol=0.03)
    # lobe shift: the TWA of the maximum of max_U P moves by the shift
    pp = perturb_polar(pol, 1.0, 10.0)
    k = pol.tws.size // 2
    best0 = np.nanmax(np.where(pol.feasible, pol.p, -np.inf), axis=2)[k]
    best1 = np.nanmax(np.where(pp.feasible, pp.p, -np.inf), axis=2)[k]
    shift = pol.twa[np.argmax(best1)] - pol.twa[np.argmax(best0)]
    assert shift == pytest.approx(10.0, abs=pol.twa[1] - pol.twa[0] + 1e-9) or \
        np.argmax(best0) <= 4
    assert np.nanmax(perturb_polar(pol, 1.1).p) >= np.nanmax(pol.p) - 1e-6


# ------------------------------------------------------------------------- simple routers / storm
def test_storm_penalty_polar_and_envelope():
    from horizon.sim.policies_simple import KN, storm_penalty_polar

    pol = synthetic_polar()
    hold = hold_power_curve(pol)
    pp, hp = storm_penalty_polar(pol, hold, 20.0)
    hi = pol.tws > 20.0 * KN
    assert hi.any()
    assert np.all(pp.p[hi][pol.feasible[hi]] < -5000.0)
    np.testing.assert_array_equal(pp.p[~hi], pol.p[~hi])
    assert np.all(hp.p_hold[hold.tws > 20.0 * KN] < -5000.0)
    build_envelope(pp)  # hull must not be degenerate


def test_mean_provider_blend():
    from horizon.sim.policies_simple import ForecastTransformPolicy
    from horizon.weather.fields import Ensemble

    g = Grid.from_bbox(-12, 4, 38, 54, 200e3)
    t = np.arange(5) * 6 * H
    uv = np.zeros((3, 5) + g.shape + (2,), np.float32)
    uv[1], uv[2] = 3.0, 6.0  # control 0, mean 3

    class Prov:
        now_s, mission_end_s = 0.0, 1e9

        def forecast(self, issue_s, horizon_s, n_members, dt_s=1.0, seed_offset=0):
            assert n_members == 3
            return Ensemble(g, EPOCH, 0.0, t, uv, np.ones(3) / 3)

    class Inner:
        def plan(self, t_s, x, y, provider):
            return provider.forecast(0.0, 1.0, 1)

    e = ForecastTransformPolicy(Inner(), 3).plan(0.0, 0.0, 0.0, Prov())
    assert e.uv.shape[0] == 1 and np.allclose(e.uv, 3.0)
    e = ForecastTransformPolicy(Inner(), 3, blend_h=12.0).plan(0.0, 0.0, 0.0, Prov())
    assert np.allclose(e.uv[0, :3], 0.0) and np.allclose(e.uv[0, 3:], 3.0)  # control <= 12 h
