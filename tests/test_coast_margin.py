"""S4 coast margin: ZERO violations of SDF >= d_min for DP, refined and oracle policies, measured
exactly (bilinear SDF along every executed chord) and by the simulator, plus the safety guard."""

import numpy as np
import pytest

from horizon.geo.coast import (
    SDF_TOL_M,
    CoastModel,
    bilinear_sdf,
    segment_min_bilinear,
    signed_distance,
)
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    OraclePolicy,
    Plan,
    run_mission,
)
from horizon.sim.policies_refine import OracleRefinedPolicy, RefinedMPCPolicy
from horizon.weather.fields import Ensemble, WindField

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
H = 3600.0
D_MIN = 20e3


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
def hugging(grid):
    """Coast with a headland (mask-derived, kinked SDF) and a wind hotspot hugging it: the energy
    optimum lies exactly on the clearance limit."""
    X, Y = grid.xy_mesh()
    x0, y0 = grid.to_xy(-4.0, 46.0)
    land = (X > x0 + 220e3) | ((np.abs(Y - (y0 + 60e3)) < 45e3) & (X > x0 + 140e3))
    land |= (np.hypot(X - (x0 - 20e3), Y - (y0 + 230e3)) < 55e3)  # island
    coast = CoastModel(grid, signed_distance(grid, land))
    s = np.clip(coast.sdf / 1e3, 0.0, 400.0)
    speed = 6.0 + 9.0 * np.exp(-np.maximum(s - 20.0, 0.0) / 35.0)  # strongest right at the limit
    t = np.arange(0, 6 * 24 * H + 1, 3 * H)
    uv = np.zeros((t.size,) + grid.shape + (2,), np.float32)
    uv[..., 0] = -speed * 0.6  # blowing towards west-south-west: sailing along the coast pays
    uv[..., 1] = -speed * 0.8
    return coast, WindField(grid, EPOCH, t, uv), (x0, y0)


class FixedWeather:
    """Perfect forecast = the given truth."""

    def __init__(self, truth):
        self.truth_wf, self.grid = truth, truth.grid

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        from horizon.dp.solver import resample_wind
        t = issue_s + dt_s * np.arange(int(round(horizon_s / dt_s)) + 1)
        return Ensemble(self.grid, EPOCH, issue_s, t, resample_wind(self.truth_wf, t)[None],
                        np.ones(1))

    def truth(self, dt_s=3600.0):
        return self.truth_wf


def exact_chord_min(coast, res):
    return float(np.nanmin(coast.segment_min(res.x[:-1], res.y[:-1], res.x[1:], res.y[1:])))


# ----------------------------------------------------------------------------- primitive
def test_segment_min_exact_vs_dense_sampling():
    rng = np.random.default_rng(1)
    f = rng.normal(size=(9, 11)) * 30e3
    x0, y0, dx = 100.0, -50.0, 40e3
    for _ in range(200):
        a = np.array([x0 + rng.uniform(0, 10 * dx), y0 + rng.uniform(0, 8 * dx)])
        b = np.array([x0 + rng.uniform(0, 10 * dx), y0 + rng.uniform(0, 8 * dx)])
        ex = segment_min_bilinear(f, x0, y0, dx, a[0], a[1], b[0], b[1])
        s = np.linspace(0, 1, 4001)
        dense = min(bilinear_sdf(f, x0, y0, dx, a[0] + q * (b[0] - a[0]), a[1] + q * (b[1] - a[1]))
                    for q in s)
        assert ex <= dense + 1e-6
        assert ex >= dense - 100.0  # dense sampling (44 m spacing) is a tight upper bound
    assert np.isnan(segment_min_bilinear(f, x0, y0, dx, -1e6, 0.0, 0.0, 0.0))


def test_dp_arc_check_is_exact_on_bilinear_sdf(grid):
    """Regression S3: plain DP corner cutting (19.75 km) came from the dx/8 sampling gap."""
    from horizon.dp.kernel import arc_feasibility
    from horizon.dp.stencil import build_stencil

    X, Y = grid.xy_mesh()
    land = np.hypot(X - grid.to_xy(-4.0, 46.0)[0], Y - grid.to_xy(-4.0, 46.0)[1]) < 70e3
    coast = CoastModel(grid, signed_distance(grid, land))
    st = build_stencil(grid, 3 * H)
    ok = arc_feasibility(st.valid, st.di, st.dj, st.length_m, coast.sdf, grid.x0, grid.y0,
                         grid.dx, D_MIN)
    jj, ii, ss = np.nonzero(ok[:, :, 1:])
    for q in np.random.default_rng(0).choice(jj.size, 400, replace=False):
        j, i, s = jj[q], ii[q], ss[q] + 1
        xa, ya = grid.x0 + i * grid.dx, grid.y0 + j * grid.dx
        m = coast.segment_min(xa, ya, xa + st.di[s] * grid.dx, ya + st.dj[s] * grid.dx)
        assert m >= D_MIN - SDF_TOL_M


