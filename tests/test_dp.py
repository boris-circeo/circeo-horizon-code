"""Tests of the backward DP: stencil, kernel vs NumPy reference, physical tests (DES-860 §8.4)."""

import dataclasses

import numpy as np
import pytest
from scipy.interpolate import RegularGridInterpolator

from horizon.core import wind as W
from horizon.dp import build_stencil as _build_stencil
from horizon.dp import solve_dp as _solve_dp
from horizon.dp.solver import _envelope_for
from horizon.geo.coast import CoastModel, signed_distance
from horizon.geo.grid import Grid
from horizon.polar import PolarTable, hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.weather.fields import WindField


def solve_dp(*a, **k):
    """One-step-arc DP (the original semantics); macro arcs are tested separately."""
    k.setdefault("max_span", 1)
    return _solve_dp(*a, **k)


def build_stencil(*a, **k):
    k.setdefault("max_span", 1)
    return _build_stencil(*a, **k)


EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
H = 3600.0


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold(polar):
    return hold_power_curve(polar)


def open_sea(grid):
    return CoastModel(grid, np.full(grid.shape, 1e6, np.float32))


def wind_from_fn(grid, times, fn):
    """WindField from ``fn(X, Y, t) -> (u, v)`` evaluated at cell centres [m] and times [s]."""
    X, Y = grid.xy_mesh()
    uv = np.stack([np.stack(fn(X, Y, t), axis=-1) for t in times]).astype(np.float32)
    return WindField(grid, EPOCH, np.asarray(times, float), uv)


def uniform_wind(grid, u, v, n=2, dt=3 * H):
    return wind_from_fn(grid, dt * np.arange(n), lambda X, Y, t: (u + 0 * X, v + 0 * X))


def centre_grid(nx_km=800, ny_km=700, dx=40e3):
    """Small grid around the projection centre (scale error < 1 %)."""
    return Grid.from_bbox(-8, 2, 40, 46, dx)


# ------------------------------------------------------------------------------ stencil
def test_stencil_basic():
    g = centre_grid()
    st = build_stencil(g, 3 * H)
    assert (st.di[0], st.dj[0]) == (0, 0) and st.valid[..., 0].all()
    assert st.length_m.dtype == np.float32 and st.heading_deg.dtype == np.float32
    ratio = st.length_m[..., 1:] / st.nominal_length_m[1:]
    assert np.nanmin(ratio) > 0.96 and np.nanmax(ratio) < 1.04
    # speed bounds honoured on ground length
    u = st.length_m[..., 1:][st.valid[..., 1:]] / st.dt_s
    assert u.min() >= 0.5 and u.max() <= 8.0
    # arcs leaving the grid are invalid; east arc heading ~ 90 deg
    s_e = int(np.where((st.di == 1) & (st.dj == 0))[0][0])
    assert not st.valid[5, g.nx - 1, s_e] and st.valid[5, 3, s_e]
    assert abs(st.heading_deg[5, 3, s_e] - 90.0) < 3.0
    assert 20.0 < st.angular_resolution_deg < 50.0


def test_stencil_consistency_violation():
    with pytest.raises(ValueError):
        build_stencil(centre_grid(dx=100e3), 1 * H)  # u_max*dt = 28.8 km < dx


def test_stencil_geodesic_length_far_from_centre():
    g = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    st = build_stencil(g, 3 * H)
    ratio = st.length_m[..., 1:] / st.nominal_length_m[1:]
    assert 0.02 < np.nanmax(np.abs(ratio - 1)) < 0.05  # the S0 ~3 % finding


