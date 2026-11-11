"""Tests of horizon.weather.forecast_model (ERA5 truth + exchangeable error-model ensemble)."""

from pathlib import Path

import numpy as np
import pytest

from horizon.geo.coast import CoastModel, build_basin_coast
from horizon.geo.grid import Grid
from horizon.sim import CausalityError, ForecastProvider, HoldAtPointPolicy, run_mission
from horizon.weather.era5 import ERA5_BOX, ERA5Archive
from horizon.weather.fields import Ensemble, WindField
from horizon.weather.forecast_model import (
    TARGET_CONTROL_RMSE,
    ERA5ForecastWeather,
    ForecastErrorParams,
    forecast_skill,
    issue_correlation,
    rank_histogram,
)

GRIB_DIR = Path("/home/claude/circeo-horizon-data/era5-data")
EPOCH = np.datetime64("2015-01-01T00:00:00")
DAY = 86400.0


@pytest.fixture(scope="module")
def grid():
    return Grid.from_bbox(*ERA5_BOX, 40e3)


@pytest.fixture(scope="module")
def archive(grid):
    a = ERA5Archive(GRIB_DIR, grid)
    try:
        a.build_cache()
    except (FileNotFoundError, ImportError):
        pytest.skip("client ERA5 files / cfgrib not available")
    return a


@pytest.fixture(scope="module")
def wx(archive, grid):
    return ERA5ForecastWeather(archive, grid, EPOCH, 360 * DAY, seed=4)


@pytest.fixture(scope="module")
def wx_legacy(archive, grid):
    return ERA5ForecastWeather(archive, grid, EPOCH, 360 * DAY, seed=4,
                               params=ForecastErrorParams.legacy())


@pytest.fixture(scope="module")
def sea(archive, grid):
    try:
        coast = build_basin_coast(40e3, bbox=ERA5_BOX)
    except FileNotFoundError:
        pytest.skip("Natural Earth land data not available")
    return (coast.sdf > 0) & ~archive.outside


def test_forecast_shapes_and_api(wx, grid):
    ens = wx.forecast(5 * DAY, 3 * DAY, 4, dt_s=10800.0)
    assert isinstance(ens, Ensemble) and ens.n_members == 4
    assert ens.uv.shape == (4, 27, grid.ny, grid.nx, 2) and ens.uv.dtype == np.float32
    assert ens.times_s[0] == 5 * DAY - 6 * 3600.0 and ens.times_s[-1] >= 8 * DAY
    assert np.isfinite(ens.uv).all()
    assert ens.epoch == EPOCH and ens.weights.sum() == pytest.approx(1.0)
    tr = wx.truth(dt_s=3 * 3600.0)
    assert isinstance(tr, WindField) and tr.uv.shape[0] == 360 * 8 + 1
    with pytest.raises(ValueError):
        wx.forecast(-1.0, DAY, 2)


def test_lead_zero_error_small(wx, sea):
    ens = wx.forecast_cycle(40 * DAY, DAY, 3, dt_s=3600.0)
    tr = wx.truth(dt_s=3600.0, start_s=40 * DAY, end_s=41 * DAY)
    e = np.sqrt(((ens.uv[0, 0] - tr.uv[0]) ** 2).sum(-1)[sea].mean())
    assert 0.3 < e < 2.0


def test_reproducibility_and_seed_offset(wx):
    a = wx.forecast(10 * DAY, 2 * DAY, 3, seed_offset=0)
    b = wx.forecast(10 * DAY, 2 * DAY, 3, seed_offset=0)
    c = wx.forecast(10 * DAY, 2 * DAY, 3, seed_offset=1)
    d = wx.forecast(10 * DAY, 2 * DAY, 5, seed_offset=0)
    assert np.array_equal(a.uv, b.uv)
    assert np.array_equal(a.uv[0], c.uv[0])          # control independent of seed_offset
    assert not np.array_equal(a.uv[1], c.uv[1])      # other members change
    assert np.array_equal(a.uv[:3], d.uv[:3])        # member k independent of n_members
    e = wx.forecast(10 * DAY + 6 * 3600.0, 2 * DAY, 3)
    assert not np.array_equal(e.uv[0, 0], a.uv[0, 1])  # other cycle: other draw


