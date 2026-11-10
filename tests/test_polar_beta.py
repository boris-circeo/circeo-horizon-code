"""Tests of the real (BETA) polar loader. Client data are confidential: tests skip if absent."""

import glob
from pathlib import Path

import numpy as np
import pytest

from horizon.core.units import KNOT
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.beta import apply_operational_limits, load_beta_polar, read_beta_file
from horizon.polar.climatology import (
    climatological_hold_power,
    hold_power_vs_tws,
    terminal_value,
)
from horizon.polar.envelope import build_envelope
from horizon.polar.table import PolarTable
from horizon.weather.fields import WindField

DATA = Path("/home/claude/circeo-horizon-data/power-polar")
needs_data = pytest.mark.skipif(not DATA.is_dir(), reason="client BETA polar data not available")
FILES = sorted(glob.glob(str(DATA / "polar_BETA_TWS=*.csv")))


@pytest.fixture(scope="module")
def beta():
    return load_beta_polar(DATA)


@pytest.fixture(scope="module")
def env_beta(beta):
    return build_envelope(beta)


@needs_data
@pytest.mark.parametrize("path", FILES)
def test_psi_is_twa_from_apparent_wind_consistency(path):
    """Psi = TWA (0 = head to wind): AWS/AWA obey the apparent-wind formula with TWA = Psi."""
    d = read_beta_file(path)
    tws = d["tws_kn"] * KNOT
    psi = np.radians(d["psi_deg"])[:, None]
    u = d["u"][None, :]
    aws = np.sqrt(tws**2 + u**2 + 2 * tws * u * np.cos(psi))
    np.testing.assert_allclose(d["aws"], aws, atol=2e-3)
    # reported AWA = direction the apparent wind blows towards, relative to the bow
    awa_std = np.degrees(np.arctan2(tws * np.sin(psi), tws * np.cos(psi) + u))
    np.testing.assert_allclose(np.abs(d["awa"]), 180.0 - awa_std, atol=0.05)
    # the alternative reading TWA = 180 - Psi is inconsistent
    alt = np.sqrt(tws**2 + u**2 - 2 * tws * u * np.cos(psi))
    assert np.abs(d["aws"] - alt).max() > 0.5
    # head to wind AWS = TWS + U; downwind AWS = TWS - U
    np.testing.assert_allclose(d["aws"][0], tws + d["u"], atol=2e-3)
    np.testing.assert_allclose(d["aws"][-1], np.abs(tws - d["u"]), atol=2e-3)


@needs_data
def test_regrid_exact_at_native_nodes():
    raw = read_beta_file(DATA / Path(FILES[5]).name)  # 20 kn
    assert raw["tws_kn"] == 20
    t = load_beta_polar(DATA, tws_kn=[20, 22], twa=raw["psi_deg"], u=raw["u"], repair_holes=False)
    got = t.p[0]
    want = raw["power"]
    assert np.array_equal(np.isnan(got), np.isnan(want))
    ok = ~np.isnan(want)
    np.testing.assert_allclose(got[ok], want[ok], rtol=1e-6, atol=1e-3)
    np.testing.assert_array_equal(t.feasible[0], ok)


@needs_data
def test_feasibility_mask_and_limits(beta):
    assert np.array_equal(beta.feasible, np.isfinite(beta.p))
    assert not beta.feasible[:, :, beta.u > 8.0 + 1e-9].any()
    assert beta.feasible.any() and (~beta.feasible).any()
    # query touching an infeasible node is NaN, never a fake number
    i, j, k = np.argwhere(~beta.feasible & (beta.u[None, None, :] < 8.0))[0]
    assert np.isnan(beta(beta.tws[i], beta.twa[j], beta.u[k]))
    # exactly on a node next to an infeasible one is still finite
    ok = np.argwhere(beta.feasible[20])[0]
    assert np.isfinite(beta(beta.tws[20], beta.twa[ok[0]], beta.u[ok[1]]))
    lo, hi = np.nanmin(beta.p), np.nanmax(beta.p)
    assert -3100 < lo < -2500 and 2900 < hi <= 3000
    assert beta.meta["params"]["Wind Turbine - Diameter of turbine [m]"] == 84
    assert beta.meta["n_repaired"] == 0


@needs_data
def test_peak_locations(beta, capsys):
    rep = []
    for kn in (10, 14, 20, 24, 30, 50):
        p = beta.p[kn]
        i, j = np.unravel_index(np.nanargmax(p), p.shape)
        rep.append((kn, float(p[i, j]), float(beta.twa[i]), float(beta.u[j])))
    with capsys.disabled():
        print("\n[BETA peak] (TWS kn, Pmax kW, TWA deg, U m/s):", rep)
    by = {r[0]: r for r in rep}
    for kn in (10, 14, 20):  # light/moderate: beam-ish reach at U 1.5-3.5
        assert 80 <= by[kn][2] <= 100 and 1.5 <= by[kn][3] <= 4.0
    for kn in (24, 30, 50):  # strong wind: stopped (U ~ 0), dead downwind, ~3 MW
        assert by[kn][2] >= 170 and by[kn][3] <= 0.25 and by[kn][1] > 2950
    # no cut-out in the data
    assert np.nanmax(beta.p[50]) > 2900


