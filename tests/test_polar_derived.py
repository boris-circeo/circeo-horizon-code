"""Tests for horizon.polar.derived."""

import numpy as np
import pytest

from horizon.polar import (
    arc_reward_lookup,
    arc_reward_table,
    f_avail,
    hold_power_curve,
    softplus_cap,
    synthetic_polar,
)


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


def test_softplus_cap():
    x = np.array([-400.0, 0.0, 1500.0, 3000.0, 6000.0])
    y = softplus_cap(x)
    assert np.all(y <= 3000.0)
    assert y[3] < 3000.0
    assert y[0] == pytest.approx(-400.0, abs=1e-6)
    assert y[2] == pytest.approx(1500.0, abs=1e-6)
    assert y[3] == pytest.approx(3000 - np.log(2) / 0.02)
    assert y[4] == pytest.approx(3000.0, abs=1e-6)
    assert np.all(np.diff(softplus_cap(np.linspace(0, 8000, 400))) >= 0)
    assert np.isfinite(softplus_cap(-1e9))
    # smaller beta -> smoother, larger deviation; larger beta -> closer to min()
    assert abs(softplus_cap(3000.0, beta=0.1) - 3000) < abs(softplus_cap(3000.0, beta=0.01) - 3000)


def test_arc_reward_table(polar):
    speeds = [0.0, 2.5, 3.75, 6.0]
    t = arc_reward_table(polar, speeds)
    assert t.r.shape == (51, 73, 4) and t.r.dtype == np.float32
    np.testing.assert_allclose(t.r[20, 36, 2], polar.p[20, 36, 15], rtol=1e-6)  # U=3.75 node
    assert t.r[20, 36, 2] == pytest.approx(polar(polar.tws[20], 90.0, 3.75), rel=1e-6)
    assert np.abs(t.r[:, :, 0]).max() < 1e-3  # U = 0: nothing
    tws0, dt, twa0, da = polar.tws[0], polar.d_tws, polar.twa[0], polar.d_twa
    assert arc_reward_lookup(t.r, tws0, dt, twa0, da, polar.tws[20], 90.0, 2) == pytest.approx(
        t.r[20, 36, 2], rel=1e-6
    )
    mid = arc_reward_lookup(t.r, tws0, dt, twa0, da, polar.tws[20], -91.25, 2)
    assert mid == pytest.approx(0.5 * (t.r[20, 36, 2] + t.r[20, 37, 2]), rel=1e-5)
    with pytest.raises(ValueError):
        arc_reward_table(polar, [])


def test_f_avail_matches_spec_orders_of_magnitude():
    # tau_m = 4 min, rho_m = 0.3: 15 / 30 / 60 min legs -> about -15 / -8 / -4.4 %
    assert 1 - f_avail(900, 240, 0.3) == pytest.approx(0.145, abs=0.01)
    assert 1 - f_avail(1800, 240, 0.3) == pytest.approx(0.082, abs=0.005)
    assert 1 - f_avail(3600, 240, 0.3) == pytest.approx(0.044, abs=0.005)
    assert f_avail(1800, 240, 1.0) == 1.0
    with pytest.raises(ValueError):
        f_avail(0, 240, 0.3)


def test_hold_curve_geometry_and_units(polar):
    h = hold_power_curve(polar)
    assert h.p_hold.shape == polar.tws.shape and h.p_hold.dtype == np.float32
    assert h.p_hold.max() < 3000 and h.p_hold.min() >= -1.0
    i = 20
    assert 75 <= h.twa_b[i] < 90  # biased to windward of beam reach
    assert 3.0 <= h.u_star[i] <= 4.5
    # zero mean ground velocity along the wind axis, from the drift-compensation geometry
    th, w, u = np.radians(h.twa_b[i]), polar.tws[i], h.u_star[i]
    drift = u * np.cos(th) - 0.03 * w * np.sin(th)
    assert abs(drift) < 0.02  # < 0.04 kn, grid roundoff only (float32 angle)
    # no leeway -> exactly beam reach
    h0 = hold_power_curve(polar, k_leeway=1e-9)
    assert h0.twa_b[i] == pytest.approx(90.0, abs=1e-2)


@pytest.mark.parametrize("tau", [120.0, 240.0, 360.0])
@pytest.mark.parametrize("rho", [0.0, 0.3, 0.5])
@pytest.mark.parametrize("t_leg", [1800.0, 2700.0, 3600.0])
def test_hold_curve_5_to_15_percent_below_beam_optimum(polar, tau, rho, t_leg):
    h = hold_power_curve(polar, tau, rho, t_leg)
    sel = slice(15, 36)  # 15-35 kn: productive band
    ratio = h.p_hold[sel] / h.p_beam[sel]
    fa = f_avail(t_leg, tau, rho)
    # loss = manoeuvre overhead (1 - fa) + small bias/offset-from-optimum loss
    assert np.all(ratio <= fa + 0.02)
    assert np.all(ratio >= fa - 0.09)
    if (tau, rho) == (240.0, 0.3):  # nominal: 5-15 % below the raw beam-reach optimum
        core = h.p_hold[18:27] / h.p_beam[18:27]  # 18-26 kn core band
        assert 0.85 <= core.min() and core.max() <= 0.96


def test_hold_curve_monotone_with_leg_duration(polar):
    short = hold_power_curve(polar, t_leg_s=1800.0).p_hold
    long = hold_power_curve(polar, t_leg_s=3600.0).p_hold
    assert np.all(long >= short - 0.1)
