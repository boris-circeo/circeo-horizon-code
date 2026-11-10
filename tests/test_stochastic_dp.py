"""Tests of the two-stage CVaR DP (DES-860 §4.4, §4.9, §5.3.3, Annex A.2)."""


import numpy as np
import pytest

from horizon.dp import build_stencil, solve_dp
from horizon.dp.stochastic import (
    RiskSpec,
    aggregate_values,
    solve_stochastic_dp,
    weighted_cvar,
)
from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DirectPowerModel,
    EnvelopePowerModel,
    ForecastProvider,
    mission_metrics,
    run_mission,
)
from horizon.sim.policies_ens import EnsembleMPCPolicy
from horizon.weather.fields import WindField
from horizon.weather.synthetic import SyntheticWeather

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
H = 3600.0
DT = 3 * H


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold(polar):
    return hold_power_curve(polar)


@pytest.fixture(scope="module")
def grid():
    return Grid.from_bbox(-8, 2, 40, 46, 40e3)


@pytest.fixture(scope="module")
def sea(grid):
    return CoastModel(grid, np.full(grid.shape, 1e6, np.float32))


# ------------------------------------------------------------------------------- CVaR
def cvar_ru(z, w, alpha):
    """Rockafellar-Uryasev: max_eta eta - E[(eta - z)+] / alpha (optimum at an atom)."""
    return max(e - float((w * np.maximum(e - z, 0)).sum()) / alpha for e in z)


@pytest.mark.parametrize("seed", range(6))
def test_weighted_cvar_vs_ru_and_enumeration(seed):
    rng = np.random.default_rng(seed)
    z = rng.normal(100, 30, 7)
    w = rng.random(7)
    w /= w.sum()
    for alpha in (0.1, 0.2, 0.37, 0.5, 1.0):
        c = float(weighted_cvar(z, w, alpha))
        assert c == pytest.approx(cvar_ru(z, w, alpha), rel=1e-10)
        # brute force: split atoms into 1e4 sub-atoms and average the worst alpha fraction
        zz = np.repeat(z, np.round(w * 20000).astype(int))
        zz.sort()
        assert c == pytest.approx(zz[: int(round(alpha * zz.size))].mean(), rel=2e-3)
    assert float(weighted_cvar(z, w, 1.0)) == pytest.approx(float(w @ z))
    assert float(weighted_cvar(z, w, 0.2)) <= float(w @ z) + 1e-12


def test_weighted_cvar_known_and_vectorised():
    # 5 equal scenarios, alpha = 0.2: worst scenario only; alpha = 0.3: 2/3 worst + 1/3 second
    z = np.array([10.0, 50.0, 20.0, 40.0, 30.0])
    w = np.full(5, 0.2)
    assert float(weighted_cvar(z, w, 0.2)) == pytest.approx(10.0)
    assert float(weighted_cvar(z, w, 0.3)) == pytest.approx((0.2 * 10 + 0.1 * 20) / 0.3)
    zz = np.stack([z, z * 2], axis=1).reshape(5, 2, 1)
    out = weighted_cvar(zz, w, 0.2)
    assert out.shape == (2, 1) and out[:, 0] == pytest.approx([10.0, 20.0])


def test_aggregate_values_and_infeasible():
    z = np.array([[10.0, 10.0], [50.0, -np.inf], [30.0, 30.0]])
    w = np.array([0.5, 0.25, 0.25])
    vbar, mean, cvar = aggregate_values(z, w, RiskSpec(0.4, 0.5))
    assert mean[0] == pytest.approx(0.5 * 10 + 0.25 * 50 + 0.25 * 30)
    assert cvar[0] == pytest.approx(10.0)
    assert vbar[0] == pytest.approx(mean[0] - 0.4 * (mean[0] - cvar[0]))
    assert vbar[1] == -np.inf and not np.isnan(vbar).any()  # unreachable in one scenario
    # a zero-weight infeasible scenario is ignored
    vb2, _, _ = aggregate_values(z, np.array([0.5, 0.0, 0.5]), RiskSpec(0.4, 0.5))
    assert np.isfinite(vb2).all()
    with pytest.raises(ValueError):
        RiskSpec(1.5)
    with pytest.raises(ValueError):
        RiskSpec(0.3, 0.0)