def test_wrap_beyond_data(archive, grid):
    w = ERA5ForecastWeather(archive, grid, np.datetime64("2015-12-28T00:00:00"), 3 * DAY, seed=1)
    ens = w.forecast(2.5 * DAY, 6 * DAY, 2, dt_s=21600.0)  # runs past 31 Dec 23 UTC
    assert np.isfinite(ens.uv).all() and w.n_wrapped_requests >= 1


def test_sim_provider_smoke(archive, grid):
    """Drop-in for the simulator: a trivial policy that queries the causal provider."""
    class Pm:
        def power_kw(self, u, v, ve, vn):
            return 0.1 * np.hypot(u, v) + 0.0 * ve

    class Pol:
        def __init__(self, x, y):
            self.inner = HoldAtPointPolicy(x, y)
            self.n = 0

        def plan(self, t_s, x, y, provider):
            ens = provider.forecast(t_s, 12 * 3600.0, 3)
            self.n += ens.n_members
            return self.inner.plan(t_s, x, y, provider)

    w = ERA5ForecastWeather(archive, grid, np.datetime64("2015-03-01T00:00:00"), DAY, seed=2)
    start = (-15.0, 48.0)
    pol = Pol(*grid.to_xy(-14.0, 48.0))
    coast = CoastModel(grid, np.full(grid.shape, 1e6, np.float32))
    res = run_mission(pol, w, w.truth(), start, DAY, Pm(), coast)
    assert pol.n >= 3 and np.isfinite(res.energy_kwh).all()
    prov = ForecastProvider(w, now_s=0.0)
    with pytest.raises(CausalityError):
        prov.forecast(3600.0, 3600.0, 1)


def _check_skill(r, tol_ctrl, strict, ratio_lo=0.8):
    for d, tgt in TARGET_CONTROL_RMSE.items():
        assert abs(r["control_rmse"][d] - tgt) < tol_ctrl * max(tgt, 2.0), (d, r["control_rmse"][d])
    assert (np.diff(r["control_rmse"][:8]) > -0.5).all()  # roughly increasing
    for d in range(3, 11):
        assert r["mean_rmse"][d] < 0.92 * r["control_rmse"][d], d
    ratio = r["spread"] / r["mean_rmse"]
    assert ((ratio > ratio_lo) & (ratio < 1.2)).all(), ratio
    if strict:
        assert r["control_rmse"][0] < 1.6 and r["control_rmse"][10] < 9.0


def test_calibration_quick(wx, sea):
    """Few issue times: loose bounds (the statistic is noisy because weather regimes differ)."""
    iss = np.linspace(5, 340, 6) * DAY
    r = forecast_skill(wx, iss, 6, 10, sea)
    _check_skill(r, 0.4, strict=True, ratio_lo=0.7)


@pytest.mark.slow
def test_calibration_and_exchangeability(archive, grid, sea):
    w = ERA5ForecastWeather(archive, grid, EPOCH, 360 * DAY, seed=9)
    iss = np.linspace(5, 350, 36) * DAY + 43200.0
    r = forecast_skill(w, iss, 10, 10, sea)
    _check_skill(r, 0.2, strict=True)
    for c in ("ranks_u", "ranks_v"):
        h = rank_histogram(r[c][[3, 5, 7]], 10) * 11.0  # 1 = flat
        assert (np.abs(h - 1.0) < 0.15).all(), h


# ------------------------------------------------------------------------------ Sprint 4
def test_legacy_mode_bit_for_bit(wx_legacy):
    """Sprint-3 outputs reproduced exactly (reference values from the S3 code)."""
    e = wx_legacy.forecast(10 * DAY, 2 * DAY, 3)
    assert e.times_s[0] == 10 * DAY
    assert float(e.uv[1, 3, 10, 10, 0]) == 0.1586010456085205
    assert float(e.uv[2, 12, 40, 40, 1]) == 9.10037899017334
    assert float(e.uv.astype(np.float64).sum()) == pytest.approx(3154905.3345427886, rel=1e-12)


