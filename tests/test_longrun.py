"""S4 persistent runs: segmenting, checkpoint/resume identity, horizon truncation, month metrics."""

import numpy as np
import pytest

from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    run_mission,
)
from horizon.sim.longrun import RunInterrupted, run_persistent, segment_boundaries
from horizon.weather.fields import Ensemble, WindField

EPOCH = np.datetime64("2026-01-30T00:00:00", "s")  # crosses the Jan/Feb month boundary
H = 3600.0
DAY = 86400.0


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


class TimeVaryingWeather:
    """Deterministic spatio-temporal wind, perfect forecast, streamed truth (no big array)."""

    def __init__(self, grid, duration_s):
        self.grid, self.epoch, self.duration_s = grid, EPOCH, duration_s
        self.max_valid_s = 0.0
        self.X, self.Y = grid.xy_mesh()

    def _field(self, t):
        s = 9 + 5 * np.sin(self.X / 6e5 + t / 8e4) * np.cos(self.Y / 5e5)
        d = np.radians(250 + 80 * np.sin(self.Y / 7e5 - t / 1e5))
        return np.stack([-s * np.sin(d), -s * np.cos(d)], axis=-1).astype(np.float32)

    def _wf(self, t):
        t = np.asarray(t, float)
        return WindField(self.grid, EPOCH, t, np.stack([self._field(x) for x in t]))

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        t = issue_s + dt_s * np.arange(int(round(horizon_s / dt_s)) + 1)
        self.max_valid_s = max(self.max_valid_s, float(t[-1]))
        return Ensemble(self.grid, EPOCH, issue_s, t, self._wf(t).uv[None], np.ones(1))

    def truth(self, dt_s=3600.0, start_s=0.0, end_s=None):
        end_s = self.duration_s if end_s is None else end_s
        return self._wf(np.arange(start_s, end_s + 0.5 * dt_s, dt_s))


def test_segment_boundaries_months():
    b = segment_boundaries(np.datetime64("2015-01-01T00:00:00", "s"), 8759 * 4, 900.0)
    assert len(b) == 13 and b[0] == 0 and b[-1] == 8759 * 4
    assert b[1] == 31 * 96 and b[2] == (31 + 28) * 96  # 2015 is not a leap year
    assert segment_boundaries(EPOCH, 10 * 96, 900.0, 4 * DAY) == [0, 384, 768, 960]


def make(grid, polar, hold, days=3.0):
    wx = TimeVaryingWeather(grid, days * DAY)
    sea = CoastModel(grid, np.full(grid.shape, 1e6, np.float32))
    pol = DeterministicMPCPolicy(polar, hold, sea, horizon_days=1.0)
    return wx, sea, pol


def test_persistent_equals_run_mission_and_months(grid, polar, hold, pm, tmp_path):
    wx, sea, pol = make(grid, polar, hold)
    start = (-4.0, 46.0)
    r = run_persistent(pol, wx, start, pm, sea, tmp_path / "a", segments="month", tag="t",
                       p_rated_kw=3000.0)
    assert [m.label for m in r.segments] == ["2026-01", "2026-02"]  # month boundary at 2 d
    assert r.segments[0].hours == 48.0 and r.segments[1].hours == 24.0
    wx2, sea2, pol2 = make(grid, polar, hold)
    ref = run_mission(pol2, wx2, wx2.truth(), start, 3 * DAY, pm, sea2)
    np.testing.assert_allclose(r.result.x, ref.x, atol=1e-6)
    np.testing.assert_allclose(r.result.power_kw, ref.power_kw, rtol=1e-6, atol=1e-6)
    assert r.energy_kwh == pytest.approx(ref.energy_kwh[-1], rel=1e-9)
    assert sum(m.energy_kwh for m in r.segments) == pytest.approx(r.energy_kwh, rel=1e-9)
    assert r.segments[0].capacity_factor == pytest.approx(
        r.segments[0].energy_kwh / (3000.0 * 48.0))
    assert all(m.guard_interventions == 0 for m in r.segments)
    # horizons were truncated at the end of the run: no valid time beyond it
    assert wx.max_valid_s <= 3 * DAY + 1e-6


def test_kill_and_resume_is_identical(grid, polar, hold, pm, tmp_path):
    start = (-4.0, 46.0)
    wx, sea, pol = make(grid, polar, hold)
    full = run_persistent(pol, wx, start, pm, sea, tmp_path / "full", segments=12 * H)
    wx, sea, pol = make(grid, polar, hold)
    d = tmp_path / "interrupted"
    with pytest.raises(RunInterrupted):
        run_persistent(pol, wx, start, pm, sea, d, segments=12 * H, stop_after_segments=3)
    assert len(list(d.glob("seg_*.json"))) == 3
    # simulate a crash in the middle of the 4th segment: npz without json must be ignored
    (d / "seg_0003.npz").write_bytes(b"garbage")
    wx, sea, pol = make(grid, polar, hold)  # fresh policy / weather objects, as after a restart
    res = run_persistent(pol, wx, start, pm, sea, d, segments=12 * H)
    assert res.resumed_from == 3
    np.testing.assert_array_equal(res.result.x, full.result.x)
    np.testing.assert_array_equal(res.result.y, full.result.y)
    np.testing.assert_array_equal(res.result.power_kw, full.result.power_kw)
    np.testing.assert_array_equal(res.result.replan_times_s, full.result.replan_times_s)
    assert [m.energy_kwh for m in res.segments] == [m.energy_kwh for m in full.segments]
    # a different configuration must not silently resume
    with pytest.raises(ValueError):
        run_persistent(pol, wx, (-5.0, 46.0), pm, sea, d, segments=12 * H)


def test_forecast_horizon_truncated_at_mission_end(grid):
    from horizon.sim import ForecastProvider

    wx = TimeVaryingWeather(grid, 3 * DAY)
    prov = ForecastProvider(wx, now_s=0.0, mission_end_s=10 * H)
    ens = prov.forecast(0.0, 24 * H, 1, dt_s=3 * H)
    assert ens.times_s[-1] == 9 * H  # last multiple of dt inside the data, nothing beyond
    ens0 = ForecastProvider(wx, 0.0, 0.0).forecast(0.0, 24 * H, 1, dt_s=3 * H)
    assert ens0.times_s.size == 1


def test_oracle_ref_h_runs_streaming_and_is_coast_safe(grid, polar, hold, pm, tmp_path):
    from horizon.sim.policies_refine import OracleHorizonRefinedPolicy

    wx = TimeVaryingWeather(grid, 2 * DAY)
    sea = CoastModel(grid, np.full(grid.shape, 1e6, np.float32))
    pol = OracleHorizonRefinedPolicy(wx, polar, hold, sea, horizon_days=1.0)
    r = run_persistent(pol, wx, (-4.0, 46.0), pm, sea, tmp_path / "o", segments=DAY, tag="oh")
    assert r.result.guard_interventions == 0 and r.result.coast_violations == 0
    assert wx.max_valid_s <= 2 * DAY + 1e-6
    wx2 = TimeVaryingWeather(grid, 2 * DAY)
    base = DeterministicMPCPolicy(polar, hold, sea, horizon_days=1.0)
    ref = run_mission(base, wx2, wx2.truth(), (-4.0, 46.0), 2 * DAY, pm, sea)
    assert r.energy_kwh >= 0.98 * ref.energy_kwh[-1]  # refined hindsight is not worse than DP
