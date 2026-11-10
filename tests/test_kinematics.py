import numpy as np
import pytest

from horizon.core import kinematics as K
from horizon.core import wind as W
from horizon.core.units import wrap180

RNG = np.random.default_rng(7)


def test_leeway_east_heading_wind_from_north_pushes_south():
    le, ln = K.leeway_vector(90.0, 0.0, -10.0, 0.03)
    assert le == pytest.approx(0.0, abs=1e-12)
    assert ln == pytest.approx(-0.3)


def test_leeway_west_heading_wind_from_north_pushes_south():
    le, ln = K.leeway_vector(270.0, 0.0, -10.0, 0.03)
    assert (le, ln) == pytest.approx((0.0, -0.3), abs=1e-12)


def test_leeway_wind_from_east_heading_north_pushes_west():
    u, v = W.uv_from_met(10.0, 90.0)
    le, ln = K.leeway_vector(0.0, u, v)
    assert (le, ln) == pytest.approx((-0.3, 0.0), abs=1e-12)


def test_leeway_magnitude_and_perpendicular_property():
    n = 1000
    psi = RNG.uniform(0, 360, n)
    u, v = RNG.normal(0, 8, (2, n))
    le, ln = K.leeway_vector(psi, u, v, 0.04)
    sin_twa = np.sin(np.radians(W.twa(u, v, psi)))
    assert np.allclose(np.hypot(le, ln), 0.04 * np.hypot(u, v) * sin_twa)
    p = np.radians(psi)
    assert np.allclose(le * np.sin(p) + ln * np.cos(p), 0.0, atol=1e-12)  # perpendicular to heading
    assert np.all(le * u + ln * v >= -1e-12)  # leeward: never against the wind


def test_ground_velocity_components():
    ve, vn = K.ground_velocity(5.0, 90.0, 0.0, -10.0, cur_u=0.5, cur_v=0.25, k_leeway=0.03)
    assert ve == pytest.approx(5.5)
    assert vn == pytest.approx(0.25 - 0.3)


def test_ground_velocity_no_wind_no_current():
    ve, vn = K.ground_velocity(4.0, 30.0, 0.0, 0.0)
    assert (ve, vn) == pytest.approx((4.0 * np.sin(np.radians(30)), 4.0 * np.cos(np.radians(30))))


def test_ground_course_wrap():
    assert K.ground_course(5.0, 359.9, 0.0, 0.0) == pytest.approx(359.9)


def test_drift_compensated_heading_known_current():
    # current 1 m/s towards east, want to go north at 5 m/s: aim west of north
    psi = K.drift_compensated_heading(0.0, 5.0, 0.0, 0.0, cur_u=1.0)
    assert psi == pytest.approx(360.0 - np.degrees(np.arcsin(1 / 5)), abs=1e-6)


def test_drift_compensated_heading_property():
    n = 500
    cog = RNG.uniform(0, 360, n)
    u, v = RNG.normal(0, 8, (2, n))
    cu, cv = RNG.normal(0, 0.5, (2, n))
    psi = K.drift_compensated_heading(cog, 5.0, u, v, cu, cv)
    ok = ~np.isnan(psi)
    assert ok.all()  # smooth leeway: always solvable here (drift << ship speed)
    back = K.ground_course(5.0, psi[ok], u[ok], v[ok], cu[ok], cv[ok])
    assert np.allclose(wrap180(back - cog[ok]), 0.0, atol=1e-6)


def test_drift_compensated_heading_no_solution_is_nan():
    psi = K.drift_compensated_heading(0.0, 1.0, 0.0, 0.0, cur_u=3.0)
    assert np.isnan(psi)


def test_leeway_zero_head_and_downwind_and_continuous():
    for psi, dir_from in [(0.0, 0.0), (0.0, 180.0), (123.0, 123.0), (123.0, 303.0)]:
        u, v = W.uv_from_met(12.0, dir_from)
        assert K.leeway_vector(psi, u, v) == pytest.approx((0.0, 0.0), abs=1e-12)
    # regression: hard-sign normal jumped by 2 k_L |W| across wind-along-heading
    u, v = W.uv_from_met(10.0, 0.0)  # wind from north, heading north
    a = np.hypot(*K.leeway_vector(0.001, u, v))
    b = np.hypot(*K.leeway_vector(-0.001, u, v))
    assert a < 1e-3 and b < 1e-3
    # beam reach: full k_L |W|
    assert np.hypot(*K.leeway_vector(90.0, u, v)) == pytest.approx(0.3)


def test_leeway_is_c1_in_heading():
    u, v = W.uv_from_met(10.0, 40.0)
    h = 1e-4
    psi = np.linspace(0, 360, 721)
    fp = np.array([K.leeway_vector(p + h, u, v) for p in psi])
    fm = np.array([K.leeway_vector(p - h, u, v) for p in psi])
    assert np.abs(fp - fm).max() / (2 * h) < 1.0  # bounded derivative, no jump


def test_station_keeping_twa_zero_mean_drift():
    for u_, w_ in [(3.75, 10.3), (1.0, 20.0), (5.0, 0.0), (3.0, 3.0)]:
        th = K.station_keeping_twa(u_, w_, 0.03)
        # mean up-wind velocity of the ship built from the actual kinematics (both tacks)
        drift = 0.0
        for tk in (+1, -1):
            uw, vw = W.uv_from_met(w_, 0.0)  # wind from north
            psi = W.heading_for_twa(uw, vw, th, tk)
            ve, vn = K.ground_velocity(u_, psi, uw, vw, k_leeway=0.03)
            drift += vn / 2  # up-wind = +north
        assert drift == pytest.approx(0.0, abs=1e-9)
    assert K.station_keeping_twa(3.0, 20.0, 1e-12) == pytest.approx(90.0, abs=1e-6)
