import numpy as np
import pytest

from horizon.core import wind as W
from horizon.core.units import wrap180

RNG = np.random.default_rng(12345)


def test_uv_from_north():
    u, v = W.uv_from_met(10.0, 0.0)
    assert u == pytest.approx(0.0, abs=1e-12) and v == pytest.approx(-10.0)


@pytest.mark.parametrize("d,exp", [(90, (-10, 0)), (180, (0, 10)), (270, (10, 0))])
def test_uv_cardinals(d, exp):
    u, v = W.uv_from_met(10.0, d)
    assert (u, v) == pytest.approx(exp, abs=1e-9)


def test_met_roundtrip_random_and_wrap():
    d = np.concatenate([RNG.uniform(0, 360, 500), [0.0, 0.1, 359.9, 180.0, 90.0]])
    s = RNG.uniform(0.1, 30, d.size)
    u, v = W.uv_from_met(s, d)
    s2, d2 = W.met_from_uv(u, v)
    assert np.allclose(s2, s)
    assert np.allclose(wrap180(d2 - d), 0.0, atol=1e-9)
    assert np.all((d2 >= 0) & (d2 < 360))


def test_wrap_discontinuity_359_0():
    for d in (359.9, 0.1):
        u, v = W.uv_from_met(10.0, d)
        assert v == pytest.approx(-10.0, abs=1e-4)
    _, d = W.met_from_uv(*W.uv_from_met(10.0, 359.9))
    assert d == pytest.approx(359.9)
    # TWA identical on both sides of the discontinuity (heading 0)
    a = W.twa(*W.uv_from_met(10.0, 359.9), 0.0)
    b = W.twa(*W.uv_from_met(10.0, 0.1), 0.0)
    assert a == pytest.approx(0.1) and b == pytest.approx(0.1)
    assert W.twa_signed(*W.uv_from_met(10.0, 359.9), 0.0) == pytest.approx(-0.1)
    assert W.twa_signed(*W.uv_from_met(10.0, 0.1), 0.0) == pytest.approx(0.1)
    # heading across the discontinuity
    assert W.twa(0.0, -10.0, 359.9) == pytest.approx(0.1)
    assert W.twa(0.0, -10.0, 0.1) == pytest.approx(0.1)


def test_met_zero_wind():
    assert W.met_from_uv(0.0, 0.0) == (0.0, 0.0)
    assert W.met_from_uv(-0.0, -0.0) == (0.0, 0.0)


def test_tws():
    assert W.tws(3.0, 4.0) == 5.0


# wind FROM north: (0, -10)
@pytest.mark.parametrize(
    "psi,twa,signed,tk",
    [
        (0, 0, 0, 1),
        (90, 90, -90, -1),
        (180, 180, 180, 1),
        (270, 90, 90, 1),
        (45, 45, -45, -1),
        (315, 45, 45, 1),
    ],
)
def test_twa_wind_from_north(psi, twa, signed, tk):
    u, v = 0.0, -10.0
    assert W.twa(u, v, psi) == pytest.approx(twa, abs=1e-9)
    assert W.twa_signed(u, v, psi) == pytest.approx(signed, abs=1e-9)
    assert W.tack(u, v, psi) == tk


def test_twa_wind_from_east_heading_north_is_starboard():
    u, v = W.uv_from_met(10.0, 90.0)
    assert W.twa_signed(u, v, 0.0) == pytest.approx(90.0)
    assert W.tack(u, v, 0.0) == 1


def test_twa_zero_wind():
    assert W.twa(0.0, 0.0, 123.0) == 0.0
    assert W.twa_signed(0.0, 0.0, 123.0) == 0.0


def test_twa_vectorised_shapes():
    psi = np.linspace(0, 360, 7)[:, None]
    u = np.array([[0.0, 5.0, -5.0]])
    out = W.twa(u, np.zeros_like(u), psi)
    assert out.shape == (7, 3)
    assert np.all((out >= 0) & (out <= 180))