@needs_data
def test_below_10kn_extrapolation(beta):
    p6, f6 = beta.p[6], beta.feasible[6]
    assert np.mean(p6[f6] > 0) < 0.05
    assert np.nanmax(p6) <= 30.0
    assert np.nanmax(beta.p[0]) <= 1e-3
    assert np.nanmin(beta.p[0]) < -2000  # consumption kept
    np.testing.assert_allclose(beta.p[10], load_beta_polar(DATA).p[10], equal_nan=True)
    # continuity to the first file: 9 kn is between 6 kn and 10 kn maxima
    assert np.nanmax(beta.p[6]) <= np.nanmax(beta.p[9]) <= np.nanmax(beta.p[10]) + 1e-3


@needs_data
def test_operational_overlay(beta):
    same = apply_operational_limits(beta)
    np.testing.assert_array_equal(same.p, beta.p)
    ov = apply_operational_limits(beta, 25, 35, mode="derate_cutout")
    np.testing.assert_array_equal(ov.p[:25], beta.p[:25])  # below derating start
    assert np.nanmax(ov.p[30]) < np.nanmax(beta.p[30])
    for kn in (35, 40, 50):  # cut-out: negative (consumption), not zero
        assert np.nanmax(ov.p[kn]) <= 1e-3 and np.nanmin(ov.p[kn]) < -2000
    neg = beta.p < 0
    np.testing.assert_allclose(ov.p[neg], beta.p[neg], atol=1e-3)
    with pytest.raises(ValueError):
        apply_operational_limits(beta, mode="bogus")


@needs_data
def test_envelope_above_direct_and_hold(beta, env_beta):
    env = env_beta
    ok = np.isfinite(env.direct)
    assert np.all(env.e[ok] >= env.direct[ok] - 1e-3)
    ip = int(round(-env.vp0 / env.dv))
    tws, p0 = hold_power_vs_tws(env)
    h = hold_power_curve(beta, include_stopped=True)
    # envelope(0) captures every single hold mode (tack alternation, stopped ship)
    good = np.isfinite(p0)
    assert np.all(p0[good] >= h.p_hold[good] - 1.0)
    # strong wind: stopped downwind is the best hold (up to isolated data holes)
    stopped = [kn for kn in range(8, 51) if h.u_star[kn] == 0.0 and h.twa_b[kn] == 180.0]
    assert len(stopped) >= 30
    for kn in (22, 24, 26, 40, 50):
        assert h.u_star[kn] == 0.0 and abs(p0[kn] - h.p_hold[kn]) < 1.0
    assert np.all(env.e[:, ip, 0][good] <= 3000.0 + 1.0)
    # without stopped modes the tack-alternation hold is not better
    h0 = hold_power_curve(beta)
    assert np.all(h0.p_hold[good] <= p0[good] + 1.0)


def test_nan_does_not_leak_on_nodes():
    tws = np.arange(3) * 1.0
    twa = np.arange(0, 91, 45.0)
    u = np.arange(3) * 1.0
    p = np.zeros((3, 3, 3))
    feas = np.ones(p.shape, bool)
    feas[1, 1, 2] = False
    t = PolarTable(p, tws, twa, u, feasible=feas)
    assert t(1.0, 45.0, 1.0) == 0.0  # node next to the hole
    assert np.isnan(t(1.0, 45.0, 1.5))
    assert np.isnan(t(1.0, 45.0, 2.0))
    p_dag, u_dag = t.reduced()
    assert np.isfinite(p_dag).all()


def test_synthetic_unchanged_hold_flags():
    s = synthetic_polar()
    assert s.feasible.all()
    h = hold_power_curve(s)
    h2 = hold_power_curve(s, include_stopped=False)
    np.testing.assert_array_equal(h.p_hold, h2.p_hold)


def _uniform_field(speed_ms: float, hours: int = 3) -> WindField:
    grid = Grid.from_bbox(-10.0, -5.0, 40.0, 44.0, 100_000.0)
    uv = np.zeros((hours, grid.ny, grid.nx, 2), dtype=np.float32)
    uv[..., 0] = speed_ms
    return WindField(grid, np.datetime64("2024-01-01T00:00:00"),
                     np.arange(hours) * 3600.0, uv)


def test_climatology_on_synthetic_field():
    env = build_envelope(synthetic_polar())
    tws, p0 = hold_power_vs_tws(env)
    w = 12.0 * KNOT
    f = _uniform_field(w)
    pc = climatological_hold_power(f, env)
    assert pc.shape == (f.grid.ny, f.grid.nx)
    np.testing.assert_allclose(pc, np.interp(w, tws, p0), rtol=1e-4)
    assert float(pc[0, 0]) > 0
    # two archives with different winds: equal-weight mean over hours
    f2 = _uniform_field(18.0 * KNOT, hours=1)
    pm = climatological_hold_power([f, f2], env)
    exp = (3 * np.interp(w, tws, p0) + np.interp(18.0 * KNOT, tws, p0)) / 4
    np.testing.assert_allclose(pm, exp, rtol=1e-4)
    v = terminal_value(pc, 24.0)
    np.testing.assert_allclose(v, pc * 24.0, rtol=1e-6)
    assert v.dtype == np.float32
    with pytest.raises(ValueError):
        terminal_value(pc, -1.0)


@needs_data
def test_climatology_with_beta_calm_negative_or_zero(env_beta):
    pc = climatological_hold_power(_uniform_field(3.0 * KNOT), env_beta)
    assert float(pc.max()) <= 1e-3
