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
    assert np.allclose(np.hypot(le, ln), 0.04 * np.hypot(u, v))
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
    # leeway flips side when the wind is exactly along the heading, so a few draws have no
    # solution (NaN); the rest must be exact.
    ok = ~np.isnan(psi)
    assert ok.mean() > 0.95
    back = K.ground_course(5.0, psi[ok], u[ok], v[ok], cu[ok], cv[ok])
    assert np.allclose(wrap180(back - cog[ok]), 0.0, atol=1e-6)


def test_drift_compensated_heading_no_solution_is_nan():
    psi = K.drift_compensated_heading(0.0, 1.0, 0.0, 0.0, cur_u=3.0)
    assert np.isnan(psi)
