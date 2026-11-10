"""Tests of the velocity-space power envelope (DES-860 §6.1.1, §6.6.1)."""

import numpy as np
import pytest

from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope, envelope_lookup


@pytest.fixture(scope="module")
def env():
    return build_envelope(synthetic_polar())


def test_envelope_above_direct_and_reward(env):
    ok = np.isfinite(env.direct)
    assert np.all(env.e[ok] >= env.direct[ok] - 1e-3)
    assert np.all(env.reward[ok] >= env.direct[ok] - 1e-3)
    np.testing.assert_allclose(env.reward[ok], np.maximum(env.direct[ok], env.f_avail * env.e[ok]),
                               rtol=1e-5, atol=1e-3)
    assert np.all(np.isnan(env.e) == np.isnan(env.reward))


def test_envelope_concave(env):
    """E(midpoint) >= mean of E at two points, for random pairs on the feasible grid."""
    rng = np.random.default_rng(0)
    it = int(round(10.0 / env.dtws))
    e = env.e[it]
    ij = np.argwhere(np.isfinite(e))
    for _ in range(300):
        a, b = ij[rng.integers(len(ij), size=2)]
        if (a + b)[0] % 2 or (a + b)[1] % 2:
            continue
        m = (a + b) // 2
        assert e[tuple(m)] >= 0.5 * (e[tuple(a)] + e[tuple(b)]) - 1.0  # kW


def test_zero_velocity_matches_hold_curve(env):
    hold = hold_power_curve(synthetic_polar())
    ip = int(round(-env.vp0 / env.dv))
    for tws in (6.0, 10.0, 14.0, 18.0):
        it = int(round(tws / env.dtws))
        assert env.reward[it, ip, 0] == pytest.approx(hold.p_hold[it], rel=0.03, abs=1.0)


def test_lookup_symmetry_and_bounds(env):
    ax = env.axes
    a = envelope_lookup(env.reward, ax, 10.0, 0.3, 3.1)
    assert a == envelope_lookup(env.reward, ax, 10.0, 0.3, -3.1)
    assert np.isfinite(a) and a > 500.0
    assert np.isnan(envelope_lookup(env.reward, ax, 10.0, 99.0, 0.0))
    # beyond the velocity grid: infeasible
    assert np.isnan(envelope_lookup(env.reward, ax, 10.0, 10.5, 0.0))
