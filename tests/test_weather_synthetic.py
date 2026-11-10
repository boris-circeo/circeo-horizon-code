"""Tests for horizon.weather.synthetic (synthetic truth + causal ensemble forecasts)."""

import numpy as np
import pytest

from horizon.geo.grid import Grid
from horizon.weather.fields import Ensemble, WindField
from horizon.weather.synthetic import SyntheticParams, SyntheticWeather, skill_vs_truth

EPOCH = np.datetime64("2024-01-01T00:00:00")
DAY = 86400.0


@pytest.fixture(scope="module")
def grid():
    return Grid.from_bbox(-45.0, 5.0, 35.0, 65.0, 80_000.0)


@pytest.fixture(scope="module")
def wx(grid):
    return SyntheticWeather(grid, EPOCH, 30 * DAY, seed=3)


@pytest.fixture(scope="module")
def truth(wx):
    return wx.truth(start_s=0.0, end_s=40 * DAY)


def test_truth_shapes_and_ranges(wx, grid):
    f = wx.truth(dt_s=3 * 3600.0)
    assert isinstance(f, WindField)
    assert f.uv.dtype == np.float32 and f.uv.flags.c_contiguous
    assert f.uv.shape == (241, grid.ny, grid.nx, 2)
    assert np.isfinite(f.uv).all()
    spd = np.hypot(f.uv[..., 0], f.uv[..., 1])
    assert 7.0 < spd.mean() < 12.0
    assert 20.0 < np.percentile(spd, 99) < 30.0
    assert spd.max() < 45.0


def test_westerly_mean_flow(wx):
    f = wx.truth(dt_s=6 * 3600.0)
    lat = wx.grid.lonlat_mesh()[1]
    band = (lat > 45) & (lat < 55)
    assert 5.0 < f.uv[:, band, 0].mean() < 14.0
    assert f.uv[:, lat < 38, 0].mean() < f.uv[:, band, 0].mean() - 3.0


def test_cyclones_rotate_counterclockwise_in_true_frame(grid):
    """Circulation of the wind around a storm centre, evaluated with true east/north vectors."""
    p = SyntheticParams(jet_u_ms=0.0, trade_u_ms=0.0, noise_sigma_ms=0.0)
    w = SyntheticWeather(grid, EPOCH, 20 * DAY, params=p, seed=5)
    n_checked = 0
    for s in w.storms:
        t = s.t0_s + 0.45 * s.life_s
        if not 0 <= t <= 20 * DAY:
            continue
        cx, cy = w.storm_centres(t)[np.argmin(
            [abs(t - q.t0_s - 0.45 * q.life_s) for q in w.storms if 0 < t - q.t0_s < q.life_s])]
        lon_c, lat_c = grid.to_lonlat(cx, cy)
        if not (-35 < lon_c < -5 and 40 < lat_c < 58):
            continue
        f = w.truth(start_s=t, end_s=t, dt_s=3600.0)
        ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        circ = []
        for a in ang:
            x, y = cx + 350e3 * np.cos(a), cy + 350e3 * np.sin(a)
            lon, lat = grid.to_lonlat(x, y)
            d_e = np.radians(lon - lon_c) * np.cos(np.radians(lat_c))
            d_n = np.radians(lat - lat_c)
            tx, ty = -d_n, d_e  # CCW tangent in true east/north
            j, i = grid.index_of(x, y)
            u, v = f.uv[0, j, i]
            circ.append((u * tx + v * ty) / np.hypot(tx, ty))
        assert np.mean(circ) > 3.0
        n_checked += 1
    assert n_checked >= 2


def test_storms_move_east(wx, grid):
    dlon, speed = [], []
    for s in wx.storms:
        n = int(s.life_s // 10800)
        lon0 = grid.to_lonlat(*s.xy[0])[0]
        lon1 = grid.to_lonlat(*s.xy[n])[0]
        dlon.append(lon1 - lon0)
        speed.append(np.hypot(*s.vel[:n].T).mean())
    assert np.mean(dlon) > 10.0 and np.min(dlon) > -5.0
    assert 9.0 < np.mean(speed) < 19.0
    life = [s.life_s for s in wx.storms]
    assert 3.0 * DAY <= min(life) and max(life) <= 6 * DAY


def test_forecast_structure_and_reproducibility(wx, grid):
    e1 = wx.forecast(5 * DAY, 2 * DAY, 4, seed_offset=1)
    e2 = wx.forecast(5 * DAY, 2 * DAY, 4, seed_offset=1)
    e3 = wx.forecast(5 * DAY, 2 * DAY, 4, seed_offset=2)
    assert isinstance(e1, Ensemble)
    assert e1.uv.shape == (4, 17, grid.ny, grid.nx, 2) and e1.uv.dtype == np.float32
    assert e1.times_s[0] == 5 * DAY and np.allclose(np.diff(e1.times_s), 10800.0)
    assert np.allclose(e1.weights, 0.25)
    np.testing.assert_array_equal(e1.uv, e2.uv)
    np.testing.assert_array_equal(e1.uv[0], e3.uv[0])  # same control
    assert not np.array_equal(e1.uv[1], e3.uv[1])


def test_seed_dependence(grid):
    a = SyntheticWeather(grid, EPOCH, 5 * DAY, seed=1).truth().uv
    b = SyntheticWeather(grid, EPOCH, 5 * DAY, seed=1).truth().uv
    c = SyntheticWeather(grid, EPOCH, 5 * DAY, seed=2).truth().uv
    np.testing.assert_array_equal(a, b)
    assert np.abs(a - c).mean() > 0.5


def test_causality_future_storms_do_not_leak(grid):
    """Control at issue time must not depend on storms born after issue + foresight."""
    w = SyntheticWeather(grid, EPOCH, 20 * DAY, seed=8)
    issue = 6 * DAY
    p = w.params
    ctrl = w.forecast(issue, 3 * DAY, 1).uv[0]
    late = [s for s in w.storms if s.t0_s > issue + p.genesis_foresight_days * DAY]
    assert late
    w.storms[:] = [s for s in w.storms if s not in late]  # remove all late storms
    ctrl2 = w.forecast(issue, 3 * DAY, 1).uv[0]
    np.testing.assert_array_equal(ctrl, ctrl2)


@pytest.mark.slow
def test_forecast_skill_and_spread(grid):
    rows = []
    for seed in range(2):
        w = SyntheticWeather(grid, EPOCH, 30 * DAY, seed=seed)
        tr = w.truth(start_s=0.0, end_s=40 * DAY)
        for iss in (3, 8, 13, 18):
            k = skill_vs_truth(w.forecast(iss * DAY, 12 * DAY, 8), tr)
            rows.append([k["rmse_control"], k["rmse_mean"], k["spread"]])
    r = np.sqrt(np.mean(np.square(rows), axis=0))  # (3, T) at 3 h
    def at(d):
        return int(d * 8)

    ctrl, mean, spread = r
    assert ctrl[0] < 2.0 and mean[0] < 2.0
    assert ctrl[at(1)] < ctrl[at(3)] < ctrl[at(5)] + 0.3
    assert ctrl[at(5)] > ctrl[at(0)] + 1.5
    assert spread[at(1)] < spread[at(3)] < spread[at(6)] + 0.3 and spread[0] < spread[at(5)]
    for d in (3, 4, 5, 6, 7):
        assert 0.6 < spread[at(d)] / mean[at(d)] < 1.5