# ---------------------------------------------------------------------------- DP fixtures
def smooth_wind(grid, n, phase=0.0, amp=4.0):
    X, Y = grid.xy_mesh()
    t = DT * np.arange(n + 1)
    uv = np.empty((n + 1, grid.ny, grid.nx, 2), np.float32)
    for k, tk in enumerate(t):
        s = 8 + amp * np.sin(X / 3e5 + tk / 1e5 + phase) * np.cos(Y / 2e5)
        d = np.radians(250 + 60 * np.sin(Y / 4e5 - tk / 1.5e5 + phase))
        uv[k, ..., 0], uv[k, ..., 1] = -s * np.sin(d), -s * np.cos(d)
    return WindField(grid, EPOCH, t, uv)


N_TOT, N_SPLIT = 12, 4


def run(scen, w, short, polar, hold, sea, risk=None, **kw):
    return solve_stochastic_dp(scen, w, short, 0.0, N_TOT * DT, DT, polar, hold, sea,
                               split_s=N_SPLIT * DT, risk=risk, **kw)


def test_single_scenario_equals_deterministic(grid, sea, polar, hold):
    wind = smooth_wind(grid, N_TOT)
    ref = solve_dp(wind, 0.0, N_TOT, DT, polar, hold, sea)
    for gamma in (0.0, 0.7):
        r = run([wind], [1.0], wind, polar, hold, sea, RiskSpec(gamma, 0.2))
        fin = np.isfinite(ref.V[0])
        assert np.array_equal(fin, np.isfinite(r.v_t0))
        assert np.allclose(r.v_t0[fin], ref.V[0][fin], rtol=1e-6, atol=1e-3)
        assert np.allclose(r.short.V[-1][fin], ref.V[N_SPLIT][fin], rtol=1e-6, atol=1e-3)


def test_identical_scenarios_give_deterministic_value(grid, sea, polar, hold):
    wind = smooth_wind(grid, N_TOT)
    ref = solve_dp(wind, 0.0, N_TOT, DT, polar, hold, sea)
    for gamma in (0.0, 0.5, 1.0):
        r = run([wind] * 4, [0.1, 0.2, 0.3, 0.4], wind, polar, hold, sea, RiskSpec(gamma, 0.2))
        fin = np.isfinite(ref.V[N_SPLIT])
        assert np.allclose(r.v_bar[fin], ref.V[N_SPLIT][fin], rtol=1e-5, atol=1e-2)
        assert np.allclose(r.v_t0[fin], ref.V[0][fin], rtol=1e-5, atol=1e-2)
        assert r.scenario_values.shape == (4,) + grid.shape


def test_vbar_monotone_in_gamma_and_bounded(grid, sea, polar, hold):
    scen = [smooth_wind(grid, N_TOT, ph, amp) for ph, amp in ((0, 4), (1.5, 6), (3.0, 3), (4.5, 7))]
    w = [0.4, 0.3, 0.2, 0.1]
    st = build_stencil(grid, DT)
    prev, vals = None, []
    for gamma in (0.0, 0.2, 0.5, 1.0):
        r = run(scen, w, scen[0], polar, hold, sea, RiskSpec(gamma, 0.2), stencil=st)
        fin = np.isfinite(r.v_bar)
        if prev is not None:
            assert np.all(r.v_bar[fin] <= prev[fin] + 1e-3)
        prev = r.v_bar
        vals.append(float(r.v_bar[fin].mean()))
        assert np.all(r.v_cvar[fin] <= r.v_mean[fin] + 1e-3)
        assert np.all(r.v_bar[fin] <= r.v_mean[fin] + 1e-3)
        assert np.all(r.v_bar[fin] >= r.scenario_values[:, fin].min(0) - 1e-3)
    assert vals[0] > vals[-1]  # strict somewhere: the scenarios do differ
    r0 = run(scen, w, scen[0], polar, hold, sea, RiskSpec(0.0, 0.2), stencil=st)
    assert np.allclose(r0.v_bar[fin], r0.v_mean[fin])