def test_determinism_and_member_independence(wx):
    a = wx.forecast_cycle(12 * DAY, 3 * DAY, 4, seed_offset=2)
    b = wx.forecast_cycle(12 * DAY, 3 * DAY, 4, seed_offset=2)
    c = wx.forecast_cycle(12 * DAY, 3 * DAY, 6, seed_offset=2)
    d = wx.forecast_cycle(12 * DAY, 3 * DAY, 4, seed_offset=0)
    assert np.array_equal(a.uv, b.uv) and np.array_equal(a.uv[:4], c.uv[:4])
    assert np.array_equal(a.uv[0], d.uv[0]) and not np.array_equal(a.uv[1], d.uv[1])
    # prefix consistency: the same valid times from a longer request are identical
    e = wx.forecast_cycle(12 * DAY, 6 * DAY, 2, seed_offset=2)
    assert np.array_equal(e.uv[:2, :a.times_s.size], a.uv[:2, :])


def test_latency_semantics(wx, wx_legacy):
    h = 3600.0
    # epoch is 00 UTC: now = 12 UTC day 10 -> latest ENS cycle <= 06 UTC; control (4 h) -> 06 UTC
    now = 10 * DAY + 12 * h
    assert wx.analysis_time(now) == 10 * DAY + 6 * h
    assert wx.analysis_time(10 * DAY + 11.99 * h) == 10 * DAY        # 06 + 6 h not yet reached
    assert wx.analysis_time(10 * DAY + 10 * h, "control") == 10 * DAY + 6 * h
    assert wx.analysis_time(10 * DAY + 9.9 * h, "control") == 10 * DAY
    assert wx.analysis_time(3 * h) == 0.0                              # clamp at mission start
    ens = wx.forecast(now, DAY, 2)
    assert ens.issue_s == 10 * DAY + 6 * h and ens.times_s[0] == ens.issue_s
    assert ens.times_s[-1] >= now + DAY and ens.issue_s <= now - 6 * h
    ctl = wx.forecast(now, DAY, 5, product="control")
    assert ctl.n_members == 1 and np.array_equal(ctl.uv[0], wx.forecast_cycle(
        ctl.issue_s, DAY + now - ctl.issue_s, 1).uv[0])
    # same cycle for all `now` inside a 6 h window
    e2 = wx.forecast(now + 5 * h, DAY, 2)
    assert e2.issue_s == ens.issue_s
    # legacy: analysis = now
    assert wx_legacy.analysis_time(now) == now
    assert wx_legacy.forecast(now, DAY, 1).issue_s == now


def test_seasonality_factor(wx):
    f = wx._season(np.array([15 * DAY, 197 * DAY]))
    assert f[0] == pytest.approx(1.15, abs=1e-3) and f[1] == pytest.approx(0.85, abs=1e-2)
    ym = wx._season(np.arange(0, 365) * DAY).mean()
    assert ym == pytest.approx(1.0, abs=0.01)


def test_issue_correlation_analytic():
    P = ForecastErrorParams()
    v = 20 * DAY
    r6 = [issue_correlation(P, v - L * DAY - 6 * 3600.0, v - L * DAY, v) for L in (0.5, 1, 3, 7)]
    assert r6[0] > 0.6 and all(np.diff(r6) > 0) and r6[-1] > 0.93
    far = issue_correlation(P, v - 8 * DAY, v - 3 * DAY, v)
    assert far < r6[2] and issue_correlation(P, v - DAY, v - DAY, v) == 1.0
    assert issue_correlation(ForecastErrorParams.legacy(), v - DAY, v - DAY - 3600, v) == 0.0


def _ctrl_err(w, a, lead_s, sea):
    ens = w.forecast_cycle(a, lead_s, 1, dt_s=6 * 3600.0)
    tr = w._truth_at(ens.times_s[-1:])[0]
    return (ens.uv[0, -1] - tr)[sea]


def test_issue_to_issue_consistency(wx, wx_legacy, sea):
    """Errors of consecutive issues for the same valid time are strongly correlated (new) vs
    uncorrelated (legacy); the 6 h-later forecast is slightly better."""
    L = 3 * DAY
    stats = {}
    for name, w in (("new", wx), ("old", wx_legacy)):
        c, e1s, e2s = [], 0.0, 0.0
        for a in np.linspace(20, 300, 5) * DAY:
            e1 = _ctrl_err(w, a, L + 6 * 3600.0, sea)
            e2 = _ctrl_err(w, a + 6 * 3600.0, L, sea)
            c.append((e1 * e2).sum() / np.sqrt((e1**2).sum() * (e2**2).sum()))
            e1s += (e1**2).mean()
            e2s += (e2**2).mean()
        stats[name] = (np.mean(c), e2s / e1s)
    assert stats["new"][0] > 0.75 and abs(stats["old"][0]) < 0.2
    assert stats["new"][1] < 1.0          # newer issue (shorter lead) has lower error


