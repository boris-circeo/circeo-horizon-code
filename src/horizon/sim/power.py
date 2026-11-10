"""Power models used by the simulator to value energy on the TRUE wind (DES-860 §8.1).

All models are vectorised: ``power_kw(u, v, ve, vn)`` with ``u, v`` the true wind components
("toward", CONVENTIONS §2) [m/s] and ``ve, vn`` the ship ground velocity (east, north) [m/s].
Leeway and current are ignored in S1, consistently with the DP.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numba import njit

from horizon.core import wind as W
from horizon.polar.derived import HoldCurve
from horizon.polar.envelope import EnvelopeTable, envelope_lookup
from horizon.polar.table import PolarTable

__all__ = ["PowerModel", "DirectPowerModel", "EnvelopePowerModel"]

HOLD_SPEED_MS = 0.5  # [m/s] below this ground speed the ship is considered to hold position


@runtime_checkable
class PowerModel(Protocol):
    """Mean net power [kW] for a ship moving at ground velocity ``(ve, vn)`` in wind ``(u, v)``."""

    def power_kw(self, u, v, ve, vn) -> np.ndarray:
        """Power [kW]; all arguments [m/s], broadcast together."""
        ...


class DirectPowerModel:
    """Single-heading polar at the heading/speed of the ground velocity.

    Below ``HOLD_SPEED_MS`` the station-keeping curve is used (DES-860 §6.6.1).

    Parameters
    ----------
    polar : PolarTable
    hold_curve : HoldCurve
    """

    def __init__(self, polar: PolarTable, hold_curve: HoldCurve):
        self.polar = polar
        self.hold = hold_curve

    def power_kw(self, u, v, ve, vn) -> np.ndarray:
        u, v, ve, vn = np.broadcast_arrays(*(np.asarray(a, float) for a in (u, v, ve, vn)))
        tws = np.hypot(u, v)
        spd = np.hypot(ve, vn)
        psi = np.degrees(np.arctan2(ve, vn))
        p = np.asarray(self.polar(tws, W.twa(u, v, psi), spd), dtype=float)
        p_hold = np.interp(tws, self.hold.tws, self.hold.p_hold)
        return np.where(spd < HOLD_SPEED_MS, p_hold, p)[()]


@njit(cache=True)
def _env_many(tab, ax, tws, vpar, vperp, out):  # pragma: no cover - jitted
    for k in range(tws.size):
        out[k] = envelope_lookup(tab, ax, tws[k], vpar[k], vperp[k])


class EnvelopePowerModel:
    """Upper-concave velocity-space envelope, i.e. exactly the DP's arc reward (incl. hold).

    Velocities outside the envelope's hull (not reachable by any heading/speed pair, e.g. fast
    motion upwind) are valued by ``fallback`` (single-heading polar) if given, else NaN.

    Parameters
    ----------
    envelope : EnvelopeTable
    fallback : PowerModel, optional
    """

    def __init__(self, envelope: EnvelopeTable, fallback: PowerModel | None = None):
        self.env = envelope
        self.fallback = fallback

    def envelope_kw(self, u, v, ve, vn) -> np.ndarray:
        """Envelope power [kW], NaN where the velocity is infeasible."""
        u, v, ve, vn = np.broadcast_arrays(*(np.asarray(a, float) for a in (u, v, ve, vn)))
        shp = u.shape
        tws = np.hypot(u, v).ravel()
        ve, vn, u, v = ve.ravel(), vn.ravel(), u.ravel(), v.ravel()
        ok = tws > 0
        sp = np.where(ok, tws, 1.0)
        vpar = np.where(ok, -(ve * u + vn * v) / sp, ve)
        vperp = np.where(ok, (ve * v - vn * u) / sp, vn)
        out = np.empty(tws.size)
        _env_many(self.env.reward, self.env.axes, np.ascontiguousarray(tws),
                  np.ascontiguousarray(vpar), np.ascontiguousarray(vperp), out)
        return out.reshape(shp)[()]

    def power_kw(self, u, v, ve, vn) -> np.ndarray:
        p = np.asarray(self.envelope_kw(u, v, ve, vn), dtype=float)
        if self.fallback is not None and np.isnan(p).any():
            p = np.where(np.isnan(p), self.fallback.power_kw(u, v, ve, vn), p)
        return p[()]
