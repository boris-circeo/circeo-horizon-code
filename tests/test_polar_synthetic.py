"""Calibration of the synthetic polar on the DES-860 §2.2.1 / §1.6 figures (tolerance ~10%)."""

import numpy as np
import pytest

from horizon.polar import SyntheticPolarParams, synthetic_polar
from horizon.polar.table import KNOT


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def red(polar):
    return polar.reduced()


def peak(polar, red, kn):
    pd, ud = red
    i = int(round(kn))
    j = int(np.argmax(pd[i]))
    return float(pd[i, j]), float(polar.twa[j]), float(ud[i, j])


@pytest.mark.parametrize(
    ("kn", "target", "lo", "hi"), [(18, 1500, 0.9, 1.1), (20, 2100, 0.9, 1.1), (22, 2700, 1.0, 1.2)]
)
def test_peak_power(polar, red, kn, target, lo, hi):
    p, _, _ = peak(polar, red, kn)
    assert lo * target <= p <= hi * target


@pytest.mark.parametrize("kn", [18, 20, 22])
def test_optimum_location(polar, red, kn):
    _, twa, u = peak(polar, red, kn)
    assert 75 <= twa <= 105
    assert 3.0 <= u <= 4.5


def test_cap_reached_and_never_exceeded(polar, red):
    assert polar.p.max() < 3000.0
    # client decision 2026-11-10: derating from 25 kn, cut-out at 35 kn
    assert peak(polar, red, 25)[0] >= 0.98 * 3000
    assert peak(polar, red, 24)[0] >= 0.95 * 3000
    assert peak(polar, red, 26)[0] >= 0.95 * 3000
    assert peak(polar, red, 35)[0] <= 1.0  # cut-out
    assert peak(polar, red, 22)[0] < 2950  # still below the knee plateau


def test_angular_sensitivity_at_20kn(polar, red):
    pd, _ = red
    ratio = pd[20, 18] / pd[20, 36]  # 45 deg vs 90 deg
    assert 1 / 4.4 <= ratio <= 1 / 2.7
    m = pd[20].max()
    j = int(np.argmax(pd[20]))
    band = polar.twa[pd[20] >= 0.5 * m]
    left, right = polar.twa[j] - band.min(), band.max() - polar.twa[j]
    assert 0.5 * (left + right) == pytest.approx(22.5, abs=4.5)
    assert 12 <= left <= 30 and 12 <= right <= 30


def test_negative_power_close_hauled_high_speed(polar):
    p = polar.p
    assert -500 <= p.min() <= -200  # about -300 kW at worst, never below -500
    ci = polar.twa < 30
    hi_u = polar.u >= 7.0
    sub = p[np.ix_(polar.tws > 15 * KNOT, ci, hi_u)]
    assert (sub < 0).mean() > 0.8
    assert p[:, polar.twa >= 60, :][:, :, polar.u <= 5].min() > -100  # no big loss at reach/low U


def test_low_wind_small(polar, red):
    pd, _ = red
    assert pd[:5].max() < 60  # TWS < 5 kn
    assert np.all(polar.p[0] <= 1e-3 + 0)  # no wind: no generation (drag only)


def test_high_wind_derating(polar, red):
    pd, _ = red
    assert pd[38].max() < pd[30].max()
    assert pd[42:].max() <= 1e-3
    assert pd[40].max() < 0.5 * 3000


def test_pdagger_monotone_below_knee(red):
    pd, _ = red
    m = pd.max(axis=1)
    assert np.all(np.diff(m[:25]) >= 0)


def test_units_and_params_effect(polar):
    assert polar.p.dtype == np.float32
    assert polar.tws[-1] == pytest.approx(50 * KNOT)
    small = synthetic_polar(SyntheticPolarParams(k_turb=1.0))
    assert small.p.max() < polar.p.max()


def test_close_hauled_net_power_never_positive():
    """DES-860 §2.2.1 item 4: net power is negative (or nil) close-hauled, TWA <= 30 deg."""
    import numpy as np

    from horizon.polar.synthetic import synthetic_polar

    pol = synthetic_polar()
    sel = pol.twa <= 30.0
    assert np.all(pol.p[:, sel, :] <= 1e-3)
    # and strictly negative once the ship actually moves
    assert np.all(pol.p[1:, sel, :][:, :, pol.u >= 1.0] < 0.0)