# ----------------------------------------------------------------------------- closed loop
def _policies(name, coast, polar, hold, truth, dur):
    if name == "DP":
        return DeterministicMPCPolicy(polar, hold, coast, horizon_days=2.0)
    if name == "REF":
        return RefinedMPCPolicy(DeterministicMPCPolicy(polar, hold, coast, horizon_days=2.0))
    if name == "ORACLE":
        return OraclePolicy(truth, polar, hold, coast, dur)
    return OracleRefinedPolicy(truth, polar, hold, coast, dur)


@pytest.mark.parametrize("name", ["DP", "REF", "ORACLE", "ORACLE_REF"])
def test_zero_violations_coast_hugging(name, hugging, polar, hold, pm):
    coast, truth, (x0, y0) = hugging
    dur = 2 * 24 * H
    wx = FixedWeather(truth)
    pol = _policies(name, coast, polar, hold, truth, dur)
    start = tuple(float(v) for v in coast.grid.to_lonlat(x0 + 100e3, y0 + 60e3))
    res = run_mission(pol, wx, truth, start, dur, pm, coast, guard=True)
    assert res.coast_violations == 0
    assert res.guard_interventions == 0  # planners alone keep the margin, the guard is idle
    assert exact_chord_min(coast, res) >= D_MIN - SDF_TOL_M
    assert res.min_margin_m >= -SDF_TOL_M
    # the scenario really hugs the coast (otherwise the test is vacuous)
    assert np.nanmin(coast.sdf_at(res.x, res.y)) < D_MIN + 30e3


# ----------------------------------------------------------------------------- guard
def test_guard_stops_a_suicidal_plan(hugging, pm):
    coast, truth, (x0, y0) = hugging
    g = coast.grid

    class Suicide:
        def plan(self, t_s, x, y, provider):
            return Plan(t_s, 3 * H, np.array([x + 400e3]), np.array([y]))  # straight into land

    start = tuple(float(v) for v in g.to_lonlat(x0 + 100e3, y0 + 60e3))
    wx = FixedWeather(truth)
    res = run_mission(Suicide(), wx, truth, start, 24 * H, pm, coast, guard=True)
    assert res.guard_interventions > 0
    assert res.coast_violations == 0
    assert exact_chord_min(coast, res) >= D_MIN - SDF_TOL_M
    assert res.min_margin_m >= -SDF_TOL_M
    assert len(res.guard_events) == min(res.guard_interventions, 1000)
    unguarded = run_mission(Suicide(), wx, truth, start, 24 * H, pm, coast, guard=False)
    assert unguarded.coast_violations > 0  # without the guard the same plan violates


@pytest.mark.parametrize("dy", [-40e3, 0.0, 40e3])
def test_refiner_exact_chord_verification_without_buffer(dy, hugging, polar):
    """S3 root cause: the NLP constrains a cubic-spline SDF, the simulator the bilinear one.
    With the safety buffer removed the exact post-solve chord check must still give >= d_min."""
    from horizon.refine import refine_plan

    coast, _, (x0, y0) = hugging
    g = coast.grid
    X, Y = g.xy_mesh()
    wind = WindField(g, EPOCH, np.arange(0, 24 * H + 1, 3 * H),
                     np.broadcast_to(np.array([8.0, 0.0], np.float32),
                                     (9,) + g.shape + (2,)).copy())
    xs0, ys0 = x0 + 60e3, y0 + 60e3 + dy
    pull = -np.hypot(X - (x0 + 170e3), Y - (y0 + 60e3 + dy)) / 1e3 * 60.0  # towards the headland
    n = 24
    k = np.arange(n + 1) * 1800.0
    warm = (xs0 + 3.0 * k, ys0 + 0.0 * k)
    r = refine_plan(wind, xs0, ys0, 0.0, pull, build_envelope(polar), coast, warm,
                    horizon_s=n * 1800.0, d_min=D_MIN, margin_m=200e3, safety_m=0.0)
    assert r.min_sdf_m >= D_MIN - SDF_TOL_M
    assert exact_chord_min_xy(coast, r.x, r.y) >= D_MIN - SDF_TOL_M


def exact_chord_min_xy(coast, x, y):
    return float(np.nanmin(coast.segment_min(x[:-1], y[:-1], x[1:], y[1:])))