def test_no_convergence_by_averaging(wx, wx_legacy, sea):
    """Averaging N past ensemble means must not converge to the truth (error floor)."""
    res = {}
    for name, w in (("new", wx), ("old", wx_legacy)):
        mse = {1: 0.0, 8: 0.0}
        for a0 in np.linspace(30, 300, 4) * DAY:
            v = a0 + 3 * DAY
            fs = [w.forecast_cycle(a0 - 6 * 3600.0 * k, v - (a0 - 6 * 3600.0 * k), 6,
                                   dt_s=6 * 3600.0).uv.mean(0)[-1][sea] for k in range(8)]
            tr = w._truth_at(np.array([v]))[0][sea]
            for n in mse:
                mse[n] += ((np.mean(fs[:n], 0) - tr) ** 2).sum(-1).mean()
        res[name] = np.sqrt(mse[8] / mse[1])
    assert res["new"] > 0.85          # floor: almost no gain from averaging 8 issues
    assert res["old"] < 0.8           # independent errors: averaging helps (the structural leak)


def test_seasonal_skill_winter_vs_summer(wx, sea):
    def rmse(days):
        r = forecast_skill(wx, np.asarray(days) * DAY, 3, 6, sea)
        return r["control_rmse"][5]
    assert rmse([2, 8, 14, 20, 340, 350]) > rmse([170, 180, 190, 200, 210, 220])


def test_spread_factor_underdispersion(archive, grid, sea):
    P = ForecastErrorParams(spread_factor=0.6)
    w = ERA5ForecastWeather(archive, grid, EPOCH, 360 * DAY, params=P, seed=5)
    r = forecast_skill(w, np.linspace(10, 300, 5) * DAY, 8, 5, sea)
    ratio = r["spread"][3:] / r["mean_rmse"][3:]
    assert (ratio < 0.8).all() and (ratio > 0.4).all(), ratio


def test_lazy_members_and_memory(wx):
    t, gen = wx.forecast_members(50 * DAY, 3 * DAY, 50)
    first = next(gen)
    assert first.dtype == np.float32 and first.shape == (t.size,) + wx.grid.shape + (2,)
    full = wx.forecast_cycle(50 * DAY, 3 * DAY, 2)
    assert np.array_equal(first, full.uv[0])
    nb = wx.ensemble_nbytes(50, 15 * DAY)
    assert nb == 50 * 121 * wx.grid.ny * wx.grid.nx * 8 and nb < 400e6


# ---------------------------------------------------------------- S5 external review
@pytest.mark.parametrize("now_h", [4, 10, 16])
def test_forecast_covers_requested_horizon_off_cycle(wx, now_h):
    """Bug: when ``now - analysis`` is not a multiple of dt the valid times ended up to dt/2
    short of ``now + horizon`` (round instead of ceil), so the DP tail read persistence."""
    now, h = now_h * 3600.0, 48 * 3600.0
    e = wx.forecast(now, h, 1, dt_s=10800.0)
    assert e.times_s[-1] >= now + h - 1e-6


def test_fast_filter_matches_fft(archive, grid):
    """The dense circulant filter equals the FFT filter to float32 round-off."""
    from horizon.weather.forecast_model import _SmoothNoise
    f = _SmoothNoise(grid, 800.0)
    z = np.random.default_rng(1).standard_normal((5, 2) + grid.shape).astype(np.float32)
    assert np.abs(f.filter(z) - f.filter_dense(z)).max() < 1e-5


def test_white_series_cache_is_exact(archive, grid):
    a = ERA5ForecastWeather(archive, grid, EPOCH, 30 * DAY, seed=3)
    b = ERA5ForecastWeather(archive, grid, EPOCH, 30 * DAY, seed=3)
    b._series_cache_bytes = 0  # cache off
    x1 = a.forecast(30 * 3600.0, 3 * DAY, 2)
    a.forecast(36 * 3600.0, 5 * DAY, 2)  # warms / lengthens the cache
    x2 = a.forecast(30 * 3600.0, 3 * DAY, 2)
    x3 = b.forecast(30 * 3600.0, 3 * DAY, 2)
    assert np.array_equal(x1.uv, x2.uv) and np.array_equal(x1.uv, x3.uv)
