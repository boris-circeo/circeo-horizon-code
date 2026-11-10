import numpy as np
import pytest

from horizon.core import units as U


def test_knot_exact():
    assert U.KNOT == 1852 / 3600
    assert U.kn_to_ms(1.0) == pytest.approx(0.514444444, rel=1e-8)


def test_roundtrips():
    x = np.linspace(0, 50, 11)
    assert np.allclose(U.ms_to_kn(U.kn_to_ms(x)), x)
    assert np.allclose(U.m_to_nm(U.nm_to_m(x)), x)
    assert U.nm_to_m(1) == 1852.0


def test_energy():
    assert U.energy_kwh(3000.0, 1800.0) == pytest.approx(1500.0)
    assert U.mean_power_kw(1500.0, 1800.0) == pytest.approx(3000.0)


@pytest.mark.parametrize("a,exp", [(0, 0), (360, 0), (-0.1, 359.9), (720.5, 0.5), (-360, 0)])
def test_wrap360(a, exp):
    assert U.wrap360(a) == pytest.approx(exp)


def test_wrap360_tiny_negative_and_array():
    assert U.wrap360(-1e-20) < 360.0
    assert np.allclose(U.wrap360(np.array([-90.0, 450.0])), [270.0, 90.0])


@pytest.mark.parametrize(
    "a,exp", [(0, 0), (180, 180), (-180, 180), (190, -170), (359.9, -0.1), (-190, 170)]
)
def test_wrap180(a, exp):
    assert U.wrap180(a) == pytest.approx(exp)
