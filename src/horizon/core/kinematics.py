"""Ground-velocity kinematics: own motion + current + leeway (DES-860 §2.2.6, CONVENTIONS §5)."""

from __future__ import annotations

import numpy as np

from horizon.core.units import wrap180, wrap360

__all__ = ["leeway_vector", "ground_velocity", "ground_course", "drift_compensated_heading"]


def leeway_vector(heading_deg, u, v, k_leeway: float = 0.03):
    """Leeway velocity ``(east, north)`` [m/s] = ``k_L |W| n_lee``.

    ``n_lee`` is the unit normal to the heading on the side the wind pushes towards (away from
    where it comes from). Wind exactly along the heading gives zero leeway.

    Parameters
    ----------
    heading_deg : [deg]; u, v : true wind "toward" components [m/s]; k_leeway : [-].
    """
    p = np.radians(heading_deg)
    e_stbd_x, e_stbd_y = np.cos(p), -np.sin(p)
    side = np.sign(u * e_stbd_x + v * e_stbd_y)  # +1: wind pushes towards starboard
    mag = k_leeway * np.hypot(u, v) * side
    return mag * e_stbd_x, mag * e_stbd_y


def ground_velocity(ship_speed, heading_deg, u, v, cur_u=0.0, cur_v=0.0, k_leeway: float = 0.03):
    """Ground velocity ``(east, north)`` [m/s] of the ship.

    Parameters
    ----------
    ship_speed : [m/s] speed through water along the heading.
    heading_deg : [deg] true heading.
    u, v : [m/s] true wind "toward" components.
    cur_u, cur_v : [m/s] surface current (east, north).
    k_leeway : [-] leeway coefficient (default 0.03).
    """
    p = np.radians(heading_deg)
    le, ln = leeway_vector(heading_deg, u, v, k_leeway)
    return (ship_speed * np.sin(p) + cur_u + le, ship_speed * np.cos(p) + cur_v + ln)


def ground_course(ship_speed, heading_deg, u, v, cur_u=0.0, cur_v=0.0, k_leeway: float = 0.03):
    """Course over ground [deg, [0, 360)] for the given heading (see :func:`ground_velocity`)."""
    ve, vn = ground_velocity(ship_speed, heading_deg, u, v, cur_u, cur_v, k_leeway)
    return wrap360(np.degrees(np.arctan2(ve, vn)))


def drift_compensated_heading(cog_deg, ship_speed, u, v, cur_u=0.0, cur_v=0.0,
                              k_leeway: float = 0.03, n_iter: int = 50, tol_deg: float = 1e-8):
    """Heading [deg] whose ground track follows the desired course over ground ``cog_deg`` [deg].

    Fixed-point iteration ``psi += wrap180(cog - COG(psi))``, vectorised. ``ship_speed`` [m/s] is
    held fixed (the speed change caused by the new heading, e.g. via the polar, is ignored).
    Converges when current + leeway is clearly smaller than ``ship_speed`` (roughly < 0.7x); where
    it has not converged to ``tol_deg`` (no solution: ship cannot stem the drift, or the leeway
    side flips discontinuously because the wind is almost exactly along the heading) NaN is
    returned.
    """
    cog = np.asarray(cog_deg, dtype=float)
    psi = cog.copy()
    for _ in range(n_iter):
        err = wrap180(cog - ground_course(ship_speed, psi, u, v, cur_u, cur_v, k_leeway))
        psi = psi + err
        if np.all(np.abs(err) < tol_deg):
            break
    err = wrap180(cog - ground_course(ship_speed, psi, u, v, cur_u, cur_v, k_leeway))
    psi = np.where(np.abs(err) < 1e-6, wrap360(psi), np.nan)
    return psi if np.ndim(psi) else float(psi)
