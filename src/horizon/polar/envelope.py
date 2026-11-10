"""Velocity-space power envelope for graph arcs and station keeping (DES-860 §6.1.1, §6.6.1).

Over one DP step the ship may alternate headings/tacks, so the best mean power for making good a
mean ground velocity ``v`` is the upper concave envelope of the polar in velocity space, in the
wind frame (``v_par`` towards the wind source, ``v_perp`` across it; port/starboard symmetry
gives ``E(v_par, -v_perp) = E(v_par, v_perp)``). Hold is the special case ``v = 0``.

Sample points: for each TWS node and each polar (TWA, U) node the *ground* velocity
``U (cos th, sin th) + k_L TWS sin(th) (-sin th, cos th)`` (heading plus the smooth leeway of
``horizon.core.kinematics.leeway_vector``), power ``P``. The envelope is built with a 3-D convex
hull (upper facets) and tabulated on a regular velocity grid. Velocities outside the convex hull
of reachable velocities are NaN (infeasible).

Manoeuvre cost: the envelope value of a mixture of headings is multiplied by
``f_avail(t_leg, tau_m, rho_m)``; the reward is ``max(P_direct, f_avail * E)`` where ``P_direct`` is
the single-heading power at that ground velocity (linear interpolation of the sample points).
Approximation: the same ``f_avail`` is used for any mixture, however small the tack fraction, so
slightly pessimistic for nearly straight arcs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import ConvexHull

from horizon.polar.derived import f_avail
from horizon.polar.table import PolarTable

__all__ = ["EnvelopeTable", "build_envelope", "envelope_lookup"]


@dataclass(frozen=True)
class EnvelopeTable:
    """Power envelope ``[TWS, v_par, v_perp >= 0]`` [kW], float32, NaN = infeasible velocity.

    Attributes
    ----------
    reward : ndarray (nTWS, nvp, nvq)  ``max(direct, f_avail * e)`` [kW].
    e : ndarray  Raw concave envelope [kW]. direct : ndarray  Single-heading power [kW] (NaN
        where no single heading reaches that velocity).
    tws0, dtws : float  [m/s]. vp0, vq0, dv : float  [m/s] velocity-grid origin / step.
    f_avail : float  Availability factor applied to mixtures.
    """

    reward: np.ndarray
    e: np.ndarray
    direct: np.ndarray
    tws0: float
    dtws: float
    vp0: float
    vq0: float
    dv: float
    f_avail: float

    @property
    def axes(self) -> np.ndarray:
        """``(tws0, dtws, vp0, vq0, dv)`` for the Numba kernel."""
        return np.array([self.tws0, self.dtws, self.vp0, self.vq0, self.dv])

    def v_par_axis(self) -> np.ndarray:
        return self.vp0 + self.dv * np.arange(self.reward.shape[1])

    def v_perp_axis(self) -> np.ndarray:
        return self.vq0 + self.dv * np.arange(self.reward.shape[2])


def build_envelope(polar: PolarTable, tau_m_s: float = 240.0, rho_m: float = 0.3,
                   t_leg_s: float = 2700.0, k_leeway: float = 0.03, dv: float = 0.25,
                   f_avail_override: float | None = None) -> EnvelopeTable:
    """Tabulate the velocity-space envelope of ``polar`` (see module docstring).

    Parameters
    ----------
    polar : PolarTable
    tau_m_s, rho_m, t_leg_s : float
        Manoeuvre parameters [s], [-], [s]; defaults as :func:`horizon.polar.hold_power_curve`.
    k_leeway : float  [-]  Leeway coefficient.
    dv : float  [m/s]  Velocity-grid step.
    f_avail_override : float, optional  Use this availability factor instead (1.0 = no cost).
    """
    fa = f_avail(t_leg_s, tau_m_s, rho_m) if f_avail_override is None else f_avail_override
    th = np.radians(polar.twa)[:, None]
    uu = polar.u[None, :]
    nt = polar.tws.size
    vmax = 0.0
    pts = []
    for it in range(nt):
        lw = k_leeway * polar.tws[it] * np.sin(th)
        vp = uu * np.cos(th) - lw * np.sin(th)
        vq = uu * np.sin(th) + lw * np.cos(th)
        pts.append((vp.ravel(), vq.ravel(), polar.p[it].ravel().astype(np.float64)))
        vmax = max(vmax, float(np.abs(vp).max()), float(np.abs(vq).max()))
    nv = int(np.ceil(vmax / dv))
    ax_p = dv * np.arange(-nv, nv + 1)
    ax_q = dv * np.arange(0, nv + 1)
    gp, gq = np.meshgrid(ax_p, ax_q, indexing="ij")
    e_t = np.full((nt, ax_p.size, ax_q.size), np.nan, dtype=np.float32)
    d_t = np.full_like(e_t, np.nan)
    q = np.column_stack([gp.ravel(), gq.ravel()])
    for it, (vp, vq, p) in enumerate(pts):
        # both tacks: mirror in v_perp
        x = np.concatenate([vp, vp])
        y = np.concatenate([vq, -vq])
        z = np.concatenate([p, p])
        xyz = np.column_stack([x, y, z])
        hull = ConvexHull(xyz)
        up = hull.equations[:, 2] > 1e-9
        a, b, c, d = (hull.equations[up, k] for k in range(4))
        zp = -(q[:, :1] * a + q[:, 1:2] * b + d) / c  # (nq, nplanes)
        env = zp.min(axis=1)
        h2 = ConvexHull(xyz[:, :2]).equations
        inside = np.all(q @ h2[:, :2].T + h2[:, 2] <= 1e-9, axis=1)
        env = np.where(inside, env, np.nan)
        # remove duplicate sample positions (U = 0 etc.) for the interpolator
        key = np.round(xyz[:, :2], 9)
        _, idx = np.unique(key, axis=0, return_index=True)
        direct = LinearNDInterpolator(xyz[idx, :2], z[idx])(q)
        direct = np.where(inside, direct, np.nan)
        env = np.where(np.isfinite(direct), np.maximum(env, direct), env)
        e_t[it] = env.reshape(gp.shape)
        d_t[it] = direct.reshape(gp.shape)
    reward = np.where(np.isfinite(d_t), np.maximum(d_t, fa * e_t), fa * e_t).astype(np.float32)
    return EnvelopeTable(reward, e_t, d_t, float(polar.tws[0]), float(polar.d_tws),
                         float(ax_p[0]), 0.0, float(dv), float(fa))


@njit(cache=True)
def envelope_lookup(tab, ax, tws, vpar, vperp):  # pragma: no cover - jitted
    """Trilinear lookup [kW] at TWS [m/s], ``v_par`` [m/s], ``v_perp`` [m/s] (sign ignored).

    TWS is clamped; NaN if the velocity is outside the table or any corner with non-zero weight
    is NaN (infeasible).
    """
    nt, npv, nq = tab.shape
    vq = abs(vperp)
    fx = (tws - ax[0]) / ax[1]
    fx = min(max(fx, 0.0), nt - 1.0)
    fy = (vpar - ax[2]) / ax[4]
    fz = (vq - ax[3]) / ax[4]
    if not (fy >= 0.0 and fy <= npv - 1.0 and fz >= 0.0 and fz <= nq - 1.0):
        return np.nan
    i = min(int(fx), nt - 2)
    j = min(int(fy), npv - 2)
    k = min(int(fz), nq - 2)
    a = fx - i
    b = fy - j
    c = fz - k
    out = 0.0
    for di in range(2):
        wa = a if di else 1.0 - a
        for dj in range(2):
            wb = b if dj else 1.0 - b
            for dk in range(2):
                w = wa * wb * (c if dk else 1.0 - c)
                if w > 0.0:
                    out += w * tab[i + di, j + dj, k + dk]
    return out