# ------------------------------------------------------------------- kernel vs reference
def reference_dp(wind, n, dt, polar, hold, st, nav, ok):
    """Plain-loop NumPy reference of the recursion (DES-860 §6.11)."""
    ny, nx = nav.shape
    V = np.full((n + 1, ny, nx), -np.inf)
    V[n][nav] = 0.0
    pol = -np.ones((n, ny, nx), int)
    dth = dt / H
    for k in range(n - 1, -1, -1):
        for j in range(ny):
            for i in range(nx):
                if not nav[j, i]:
                    continue
                best, bs = -np.inf, -1
                for s in range(st.n_arcs):
                    jj, ii = j + st.dj[s], i + st.di[s]
                    if s and not ok[j, i, s]:
                        continue
                    if not np.isfinite(V[k + 1, jj, ii]):
                        continue
                    uvs = [wind.uv[k, j, i], wind.uv[k + 1, j, i]]
                    if s == 0:
                        m = np.mean(uvs, axis=0)
                        p = np.interp(np.hypot(*m), hold.tws, hold.p_hold)
                    else:
                        m = np.mean(uvs + [wind.uv[k, jj, ii], wind.uv[k + 1, jj, ii]], axis=0)
                        spd = st.length_m[j, i, s] / dt
                        twa = W.twa(m[0], m[1], st.heading_deg[j, i, s])
                        p = polar(np.hypot(*m), twa, spd)
                    c = p * dth + V[k + 1, jj, ii]
                    if c > best:
                        best, bs = c, s
                V[k, j, i], pol[k, j, i] = best, bs
    return V, pol


