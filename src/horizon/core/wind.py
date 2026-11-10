"""Wind vector maths. Single home of the "toward" <-> "from" conversion (docs/CONVENTIONS.md §2-3).

Wind is stored as ``(u, v)`` [m/s], components of the air motion towards east / north (ERA5 sense).
Meteorological direction is where the wind comes from, degrees clockwise from true north.
All functions accept scalars or broadcastable arrays.
"""

from __future__ import annotations

import numpy as np

from horizon.core.units import wrap180, wrap360

__all__ = [
    "uv_from_met", "met_from_uv", "tws", "twa", "twa_signed", "tack",
    "heading_for_twa", "apparent_wind", "interp_uv_time",
]


def uv_from_met(speed, dir_from_deg):
    """(u, v) [m/s] from speed [m/s] and meteorological "from" direction [deg cw from north]."""
    d = np.radians(dir_from_deg)
    return -speed * np.sin(d), -speed * np.cos(d)


def met_from_uv(u, v):
    """Meteorological "from" direction [deg, [0, 360)] and speed [m/s] of ``(u, v)`` [m/s].

    Returns ``(speed, dir_from_deg)``. Direction is 0 for zero wind.
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    spd = np.hypot(u, v)
    d = wrap360(np.degrees(np.arctan2(-u, -v)))
    d = np.where(spd == 0.0, 0.0, d)
    return (spd, d) if np.ndim(spd) else (float(spd), float(d))


def tws(u, v):
    """True wind speed [m/s] from components ``u, v`` [m/s]."""
    return np.hypot(u, v)


def _rel_components(u, v, heading_deg):
    """Components of the "from" vector (-W) along heading and starboard axes [m/s]."""
    p = np.radians(heading_deg)
    s, c = np.sin(p), np.cos(p)
    along = -(u * s + v * c)  # towards the bow
    stbd = -(u * c - v * s)   # towards the starboard side (right of heading = (cos, -sin))
    return along, stbd


def twa(u, v, heading_deg):
    """Unsigned true wind angle [deg, [0, 180]]: heading vs. wind "from" direction.

    ``TWA = arccos(-(W . e_psi) / |W|)``; 0 = head to wind, 180 = dead downwind
    (DES-860 §2.2.6, corrected by 180 deg, see docs/CONVENTIONS.md §3).
    Zero wind: returns 0 (power is zero there anyway).
    """
    along, stbd = _rel_components(u, v, heading_deg)
    w = np.hypot(along, stbd)
    cosa = np.divide(along, w, out=np.ones(np.shape(w)), where=w > 0)
    out = np.degrees(np.arccos(np.clip(cosa, -1.0, 1.0)))
    return out if np.ndim(out) else float(out)


def twa_signed(u, v, heading_deg):
    """Signed TWA [deg, (-180, 180]]; positive = wind from starboard (right-hand side).

    Zero wind: returns 0.
    """
    along, stbd = _rel_components(u, v, heading_deg)
    out = wrap180(np.degrees(np.arctan2(stbd, along)))
    return np.where(np.hypot(along, stbd) == 0.0, 0.0, out) if np.ndim(out) else (
        0.0 if along == 0.0 and stbd == 0.0 else out)


def tack(u, v, heading_deg):
    """Tack: +1 wind from starboard, -1 wind from port. Dead head/downwind (|signed TWA| 0 or 180)
    is ambiguous; ``signed >= 0`` gives +1 (numerical noise may flip it there)."""
    return np.where(np.asarray(twa_signed(u, v, heading_deg)) < 0.0, -1, 1)


def heading_for_twa(u, v, twa_deg, tack_):
    """Heading [deg, [0, 360)] giving unsigned TWA ``twa_deg`` [deg] on tack ``tack_`` (+1/-1).

    Inverse of :func:`twa` / :func:`tack`: ``heading = dir_from - tack * TWA``.
    Zero wind: the "from" direction is taken as 0 (north).
    """
    _, d = met_from_uv(u, v)
    return wrap360(d - np.asarray(tack_) * np.asarray(twa_deg, dtype=float))


def apparent_wind(u, v, ship_speed, heading_deg):
    """Apparent wind seen from a moving ship (through-water motion, no current).

    Parameters
    ----------
    u, v : float or ndarray  [m/s]  true wind "toward" components.
    ship_speed : float or ndarray  [m/s]
    heading_deg : float or ndarray  [deg]

    Returns
    -------
    u_a, v_a : [m/s] ``W - U e_psi``; aws : [m/s] apparent wind speed; awa : [deg, [0, 180]].
    """
    p = np.radians(heading_deg)
    ua = u - ship_speed * np.sin(p)
    va = v - ship_speed * np.cos(p)
    return ua, va, np.hypot(ua, va), twa(ua, va, heading_deg)


def interp_uv_time(t, t0, uv0, t1, uv1):
    """Linear interpolation of wind in (u, v) components at time ``t`` between ``t0`` and ``t1``.

    Components, never speed/direction: interpolating direction across 359/0 deg creates fictitious
    winds and 180 deg TWA errors (DES-860 §2.2.6). ``t`` may be ``datetime64`` or numeric (same
    unit as ``t0, t1``); the weight is clipped to [0, 1] (no extrapolation). ``uv0, uv1`` are
    ``(..., 2)`` arrays [m/s].
    """
    w = np.clip((np.asarray(t) - np.asarray(t0)) / (np.asarray(t1) - np.asarray(t0)), 0.0, 1.0)
    w = np.asarray(w, dtype=float)[..., None] if np.ndim(w) else float(w)
    return (1.0 - w) * np.asarray(uv0, dtype=float) + w * np.asarray(uv1, dtype=float)