def test_property_twa_consistency_and_inverse():
    n = 2000
    s = RNG.uniform(0.5, 30, n)
    d = RNG.uniform(0, 360, n)
    psi = RNG.uniform(0, 360, n)
    u, v = W.uv_from_met(s, d)
    ts = W.twa_signed(u, v, psi)
    assert np.allclose(np.abs(ts), W.twa(u, v, psi), atol=1e-7)
    # analytic: signed TWA = wrap180(dir_from - heading)
    assert np.allclose(wrap180(ts - (d - psi)), 0.0, atol=1e-7)
    tk = W.tack(u, v, psi)
    assert np.all(np.sign(ts[np.abs(ts) > 1e-6]) == tk[np.abs(ts) > 1e-6])
    # heading_for_twa round trip
    psi2 = W.heading_for_twa(u, v, W.twa(u, v, psi), tk)
    assert np.allclose(wrap180(psi2 - psi), 0.0, atol=1e-6)
    assert np.all((psi2 >= 0) & (psi2 < 360))


def test_heading_for_twa_known():
    u, v = 0.0, -10.0  # from north
    assert W.heading_for_twa(u, v, 90.0, +1) == pytest.approx(270.0)
    assert W.heading_for_twa(u, v, 90.0, -1) == pytest.approx(90.0)
    assert W.heading_for_twa(u, v, 0.0, 1) == pytest.approx(0.0)
    assert W.heading_for_twa(u, v, 180.0, 1) == pytest.approx(180.0)


def test_apparent_wind_still_air():
    ua, va, aws, awa = W.apparent_wind(0.0, 0.0, 4.0, 0.0)
    assert (ua, va) == pytest.approx((0.0, -4.0), abs=1e-12)
    assert aws == pytest.approx(4.0)
    assert awa == pytest.approx(0.0)


def test_apparent_wind_beam():
    # ship 5 m/s east, true wind from north 10 m/s -> apparent from ahead-port
    ua, va, aws, awa = W.apparent_wind(0.0, -10.0, 5.0, 90.0)
    assert (ua, va) == pytest.approx((-5.0, -10.0))
    assert aws == pytest.approx(np.hypot(5, 10))
    assert awa == pytest.approx(90.0 - np.degrees(np.arctan2(5, 10)))
    assert awa < 90.0  # apparent wind moves forward


def test_apparent_wind_downwind():
    _, _, aws, awa = W.apparent_wind(0.0, 10.0, 4.0, 0.0)  # wind from south, heading north
    assert aws == pytest.approx(6.0) and awa == pytest.approx(180.0)


def test_interp_uv_time_numeric_and_datetime():
    uv0 = np.array([0.0, -10.0])
    uv1 = np.array([10.0, 0.0])
    assert np.allclose(W.interp_uv_time(5.0, 0.0, uv0, 10.0, uv1), [5.0, -5.0])
    t0 = np.datetime64("2025-01-01T00:00:00")
    t1 = np.datetime64("2025-01-01T06:00:00")
    t = np.datetime64("2025-01-01T03:00:00")
    assert np.allclose(W.interp_uv_time(t, t0, uv0, t1, uv1), [5.0, -5.0])
    # clipping
    assert np.allclose(W.interp_uv_time(-3.0, 0.0, uv0, 10.0, uv1), uv0)


def test_interp_uv_through_wrap_no_fictitious_wind():
    # from 350 deg to 10 deg at 10 m/s: midpoint must be a ~10 m/s northerly, not a southerly
    uv0 = np.array(W.uv_from_met(10.0, 350.0))
    uv1 = np.array(W.uv_from_met(10.0, 10.0))
    mid = W.interp_uv_time(0.5, 0.0, uv0, 1.0, uv1)
    _, d = W.met_from_uv(*mid)
    assert wrap180(d) == pytest.approx(0.0, abs=1e-9)
    assert np.hypot(*mid) > 9.8
