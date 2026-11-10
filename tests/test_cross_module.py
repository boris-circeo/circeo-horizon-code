"""Cross-module convention tests (core.wind x core.kinematics x polar), docs/CONVENTIONS.md."""

import numpy as np
import pytest

from horizon.core import kinematics as K
from horizon.core import wind as W
from horizon.core.units import KNOT
from horizon.polar import (
    arc_reward_lookup,
    arc_reward_table,
    hold_power_curve,
    synthetic_polar,
)
from horizon.polar import table as table_mod


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


def test_knot_single_definition():
    from horizon.core import units

    assert table_mod.KNOT is units.KNOT or table_mod.KNOT == units.KNOT == 1852.0 / 3600.0
    assert KNOT == 1852.0 / 3600.0


def test_westerly_wind_heading_north_is_beam_reach_near_optimal(polar):
    tws = 20 * KNOT
    u, v = W.uv_from_met(tws, 270.0)  # wind FROM the west
    assert u > 0 and abs(v) < 1e-12  # blows toward the east
    th = W.twa(u, v, 0.0)  # ship heading north
    assert th == pytest.approx(90.0)
    assert W.twa_signed(u, v, 0.0) == pytest.approx(-90.0)  # wind from port
    assert W.tack(u, v, 0.0) == -1
    p = polar(tws, th, 3.75)
    best = max(polar(tws, a, s) for a in polar.twa for s in polar.u)
    assert p > 0.9 * best and p > 1500.0
    assert polar(tws, W.twa_signed(u, v, 0.0), 3.75) == pytest.approx(p, rel=1e-9)


def test_heading_into_wind_gets_low_negative_power(polar):
    tws = 20 * KNOT
    u, v = W.uv_from_met(tws, 270.0)
    assert W.twa(u, v, 270.0) == pytest.approx(0.0)  # steering into the wind
    assert W.twa(u, v, 90.0) == pytest.approx(180.0)  # running downwind
    head = polar(tws, W.twa(u, v, 270.0), 10.0)  # fast, head to wind: drag only
    beam = polar(tws, W.twa(u, v, 0.0), 3.75)
    assert head < 0.0 < beam
    assert polar(tws, W.twa(u, v, 270.0), 5.0) < 0.1 * beam  # at any speed, far below beam
    assert head > -500.0


@pytest.mark.parametrize("dir_from", [0.0, 37.0, 135.0, 270.0, 359.0])
def test_heading_for_twa_roundtrip_through_polar(polar, dir_from):
    u, v = W.uv_from_met(15 * KNOT, dir_from)
    for tk in (+1, -1):
        psi = W.heading_for_twa(u, v, 93.0, tk)
        assert W.twa(u, v, psi) == pytest.approx(93.0)
        assert W.tack(u, v, psi) == tk
        assert polar(15 * KNOT, W.twa_signed(u, v, psi), 3.75) == pytest.approx(
            polar(15 * KNOT, 93.0, 3.75)
        )


def test_leeway_pushes_downwind_side_consistent_with_tack():
    u, v = W.uv_from_met(10.0, 30.0)
    for psi in (50.0, 200.0, 310.0):
        le, ln = K.leeway_vector(psi, u, v)
        assert le * u + ln * v >= -1e-12  # never against the wind
        # leeway is on the side opposite to where the wind comes from: wind from starboard
        # (tack +1) pushes the ship to port, i.e. negative starboard component
        stbd = le * np.cos(np.radians(psi)) - ln * np.sin(np.radians(psi))
        assert np.sign(stbd) == -W.tack(u, v, psi) or abs(stbd) < 1e-12


def test_hold_curve_matches_kinematic_drift_and_beam_optimum(polar):
    h = hold_power_curve(polar)
    for i in (10, 20, 30):
        w, uu = polar.tws[i], float(h.u_star[i])
        uw, vw = W.uv_from_met(w, 0.0)
        vn = 0.0
        for tk in (+1, -1):
            psi = W.heading_for_twa(uw, vw, float(h.twa_b[i]), tk)
            vn += 0.5 * K.ground_velocity(uu, psi, uw, vw)[1]
        assert abs(vn) < 0.02  # hold TWA bias is consistent with core.kinematics
        assert h.twa_b[i] == pytest.approx(K.station_keeping_twa(uu, w), abs=1e-3)
    # uniform wind, no leeway: analytic beam reach
    h0 = hold_power_curve(polar, k_leeway=0.0)
    np.testing.assert_allclose(h0.twa_b[5:], 90.0, atol=1e-4)
    fa = h0.f_avail
    # p_hold = fa * max_U P(90deg) over U >= u_min, bounded by the beam optimum
    assert np.all(h0.p_hold <= fa * h0.p_beam + 1e-3)


@pytest.mark.physics
def test_power_sanity_range_over_full_table_and_interpolated(polar):
    assert polar.p.min() >= -500.0 and polar.p.max() <= 3000.0
    rng = np.random.default_rng(3)
    n = 20000
    p = polar(rng.uniform(0, 50 * KNOT, n), rng.uniform(-180, 180, n), rng.uniform(0, 10, n))
    assert p.min() >= -500.0 and p.max() <= 3000.0
    # no generation above cut-out (42 kn): only drag remains
    assert polar(50 * KNOT, 90.0, 3.75) < 0.0


@pytest.mark.physics
def test_port_starboard_symmetry_whole_table(polar):
    rng = np.random.default_rng(4)
    w, a, s = rng.uniform(0, 25, 500), rng.uniform(0, 180, 500), rng.uniform(0, 10, 500)
    np.testing.assert_array_equal(polar(w, a, s), polar(w, -a, s))


def test_arc_reward_lookup_edge_cases(polar):
    t = arc_reward_table(polar, [0.0, 3.75])
    args = (t.r, polar.tws[0], polar.d_tws, polar.twa[0], polar.d_twa)
    assert np.isnan(arc_reward_lookup(*args, np.nan, 90.0, 1))
    assert np.isnan(arc_reward_lookup(*args, 10.0, np.nan, 1))
    assert np.isnan(arc_reward_lookup(*args, np.inf, 90.0, 1))  # same as PolarTable
    assert np.isnan(arc_reward_lookup(*args, 10.0, 90.0, 2))  # k out of range
    assert np.isnan(arc_reward_lookup(*args, 10.0, 90.0, -1))
    # clamped outside the table, agrees with PolarTable at the bounds and the last TWA node
    assert arc_reward_lookup(*args, 1e3, 1e3, 1) == pytest.approx(t.r[-1, -1, 1])
    assert arc_reward_lookup(*args, -5.0, 0.0, 1) == pytest.approx(t.r[0, 0, 1])
    # exact node and polar agreement at a speed that is a table node
    w = polar.tws[17]
    assert arc_reward_lookup(*args, w, 180.0, 1) == pytest.approx(polar(w, 180.0, 3.75), rel=1e-6)


def test_coast_asset_is_packaged_and_loadable():
    from horizon.geo.coast import _ASSET_DIR, build_basin_coast

    assert list(_ASSET_DIR.glob("*.npz"))
    m = build_basin_coast()  # served from the committed asset
    assert m.sdf.dtype == np.float32 and np.isfinite(m.sdf).all()
