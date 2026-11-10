"""Derived polar products for the graph DP and the NLP (DES-860 §7.3.3, §6.6, §2.6).

Contents: smooth generator cap, arc reward table, and the station-keeping (hold) power curve.
Units follow ``docs/CONVENTIONS.md`` (m/s, kW, degrees, seconds).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

from horizon.core.kinematics import station_keeping_twa
from horizon.polar.table import PolarTable

__all__ = [
    "ArcRewardTable",
    "HoldCurve",
    "arc_reward_lookup",
    "arc_reward_table",
    "f_avail",
    "hold_power_curve",
    "softplus_cap",
]


def softplus_cap(p_raw, cap: float = 3000.0, beta: float = 0.02):
    """Smooth generator cap ``cap - log(1 + exp(beta (cap - p_raw))) / beta`` (DES-860 §2.2.2).

    Differentiable replacement of ``min(p_raw, cap)``; always strictly below ``cap``. The
    deviation from the hard cap is at most ``ln(2)/beta`` (at ``p_raw = cap``) and decays
    exponentially away from the knee.

    Parameters
    ----------
    p_raw : array_like  [kW]
        Uncapped power.
    cap : float  [kW]
        Generator limit (default 3000).
    beta : float  [1/kW]
        Knee sharpness (default 0.02 -> max error 34.7 kW).

    Returns
    -------
    numpy.ndarray or float
        Capped power [kW].
    """
    x = beta * (cap - np.asarray(p_raw, dtype=np.float64))
    return cap - np.logaddexp(0.0, x) / beta


@dataclass(frozen=True)
class ArcRewardTable:
    """Arc power table ``R[TWS, TWA, k]`` [kW] for a finite set of arc speeds.

    Attributes
    ----------
    r : numpy.ndarray (float32, nTWS x nTWA x nK)  [kW]
    tws : numpy.ndarray  [m/s]
    twa : numpy.ndarray  [deg]
        TWA relative to the arc heading, [0, 180].
    speeds : numpy.ndarray  [m/s]
        Arc speeds through water (stencil crowns).
    """

    r: np.ndarray
    tws: np.ndarray
    twa: np.ndarray
    speeds: np.ndarray


def arc_reward_table(polar: PolarTable, arc_speeds) -> ArcRewardTable:
    """Sample the polar at the finite set of stencil speeds (DES-860 §7.3.3, item 3).

    Removes the U-interpolation from the hot loop: arc evaluation becomes a 2-D gather.
    The TWS/TWA axes are those of ``polar``; speeds are through-water speeds [m/s].
    """
    speeds = np.atleast_1d(np.asarray(arc_speeds, dtype=np.float64))
    if speeds.ndim != 1 or speeds.size == 0 or np.any(speeds < 0):
        raise ValueError("arc_speeds must be a non-empty 1-D array of non-negative speeds [m/s]")
    r = np.empty((polar.tws.size, polar.twa.size, speeds.size), dtype=np.float32)
    ws, wa = np.meshgrid(polar.tws, polar.twa, indexing="ij")
    for k, s in enumerate(speeds):
        r[:, :, k] = polar(ws, wa, s)
    return ArcRewardTable(r, polar.tws.copy(), polar.twa.copy(), speeds)


@njit(cache=True)
def arc_reward_lookup(r, tws0, dtws, twa0, dtwa, tws, twa, k):  # pragma: no cover - jitted
    """Bilinear gather of ``R[:, :, k]`` at (TWS [m/s], TWA [deg], sign ignored) [kW].

    Clamped at the TWS/TWA bounds; NaN for non-finite inputs or ``k`` outside ``[0, nK)``
    (same convention as :func:`horizon.polar.table.trilinear_scalar`).
    """
    nx, ny, nk = r.shape
    y = abs(twa)
    if not (np.isfinite(tws) and np.isfinite(y)) or k < 0 or k >= nk:
        return np.nan
    fx = min(max((tws - tws0) / dtws, 0.0), nx - 1.0)
    fy = min(max((y - twa0) / dtwa, 0.0), ny - 1.0)
    i = min(int(fx), nx - 2)
    j = min(int(fy), ny - 2)
    ax = fx - i
    ay = fy - j
    c0 = r[i, j, k] * (1 - ay) + r[i, j + 1, k] * ay
    c1 = r[i + 1, j, k] * (1 - ay) + r[i + 1, j + 1, k] * ay
    return c0 * (1 - ax) + c1 * ax


def f_avail(t_leg_s: float, tau_m_s: float, rho_m: float) -> float:
    """Manoeuvre availability ``1 - tau_m (1 - rho_m) / (t_leg + tau_m)`` (DES-860 §2.6.3).

    Parameters
    ----------
    t_leg_s : float  [s]  Productive leg duration between manoeuvres.
    tau_m_s : float  [s]  Manoeuvre duration.
    rho_m : float  [-]  Fraction of production kept during the manoeuvre, in [0, 1].
    """
    if t_leg_s <= 0 or tau_m_s < 0 or not 0.0 <= rho_m <= 1.0:
        raise ValueError("require t_leg > 0, tau_m >= 0, 0 <= rho_m <= 1")
    return 1.0 - tau_m_s * (1.0 - rho_m) / (t_leg_s + tau_m_s)


@dataclass(frozen=True)
class HoldCurve:
    """1-D station-keeping curve (DES-860 §6.6.1).

    Attributes
    ----------
    tws : numpy.ndarray  [m/s]
    p_hold : numpy.ndarray (float32)  [kW]
        Mean usable power ``f_avail * P(TWS, TWA_b, U*)`` (both tacks averaged).
    twa_b, twa_b_prime : numpy.ndarray (float32)  [deg]
        Optimal TWA on each tack (equal under port/starboard symmetry).
    u_star : numpy.ndarray (float32)  [m/s]
        Optimal leg speed.
    p_beam : numpy.ndarray (float32)  [kW]
        Reference raw beam-reach optimum ``max_U P(TWS, 90 deg, U)`` (no manoeuvre cost).
    f_avail : float
        Availability factor used.
    """

    tws: np.ndarray
    p_hold: np.ndarray
    twa_b: np.ndarray
    twa_b_prime: np.ndarray
    u_star: np.ndarray
    p_beam: np.ndarray
    f_avail: float


def hold_power_curve(
    polar: PolarTable,
    tau_m_s: float = 240.0,
    rho_m: float = 0.3,
    t_leg_s: float = 2700.0,
    k_leeway: float = 0.03,
    u_min: float = 0.5,
) -> HoldCurve:
    """Mean power in station-keeping by alternating beam-reach tacks (DES-860 §2.2.6, §2.6).

    Geometry: with equal-duration legs on both tacks at TWA ``theta`` and speed ``U``, the mean
    velocity along the wind axis is ``U cos(theta) - k_L TWS sin(theta)^2`` (up-wind positive; the
    smooth leeway of :func:`horizon.core.kinematics.leeway_vector` has magnitude
    ``k_L TWS sin(theta)`` and pushes down-wind); the cross-wind mean cancels by symmetry. Zero
    mean ground velocity requires ``theta = station_keeping_twa(U, TWS, k_L)`` (the
    drift-compensation bias, ~85 deg at 20 kn for U ~ 3.75 m/s, k_L = 0.03). For each TWS the
    leg speed ``U*`` is grid-searched over the polar's U axis (>= ``u_min``), with
    ``theta(U)`` imposed; currents are ignored.

    Parameters
    ----------
    polar : PolarTable
    tau_m_s : float  [s]  Manoeuvre duration (default 4 min; hypothesis, 2-6 min).
    rho_m : float  [-]  Production fraction kept during a manoeuvre (default 0.3).
    t_leg_s : float  [s]  Productive leg duration (default 45 min).
    k_leeway : float  [-]  Leeway coefficient (default 0.03, CONVENTIONS §5).
    u_min : float  [m/s]  Smallest admissible leg speed.

    Returns
    -------
    HoldCurve
    """
    fa = f_avail(t_leg_s, tau_m_s, rho_m)
    cand = polar.u[polar.u >= u_min]
    ws = polar.tws[:, None]
    theta = station_keeping_twa(cand[None, :], ws, k_leeway)  # (nTWS, nU)
    p = polar(ws, theta, cand[None, :])
    k = np.argmax(p, axis=1)
    rows = np.arange(polar.tws.size)
    theta_b = theta[rows, k]
    p_beam = polar(polar.tws[:, None], 90.0, polar.u[None, :]).max(axis=1)
    return HoldCurve(
        tws=polar.tws.copy(),
        p_hold=(fa * p[rows, k]).astype(np.float32),
        twa_b=theta_b.astype(np.float32),
        twa_b_prime=theta_b.astype(np.float32),
        u_star=cand[k].astype(np.float32),
        p_beam=p_beam.astype(np.float32),
        f_avail=fa,
    )