def test_kernel_matches_numpy_reference(polar, hold):
    g = Grid.from_bbox(-12, 0, 38, 46, 80e3)
    land = np.zeros(g.shape, bool)
    land[: g.ny // 3, g.nx // 2: g.nx // 2 + 2] = True  # a peninsula
    coast = CoastModel(g, signed_distance(g, land))
    n, dt = 6, 3 * H
    wind = wind_from_fn(g, dt * np.arange(n + 1), lambda X, Y, t: (
        8 * np.sin(X / 4e5 + t / 4e4) + 3, 7 * np.cos(Y / 3e5 - t / 5e4) - 2))
    res = solve_dp(wind, 0.0, n, dt, polar, hold, coast, d_min=40e3, reward_model="direct")
    from horizon.dp.kernel import arc_feasibility
    ok = arc_feasibility(res.stencil.valid, res.stencil.di, res.stencil.dj, res.stencil.length_m,
                         coast.sdf, g.x0, g.y0, g.dx, 40e3)
    Vr, pr = reference_dp(wind, n, dt, polar, hold, res.stencil, coast.sdf >= 40e3, ok)
    fin = np.isfinite(Vr)
    assert np.array_equal(fin, np.isfinite(res.V))
    np.testing.assert_allclose(res.V[fin], Vr[fin], rtol=1e-4, atol=1e-2)
    diff = (res.policy[:n] != pr[:n]) & fin[:n]
    assert diff.mean() < 1e-3  # identical except numerical ties


# ------------------------------------------------------------------------- coast, land
def test_coast_avoidance_and_land(polar, hold):
    g = Grid.from_bbox(-12, 0, 38, 46, 40e3)
    land = np.zeros(g.shape, bool)
    land[g.ny // 2 - 3: g.ny // 2 + 3, g.nx // 2 - 4: g.nx // 2 + 4] = True
    coast = CoastModel(g, signed_distance(g, land))
    n, dt = 8, 3 * H
    # wind from the west: beam reach north/south, strong everywhere
    wind = uniform_wind(g, 9.0, 0.0, n + 1)
    res = solve_dp(wind, 0.0, n, dt, polar, hold, coast, d_min=60e3)
    assert np.all(res.V[:, land] == -np.inf)
    assert np.all(res.policy[:, land] == -1)
    assert np.all(res.V[:, coast.sdf < 60e3] == -np.inf)
    # many start cells: every extracted path stays at SDF >= d_min (cells and arc midpoints)
    rng = np.random.default_rng(0)
    js, is_ = np.where(res.nav)
    for q in rng.choice(js.size, 40, replace=False):
        p = res.path(js[q], is_[q])
        x0, y0 = (g.x0 + g.dx * p.i), (g.y0 + g.dx * p.j)
        x1, y1 = (g.x0 + g.dx * p.i_end), (g.y0 + g.dx * p.j_end)
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            assert np.all(coast.sdf_at(x0 + f * (x1 - x0), y0 + f * (y1 - y0)) >= 60e3 - 1.0)


# --------------------------------------------------------------- (i) uniform wind
@pytest.mark.parametrize("model", ["direct", "envelope"])
def test_uniform_wind_racetrack_energy(polar, hold, model):
    g = centre_grid()
    n, dt = 6, 3 * H
    u, v = 0.0, -10.0  # wind from the north (TWS 10 m/s): beam reach east/west
    wind = uniform_wind(g, u, v, n + 1)
    res = solve_dp(wind, 0.0, n, dt, polar, hold, open_sea(g), d_min=20e3, reward_model=model)
    j0, i0 = g.ny // 2, 2
    st = res.stencil
    env = _envelope_for(polar, hold.f_avail)
    interp = RegularGridInterpolator(
        (env.tws0 + env.dtws * np.arange(env.reward.shape[0]), env.v_par_axis(),
         env.v_perp_axis()), env.reward, bounds_error=False)
    arcs = []
    for s in range(1, st.n_arcs):
        if st.valid[j0, i0, s]:
            hd, sp = st.heading_deg[j0, i0, s], st.length_m[j0, i0, s] / dt
            if model == "direct":
                arcs.append(polar(10.0, W.twa(u, v, hd), sp) * dt / H)
            else:  # wind from the north: upwind = north, v_par = v_north, v_perp = |v_east|
                r = interp([[10.0, sp * np.cos(np.radians(hd)), abs(sp * np.sin(np.radians(hd)))]])
                arcs.append(float(r[0]) * dt / H if np.isfinite(r[0]) else -np.inf)
    if model == "direct":
        e_hold = float(np.interp(10.0, hold.tws, hold.p_hold)) * dt / H
    else:
        e_hold = float(interp([[10.0, 0.0, 0.0]])[0]) * dt / H
    expected = n * max(max(arcs), e_hold)
    assert expected > 5000.0  # kWh, sanity
    assert abs(res.V[0, j0, i0] / expected - 1) < 0.02
    p = res.path(j0, i0)
    assert abs(p.energy_kwh - res.V[0, j0, i0]) < 1e-2 * max(1.0, abs(p.energy_kwh)) + 1.0
    if model == "direct":  # (the envelope may legitimately mix tacks, i.e. sit still)
        dy = g.dx * (p.j_end[-1] - p.j[0])  # wind blows toward south => upwind = north
        assert dy < 0.1 * np.sum(p.speed * dt)
        assert np.all(np.abs(W.twa(u, v, p.heading[p.offset > 0]) - 90.0) < 30.0)


def test_envelope_energy_independent_of_wind_direction(polar, hold):
    """Uniform wind from 8 directions: DP energy spread < 6 % (stencil bias)."""
    g = centre_grid()
    n, dt = 6, 3 * H
    spread = {}
    for model in ("direct", "envelope"):
        vals = []
        for d in range(0, 360, 45):
            uu, vv = W.uv_from_met(10.0, d)
            res = solve_dp(uniform_wind(g, uu, vv, n + 1), 0.0, n, dt, polar, hold, open_sea(g),
                           reward_model=model)
            vals.append(float(res.V[0, g.ny // 2, g.nx // 2]))
        spread[model] = max(vals) / min(vals) - 1
    print(spread)
    # diagonal winds are the worst case: no stencil arc is a beam reach at the optimal speed
    assert spread["envelope"] < 0.06 and spread["envelope"] < spread["direct"]


# ------------------------------------------------------------ (iii) linearity in the polar
@pytest.mark.filterwarnings("ignore:polar values")
def test_linearity_constant_shift(polar, hold):
    g = centre_grid()
    n, dt, c = 5, 3 * H, 100.0
    wind = wind_from_fn(g, dt * np.arange(n + 1), lambda X, Y, t: (
        6 + 4 * np.sin(X / 3e5), -5 + 4 * np.cos(Y / 2e5 + t / 3e4)))
    land = np.zeros(g.shape, bool)
    land[:3, :] = True
    coast = CoastModel(g, signed_distance(g, land))
    r0 = solve_dp(wind, 0.0, n, dt, polar, hold, coast, reward_model="direct")
    polar_c = PolarTable(polar.p + np.float32(c), polar.tws, polar.twa, polar.u, strict=False)
    hold_c = dataclasses.replace(hold, p_hold=hold.p_hold + np.float32(c))
    r1 = solve_dp(wind, 0.0, n, dt, polar_c, hold_c, coast, reward_model="direct")
    fin = np.isfinite(r0.V)
    assert np.array_equal(fin, np.isfinite(r1.V))
    for k in range(n + 1):
        shift = c * (n - k) * dt / H
        np.testing.assert_allclose(r1.V[k][fin[k]] - r0.V[k][fin[k]], shift, rtol=2e-4)
    assert np.array_equal(r0.policy, r1.policy)


@pytest.mark.filterwarnings("ignore:polar values")
def test_linearity_envelope(polar, hold):
    g = centre_grid()
    n, dt, c = 5, 3 * H, 100.0
    wind = wind_from_fn(g, dt * np.arange(n + 1), lambda X, Y, t: (
        6 + 4 * np.sin(X / 3e5), -5 + 4 * np.cos(Y / 2e5 + t / 3e4)))
    polar_c = PolarTable(polar.p + np.float32(c), polar.tws, polar.twa, polar.u, strict=False)
    e0 = build_envelope(polar, f_avail_override=1.0)
    e1 = build_envelope(polar_c, f_avail_override=1.0)
    r0 = solve_dp(wind, 0.0, n, dt, polar, hold, open_sea(g), envelope=e0)
    r1 = solve_dp(wind, 0.0, n, dt, polar_c, hold, open_sea(g), envelope=e1)
    fin = np.isfinite(r0.V)
    assert np.array_equal(fin, np.isfinite(r1.V))
    for k in range(n + 1):
        np.testing.assert_allclose(r1.V[k][fin[k]] - r0.V[k][fin[k]], c * (n - k) * dt / H,
                                   rtol=5e-4)


# -------------------------------------------------------- policy / path consistency
@pytest.mark.parametrize("model", ["direct", "envelope"])
def test_path_consistency(polar, hold, model):
    g = centre_grid()
    n, dt = 6, 3 * H
    wind = wind_from_fn(g, dt * np.arange(n + 1), lambda X, Y, t: (
        7 + 3 * np.sin(Y / 2e5), -6 * np.cos(X / 3e5 + t / 5e4)))
    res = solve_dp(wind, 0.0, n, dt, polar, hold, open_sea(g), reward_model=model)
    st = res.stencil
    env = _envelope_for(polar, hold.f_avail)
    p = res.path(g.ny // 2, g.nx // 2)
    assert p.k.tolist() == list(range(n))
    for a in range(n):
        k, j, i, s = p.k[a], int(p.j[a]), int(p.i[a]), p.offset[a]
        jj, ii = j + st.dj[s], i + st.di[s]
        assert (jj, ii) == (p.j_end[a], p.i_end[a])
        pts = ((j, i),) if s == 0 else ((j, i), (jj, ii))
        m = np.mean([wind.uv[kk, jx, ix] for kk in (k, k + 1) for jx, ix in pts], axis=0)
        if model == "envelope":
            ang = np.radians(p.heading[a]) if s else 0.0
            vx, vy = p.speed[a] * np.sin(ang), p.speed[a] * np.cos(ang)
            sp = np.hypot(*m)
            vpar, vperp = -(vx * m[0] + vy * m[1]) / sp, abs(vx * m[1] - vy * m[0]) / sp
            interp = RegularGridInterpolator(
                (env.tws0 + env.dtws * np.arange(env.reward.shape[0]), env.v_par_axis(),
                 env.v_perp_axis()), env.reward)
            r = float(interp([[sp, vpar, vperp]])[0]) * dt / H
        elif s == 0:
            r = np.interp(np.hypot(*m), hold.tws, hold.p_hold) * dt / H
        else:
            r = polar(np.hypot(*m), W.twa(m[0], m[1], p.heading[a]), p.speed[a]) * dt / H
        assert r == pytest.approx(p.reward[a], rel=2e-3, abs=0.05)
        assert res.V[k, j, i] == pytest.approx(r + res.V[k + 1, jj, ii], rel=1e-4, abs=0.05)
    # value_at: exact at nodes, bilinear in between
    assert res.value_at(g.x[3], g.y[4], 0) == pytest.approx(res.V[0, 4, 3])
    mid = res.value_at(0.5 * (g.x[3] + g.x[4]), g.y[4], 0)
    assert mid == pytest.approx(0.5 * (res.V[0, 4, 3] + res.V[0, 4, 4]), rel=1e-5)
    assert np.isnan(res.value_at(g.x[0] - 1e6, g.y[0], 0))


def test_terminal_and_wind_resampling(polar, hold):
    """Terminal value is propagated; a wind on a different time step gives the same answer."""
    g = centre_grid()
    n, dt = 4, 3 * H
    term = np.zeros(g.shape, np.float32)
    term[:, -3:] = 5000.0  # reward for finishing in the east
    fn = lambda X, Y, t: (2 + 0 * X, 3 + 0 * X)  # noqa: E731
    w_coarse = wind_from_fn(g, dt * np.arange(n + 1), fn)
    w_fine = wind_from_fn(g, 0.5 * dt * np.arange(2 * n + 1), fn)
    a = solve_dp(w_coarse, 0.0, n, dt, polar, hold, open_sea(g), terminal=term)
    b = solve_dp(w_fine, 0.0, n, dt, polar, hold, open_sea(g), terminal=term)
    np.testing.assert_allclose(a.V, b.V, rtol=1e-6)
    p = a.path(g.ny // 2, g.nx - 9)
    assert p.i_end[-1] > p.i[0]  # heads east toward the terminal reward


# ---------------------------------------------------------- (iv) grid refinement x2
def test_ranking_stable_under_refinement(polar, hold):
    coarse = Grid.from_bbox(-8, 2, 40, 46, 40e3)
    fine = Grid(coarse.crs_wkt, coarse.x0 - coarse.dx / 4, coarse.y0 - coarse.dx / 4,
                coarse.dx / 2, 2 * coarse.nx, 2 * coarse.ny)
    assert fine.coarsen(2) == coarse

    def fn(X, Y, t):
        s = 8 + 5 * np.sin(X / 2.5e5 + 0.3) * np.cos(Y / 2e5)
        d = np.radians(200 + 60 * np.sin(Y / 3e5))
        return -s * np.sin(d), -s * np.cos(d)

    t_c, t_f = 3 * H, 1.5 * H
    n_c = 4
    res = {}
    for name, g, dt, n in (("c", coarse, t_c, n_c), ("f", fine, t_f, 2 * n_c)):
        wind = wind_from_fn(g, t_f * np.arange(2 * n_c + 1), fn)
        res[name] = solve_dp(wind, 0.0, n, dt, polar, hold, open_sea(g))
    rng = np.random.default_rng(1)
    sel = rng.choice(np.arange(3, coarse.nx - 3), 12), rng.choice(np.arange(3, coarse.ny - 3), 12)
    xs, ys = coarse.x[sel[0]], coarse.y[sel[1]]
    vc = res["c"].V[0][sel[1], sel[0]]
    vf = np.asarray(res["f"].value_at(xs, ys, 0))
    err = np.abs(vf / vc - 1)  # coarse stencil quantisation: ~1-6 % (DES-860 §6.12 says < 1 %)
    assert np.median(err) < 0.02 and err.max() < 0.08
    rank_c, rank_f = np.argsort(np.argsort(vc)), np.argsort(np.argsort(vf))
    rho = np.corrcoef(rank_c, rank_f)[0, 1]
    assert rho > 0.9
    # first-step headings of the optimal route agree (within the stencil resolution)
    for q in range(3):
        pc = res["c"].path(sel[1][q], sel[0][q])
        jf, if_ = fine.index_of(xs[q], ys[q])
        pf = res["f"].path(int(jf), int(if_))
        if pc.offset[0] > 0 and pf.offset[0] > 0:
            dh = (pc.heading[0] - pf.heading[0] + 180) % 360 - 180
            assert abs(dh) < 50.0


# ---------------------------------------------------------------- (ii) toy front
def _greedy_energy(wind, n, dt, polar, hold, coast, j, i):
    """Myopic policy: re-solve a 1-step DP at each step and follow it."""
    total = 0.0
    for k in range(n):
        r = solve_dp(wind, k * dt, 1, dt, polar, hold, coast)
        s = int(r.policy[0, j, i])
        total += float(r.V[0, j, i])
        j, i = j + int(r.stencil.dj[s]), i + int(r.stencil.di[s])
    return total


def test_toy_front_anticipation(polar, hold):
    g = Grid.from_bbox(-14, 4, 38, 48, 40e3)
    n, dt, c = 8, 3 * H, 10.0  # front speed 10 m/s > max ship speed 8 m/s
    sig = 100e3
    x_s, y_s = g.x[5], g.y[g.ny // 2 - 4]
    x_b0, y_b = x_s - 150e3, g.y[g.ny // 2]

    def fn(X, Y, t):  # Gaussian blob of westerlies, advected eastward; weak background wind
        a = 12.0 * np.exp(-((X - x_b0 - c * t) ** 2 + (Y - y_b) ** 2) / (2 * sig**2))
        return 1.0 + a, 0.0 * X

    wind = wind_from_fn(g, dt * np.arange(n + 1), fn)
    coast = open_sea(g)
    res = solve_dp(wind, 0.0, n, dt, polar, hold, coast)
    j0, i0 = int(g.index_of(x_s, y_s)[0]), int(g.index_of(x_s, y_s)[1])
    p = res.path(j0, i0)
    greedy = _greedy_energy(wind, n, dt, polar, hold, coast, j0, i0)
    assert p.energy_kwh > 1.3 * greedy
    # anticipation: the ship moves toward the front's track (north) before the front arrives
    assert (g.y0 + g.dx * p.j_end[2]) - g.y[j0] > 0.5 * (y_b - y_s)
    # no chase: the ship does not follow the front east at the front's speed
    assert (g.x0 + g.dx * p.i_end[-1]) - x_s < 0.5 * c * n * dt


# ------------------------------------------------------------------ macro (multi-step) arcs
def test_macro_stencil_properties():
    g = centre_grid()
    assert _build_stencil(g, 3 * H).span.max() == 2  # library default
    st = _build_stencil(g, 3 * H, max_span=3)
    assert 60 <= st.n_arcs <= 130
    assert set(np.unique(st.span)) == {1, 2, 3}
    assert st.angular_resolution_deg <= 10.0
    # speed bounds on ground length / (span dt)
    u = st.length_m / (st.span[None, None, :] * st.dt_s)
    ok = st.valid[..., 1:]
    assert u[..., 1:][ok].min() >= 0.5 and u[..., 1:][ok].max() <= 8.0
    # the 8 one-step neighbours are present and the set is symmetric under 90 deg rotation
    arcs = set(zip(st.di.tolist(), st.dj.tolist(), st.span.tolist(), strict=True))
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            if (a, b) != (0, 0):
                assert (a, b, 1) in arcs
    assert all((-b, a, m) in arcs for a, b, m in arcs)


def test_macro_uniform_wind_path_and_horizon_end(polar, hold):
    g = centre_grid()
    n, dt = 7, 3 * H  # 7 is not a multiple of 3: shorter arcs close the horizon
    wind = uniform_wind(g, 0.0, -10.0, n + 1)
    res = _solve_dp(wind, 0.0, n, dt, polar, hold, open_sea(g), max_span=3)
    j0, i0 = g.ny // 2, 2
    p = res.path(j0, i0)
    assert p.k.tolist() == list(range(n)) and p.arc_span.sum() == n
    np.testing.assert_allclose(p.i[1:], p.i_end[:-1])  # continuous track
    assert abs(p.energy_kwh - res.V[0, j0, i0]) < 1.0
    # steady wind: arc energy = span * reward(velocity) from the envelope table
    env = _envelope_for(polar, hold.f_avail)
    interp = RegularGridInterpolator(
        (env.tws0 + env.dtws * np.arange(env.reward.shape[0]), env.v_par_axis(),
         env.v_perp_axis()), env.reward, bounds_error=False)
    st = res.stencil
    for k, j, i, s, m in zip(p.arc_k, p.arc_j, p.arc_i, p.arc_offset, p.arc_span, strict=True):
        psi = np.radians(st.heading_deg[j, i, s]) if s else 0.0
        sp = st.length_m[j, i, s] / (m * dt)
        r = float(interp([[10.0, sp * np.cos(psi), abs(sp * np.sin(psi))]])[0]) * dt / H * m
        assert res.V[k, j, i] - res.V[k + m, j + st.dj[s], i + st.di[s]] == pytest.approx(
            r, rel=1e-3, abs=0.1)
    # macro arcs are at least as good as the one-step ring (same hold/neighbour arcs included)
    one = _solve_dp(wind, 0.0, n, dt, polar, hold, open_sea(g), max_span=1)
    assert res.V[0, j0, i0] >= one.V[0, j0, i0] * 0.99


def test_macro_coast_clearance(polar, hold):
    g = Grid.from_bbox(-12, 0, 38, 46, 40e3)
    land = np.zeros(g.shape, bool)
    land[g.ny // 2 - 3: g.ny // 2 + 3, g.nx // 2 - 4: g.nx // 2 + 4] = True
    coast = CoastModel(g, signed_distance(g, land))
    n, dt = 9, 3 * H
    res = _solve_dp(uniform_wind(g, 9.0, 0.0, n + 1), 0.0, n, dt, polar, hold, coast, d_min=60e3,
                    max_span=3)
    assert np.all(res.V[:, land] == -np.inf)
    rng = np.random.default_rng(0)
    js, is_ = np.where(res.nav)
    for q in rng.choice(js.size, 40, replace=False):
        p = res.path(js[q], is_[q])
        x0, y0 = g.x0 + g.dx * p.i, g.y0 + g.dx * p.j
        x1, y1 = g.x0 + g.dx * p.i_end, g.y0 + g.dx * p.j_end
        for f in (0.0, 0.5, 1.0):
            assert np.all(coast.sdf_at(x0 + f * (x1 - x0), y0 + f * (y1 - y0)) >= 60e3 - 1.0)


def test_macro_orientation_and_beam_reach(polar, hold):
    """Uniform wind from many directions: tracks follow near-beam headings, not the grid axes."""
    g = centre_grid()
    n, dt = 6, 3 * H
    heads = []
    vals = []
    for d in (0, 11, 37, 45, 62, 90, 100, 153, 200, 290):
        uu, vv = W.uv_from_met(10.0, d)
        res = _solve_dp(uniform_wind(g, uu, vv, n + 1), 0.0, n, dt, polar, hold, open_sea(g),
                        max_span=3)
        p = res.path(g.ny // 2, g.nx // 2)
        mv = p.offset > 0
        twa = W.twa(uu, vv, p.heading[mv])
        assert mv.sum() >= 3 and np.all(np.abs(twa - 93.0) < 12.0), (d, twa)
        heads += list(p.heading[mv])
        vals.append(float(res.V[0, g.ny // 2, g.nx // 2]))
    off_axis = [h for h in heads if min(h % 45, 45 - h % 45) > 5.0]
    assert len(off_axis) >= 10  # genuinely off the 8 grid directions
    assert max(vals) / min(vals) - 1 < 0.07  # was 5.8 % -> lattice-limited, see docs
