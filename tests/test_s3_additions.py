"""Tests of the Sprint-3 additions: FeasiblePowerModel, climatological terminal value in B1,
precomputed-mean B0 selection."""

import numpy as np
import pytest

from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.sim import DeterministicMPCPolicy, FeasiblePowerModel, best_climatological_point
from horizon.sim.simulator import ForecastProvider
from horizon.weather.fields import Ensemble


class _Base:
    """Finite power only below 4 m/s ground speed."""

    def power_kw(self, u, v, ve, vn):
        sp = np.hypot(ve, vn)
        return np.where(sp <= 4.0, 100.0 - sp, np.nan)


def test_feasible_power_model_shrinks_speed():
    fm = FeasiblePowerModel(_Base(), shrink=0.9)
    p = fm.power_kw(5.0, 0.0, [0.0, 0.0], [2.0, 6.0])
    assert p[0] == pytest.approx(98.0)  # untouched
    assert 96.0 < p[1] < 97.0  # shrunk to <= 4 m/s
    assert fm.n_clamped == 1
    assert np.isfinite(FeasiblePowerModel(_Base(), max_iter=1).power_kw(0, 0, 0, 100.0))


class _Wx:
    def __init__(self, grid):
        self.grid = grid

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        t = issue_s + np.arange(int(round(horizon_s / dt_s)) + 1) * dt_s
        uv = np.zeros((n_members, t.size) + self.grid.shape + (2,), np.float32)
        return Ensemble(self.grid, np.datetime64("2015-01-01T00:00:00", "s"), float(issue_s), t, uv,
                        np.full(n_members, 1.0 / n_members))


def test_b1_terminal_pulls_towards_windy_cells():
    grid = Grid.from_bbox(-12, 4, 38, 54, 80e3)
    sea = CoastModel(grid, np.full(grid.shape, 1e6, np.float32))
    pol = synthetic_polar()
    hold = hold_power_curve(pol)
    clim = np.zeros(grid.shape, np.float32)
    j0, i0 = grid.index_of(*grid.to_xy(-4.0, 46.0))
    clim[int(j0) + 2, int(i0) + 2] = 1000.0
    prov = ForecastProvider(_Wx(grid), 0.0, 30 * 86400.0)
    x, y = grid.to_xy(-4.0, 46.0)
    p0 = DeterministicMPCPolicy(pol, hold, sea, horizon_days=1.0)
    p1 = DeterministicMPCPolicy(pol, hold, sea, horizon_days=1.0, terminal_clim_kw=clim)
    a, b = p0.plan(0.0, x, y, prov), p1.plan(0.0, x, y, prov)
    tx, ty = grid.x0 + grid.dx * (i0 + 2), grid.y0 + grid.dx * (j0 + 2)
    d0 = np.hypot(a.x[-1] - tx, a.y[-1] - ty)
    d1 = np.hypot(b.x[-1] - tx, b.y[-1] - ty)
    assert d1 < d0
    assert b.value_kwh > a.value_kwh  # terminal value adds to the plan value


def test_best_point_from_precomputed_mean():
    grid = Grid.from_bbox(-12, 4, 38, 54, 40e3)
    sea = CoastModel(grid, np.full(grid.shape, 1e6, np.float32))
    mean = np.zeros(grid.shape)
    mean[20, 30] = 5.0
    mean[21, 31] = 9.0
    mask = np.ones(grid.shape, bool)
    mask[21, 31] = False
    x, y, m = best_climatological_point([], None, sea, grid.to_xy(-4.0, 46.0), mean_kw=mean,
                                        extra_mask=mask)
    assert grid.index_of(x, y) == (20, 30) and m == 5.0