def test_non_anticipative_trunk_is_single_and_scenario_pre_split_irrelevant(
        grid, sea, polar, hold):
    scen = [smooth_wind(grid, N_TOT, ph) for ph in (0.0, 2.0, 4.0)]
    w = [0.5, 0.3, 0.2]
    short = smooth_wind(grid, N_TOT, 0.7)
    r = run(scen, w, short, polar, hold, sea)
    assert r.short.policy.shape[0] == N_SPLIT  # one policy array, no scenario axis
    assert r.path(grid.ny // 2, grid.nx // 2).k.tolist() == list(range(N_SPLIT))
    # scramble the scenarios BEFORE the split: the common trunk must not change
    scr = []
    for s in scen:
        uv = s.uv.copy()
        uv[:N_SPLIT] = -uv[:N_SPLIT]
        scr.append(WindField(grid, EPOCH, s.times_s, uv))
    r2 = run(scr, w, short, polar, hold, sea)
    assert np.array_equal(r.short.policy, r2.short.policy)
    assert np.array_equal(r.v_t0, r2.v_t0)


def test_scenario_values_match_branch_dp(grid, sea, polar, hold):
    scen = [smooth_wind(grid, N_TOT, ph) for ph in (0.0, 2.0)]
    r = run(scen, [0.5, 0.5], scen[0], polar, hold, sea)
    for s, wind in enumerate(scen):
        ref = solve_dp(wind, N_SPLIT * DT, N_TOT - N_SPLIT, DT, polar, hold, sea)
        assert np.array_equal(r.scenario_values[s], ref.V[0])
    assert r.split_time_s == N_SPLIT * DT


def test_terminal_and_input_validation(grid, sea, polar, hold):
    wind = smooth_wind(grid, N_TOT)
    term = np.full(grid.shape, 100.0, np.float32)
    r0 = run([wind], [1.0], wind, polar, hold, sea)
    r1 = run([wind], [1.0], wind, polar, hold, sea, terminal=term)
    r2 = run([wind, wind], [0.5, 0.5], wind, polar, hold, sea, terminal=[term, term])
    fin = np.isfinite(r0.v_t0)
    assert np.allclose(r1.v_t0[fin] - r0.v_t0[fin], 100.0, atol=0.1)
    assert np.allclose(r2.v_t0[fin], r1.v_t0[fin], atol=0.1)
    with pytest.raises(ValueError):
        run([wind], [0.5], wind, polar, hold, sea)
    with pytest.raises(ValueError):
        solve_stochastic_dp([wind], [1.0], wind, 0.0, 4 * DT, DT, polar, hold, sea,
                            split_s=4 * DT)


# ---------------------------------------------------------- ensemble beats deterministic
def front_wind(grid, centre_y, n_tot, n_split):
    """Calm (2 m/s) except a strong westerly (14 m/s) patch at ``y = centre_y`` [m],
    present only for DP steps ``n_split + 2 .. n_split + 6`` (a front passing)."""
    X, Y = grid.xy_mesh()
    t = DT * np.arange(n_tot + 1)
    uv = np.zeros((n_tot + 1, grid.ny, grid.nx, 2), np.float32)
    uv[..., 0] = 2.0
    patch = np.exp(-((X - 0.0) ** 2 + (Y - centre_y) ** 2) / (2 * 120e3 ** 2))
    for k in range(n_tot + 1):
        if n_split + 2 <= k <= n_split + 6:
            uv[k, ..., 0] = 2.0 + 12.0 * patch
    return WindField(grid, EPOCH, t, uv)


def test_ensemble_beats_deterministic_front_north_vs_south(grid, sea, polar, hold):
    n_tot, n_split = 12, 4
    north, south = (front_wind(grid, y, n_tot, n_split) for y in (+260e3, -260e3))
    # start at the centre of the domain
    cj, ci = grid.ny // 2, grid.nx // 2
    w = [0.5, 0.5]
    st = build_stencil(grid, DT)

    def total_expected(end_cell, trunk_kwh, res):
        return trunk_kwh + float(sum(wi * res.scenario_values[s][end_cell]
                                     for s, wi in enumerate(w)))

    def trunk_of(wind_full):
        """Route optimal for ``wind_full`` over the whole horizon; trunk end cell + energy."""
        d = solve_dp(wind_full, 0.0, n_tot, DT, polar, hold, sea, stencil=st)
        p = d.path(cj, ci, 0)
        return (int(p.j_end[n_split - 1]), int(p.i_end[n_split - 1])), float(
            p.reward[:n_split].sum())

    mean = WindField(grid, EPOCH, north.times_s, 0.5 * (north.uv + south.uv))
    sto = solve_stochastic_dp([north, south], w, north, 0.0, n_tot * DT, DT, polar, hold, sea,
                              split_s=n_split * DT, risk=RiskSpec(0.0, 0.2), stencil=st)
    p = sto.path(cj, ci)
    sto_cell, sto_trunk = (int(p.j_end[-1]), int(p.i_end[-1])), float(p.energy_kwh)
    e_sto = total_expected(sto_cell, sto_trunk, sto)
    e_alt = {}
    for name, fld in (("mean", mean), ("north", north), ("south", south)):
        cell, trunk = trunk_of(fld)
        e_alt[name] = total_expected(cell, trunk, sto)
    # the stochastic plan hedges: it ends the trunk between the two fronts ...
    y_end = grid.y0 + sto_cell[0] * grid.dx
    assert abs(y_end) < 130e3
    # ... and has strictly more expected energy than plans optimal for the mean or one member
    for name, e in e_alt.items():
        assert e_sto > e + 1.0, (name, e_sto, e)
    # sanity: the value is the expectation of the scenario values (gamma = 0)
    assert sto.v_t0[cj, ci] == pytest.approx(e_sto, rel=1e-4)
    # CVaR-averse variant keeps a hedged position and a higher worst-case than the north plan
    cv = solve_stochastic_dp([north, south], w, north, 0.0, n_tot * DT, DT, polar, hold, sea,
                             split_s=n_split * DT, risk=RiskSpec(0.5, 0.5), stencil=st)
    pc = cv.path(cj, ci)
    cell_c = (int(pc.j_end[-1]), int(pc.i_end[-1]))
    worst_c = cv.scenario_values[:, cell_c[0], cell_c[1]].min()
    cell_n, _ = trunk_of(north)
    assert worst_c >= sto.scenario_values[:, cell_n[0], cell_n[1]].min() - 1.0


# ------------------------------------------------------------------------------- policy
def test_ensemble_policy_closed_loop(polar, hold):
    g = Grid.from_bbox(-12, 4, 38, 54, 40e3)
    sea_g = CoastModel(g, np.full(g.shape, 1e6, np.float32))
    pm = EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))
    T = 3 * 86400.0
    wx = SyntheticWeather(g, EPOCH, T + 6 * 86400.0, seed=7)
    pol = EnsembleMPCPolicy(polar, hold, sea_g, horizon_days=5.0, n_members=8, k=3, gamma=0.3)
    x, y = g.to_xy(-4.0, 46.0)
    plan = pol.plan(0.0, x, y, ForecastProvider(wx, 0.0, T + 6 * 86400.0))
    assert plan.x.size == 16  # 48 h trunk at 3 h
    d = pol.last_diagnostics
    assert len(d["members"]) == 3 and sum(d["weights"]) == pytest.approx(1.0)
    assert all(isinstance(m, int) for m in d["members"])
    assert d["vbar_min_kwh"] <= d["vbar_mean_kwh"] <= d["vbar_max_kwh"]
    assert d["v_cvar_at_split_kwh"] <= d["v_mean_at_split_kwh"] + 1e-3
    res = run_mission(pol, wx, wx.truth(), (-4.0, 46.0), T, pm, sea_g)
    assert res.coast_violations == 0 and mission_metrics(res).energy_kwh > 0
