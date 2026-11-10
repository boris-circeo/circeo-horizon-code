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
    forecast_skill,
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
def sea(archive, grid):
    try:
        coast = build_basin_coast(40e3, bbox=ERA5_BOX)
    except FileNotFoundError:
        pytest.skip("Natural Earth land data not available")
    return (coast.sdf > 0) & ~archive.outside


def test_forecast_shapes_and_api(wx, grid):
    ens = wx.forecast(5 * DAY, 3 * DAY, 4, dt_s=10800.0)
    assert isinstance(ens, Ensemble) and ens.n_members == 4
    assert ens.uv.shape == (4, 25, grid.ny, grid.nx, 2) and ens.uv.dtype == np.float32
    assert ens.times_s[0] == 5 * DAY and np.isfinite(ens.uv).all()
    assert ens.epoch == EPOCH and ens.weights.sum() == pytest.approx(1.0)
    tr = wx.truth(dt_s=3 * 3600.0)
    assert isinstance(tr, WindField) and tr.uv.shape[0] == 360 * 8 + 1
    with pytest.raises(ValueError):
        wx.forecast(-1.0, DAY, 2)


def test_lead_zero_error_small(wx, sea):
    ens = wx.forecast(40 * DAY, DAY, 3, dt_s=3600.0)
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
    e = wx.forecast(10 * DAY + 3 * 3600.0, 2 * DAY, 3)
    assert not np.array_equal(e.uv[0, 0], a.uv[0, 1])  # other issue time: other draw


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


def _check_skill(r, tol_ctrl, strict):
    for d, tgt in TARGET_CONTROL_RMSE.items():
        assert abs(r["control_rmse"][d] - tgt) < tol_ctrl * max(tgt, 2.0), (d, r["control_rmse"][d])
    assert (np.diff(r["control_rmse"][:8]) > -0.5).all()  # roughly increasing
    for d in range(3, 11):
        assert r["mean_rmse"][d] < 0.92 * r["control_rmse"][d], d
    ratio = r["spread"] / r["mean_rmse"]
    assert ((ratio > 0.8) & (ratio < 1.2)).all(), ratio
    if strict:
        assert r["control_rmse"][0] < 1.6 and r["control_rmse"][10] < 9.0


def test_calibration_quick(wx, sea):
    """Few issue times: loose bounds (the statistic is noisy because weather regimes differ)."""
    iss = np.linspace(5, 340, 6) * DAY
    r = forecast_skill(wx, iss, 6, 10, sea)
    _check_skill(r, 0.4, strict=True)


@pytest.mark.slow
def test_calibration_and_exchangeability(archive, grid, sea):
    w = ERA5ForecastWeather(archive, grid, EPOCH, 360 * DAY, seed=9)
    iss = np.linspace(5, 350, 36) * DAY + 43200.0
    r = forecast_skill(w, iss, 10, 10, sea)
    _check_skill(r, 0.2, strict=True)
    for c in ("ranks_u", "ranks_v"):
        h = rank_histogram(r[c][[3, 5, 7]], 10) * 11.0  # 1 = flat
        assert (np.abs(h - 1.0) < 0.15).all(), h
