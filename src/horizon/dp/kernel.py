"""Numba backward-recursion kernel (DES-860 §6.2.1, §6.11).

``V[k, c] = max_s ( r(c, s, k) + V[k+1, c + s] )`` over the stencil, with the hold arc at index 0.
Arc reward [kWh] = ``P * dt / 3600`` with ``P`` the polar power at the wind averaged over the arc
end points and over ``[t_k, t_{k+1}]`` (in (u, v) components), TWA from the arc's true heading, and
``U = ground length / dt`` (leeway and currents are neglected at graph level).
Accumulation is in float64; V is stored float32 (relative rounding ~6e-8 per step, i.e. ~1e-5
after 100 steps: negligible against the 1 % physical tolerances, DES-860 §7.13).
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange

from horizon.geo.coast import bilinear_sdf
from horizon.polar.envelope import envelope_lookup
from horizon.polar.table import trilinear_scalar

__all__ = ["arc_feasibility", "backward_recursion"]


@njit(cache=True, parallel=True)
def arc_feasibility(valid, di, dj, length, sdf, x0, y0, dx, d_min):  # pragma: no cover - jitted
    """Time-independent arc mask: stencil validity + coast clearance along the arc.

    An arc is kept if both end cells and every sample along the straight grid segment (spacing
    <= dx/2, including the midpoint) have ``SDF >= d_min`` [m].

    Returns
    -------
    ok : bool (Ny, Nx, K)
    """
    ny, nx, k = valid.shape
    ok = np.zeros((ny, nx, k), dtype=np.bool_)
    for j in prange(ny):
        for i in range(nx):
            if not sdf[j, i] >= d_min:
                continue
            ok[j, i, 0] = True
            for s in range(1, k):
                if not valid[j, i, s]:
                    continue
                jj = j + dj[s]
                ii = i + di[s]
                if not sdf[jj, ii] >= d_min:
                    continue
                m = int(np.ceil(2.0 * np.hypot(di[s], dj[s]))) - 1
                good = True
                for q in range(1, m + 1):
                    f = q / (m + 1.0)
                    v = bilinear_sdf(sdf, x0, y0, dx, x0 + (i + f * di[s]) * dx,
                                     y0 + (j + f * dj[s]) * dx)
                    if not v >= d_min:
                        good = False
                        break
                ok[j, i, s] = good
    return ok


@njit(cache=True)
def _hold_power(hold_p, tws0, dtws, tws):  # pragma: no cover - jitted
    n = hold_p.shape[0]
    f = min(max((tws - tws0) / dtws, 0.0), n - 1.0)
    i = min(int(f), n - 2)
    a = f - i
    return hold_p[i] * (1.0 - a) + hold_p[i + 1] * a


@njit(cache=True, parallel=True)
def backward_recursion(V, policy, uv, di, dj, length, heading, ok, nav, P, ax, u_max_table,
                       hold_p, hold_tws0, hold_dtws, dt_s, mode, env,
                       env_ax):  # pragma: no cover - jitted
    """Fill ``V[:n]`` and ``policy`` backwards from ``V[n]`` (in place).

    Parameters
    ----------
    V : float32 (n+1, Ny, Nx)  [kWh]  ``V[n]`` holds the terminal value (-inf where not navigable).
    policy : int16 (n, Ny, Nx)  Output stencil index (-1 = no feasible arc).
    uv : float32 (n+1, Ny, Nx, 2)  [m/s]  Wind at the DP time nodes.
    di, dj : int32 (K,)  Stencil offsets (index 0 = hold).
    length, heading : float32 (Ny, Nx, K)  [m], [deg]  Geodesic arc geometry.
    ok : bool (Ny, Nx, K)  Arc feasibility; nav : bool (Ny, Nx)  navigable cells.
    P : float32 polar table; ax : 6 axis parameters (``PolarTable.axis_params``).
    u_max_table : float  [m/s]  Largest tabulated ship speed; faster arcs are invalid.
    hold_p, hold_tws0, hold_dtws : 1-D hold curve [kW] and its uniform TWS axis [m/s].
    dt_s : float  [s]
    mode : int  0 = direct single-heading reward, 1 = velocity-space envelope (hold is v = 0).
    env, env_ax : envelope table (nTWS, nvp, nvq) [kW] and its axes (EnvelopeTable.axes).
    """
    n = V.shape[0] - 1
    ny, nx = V.shape[1], V.shape[2]
    k_arcs = di.shape[0]
    dth = dt_s / 3600.0
    for k in range(n - 1, -1, -1):
        for j in prange(ny):
            for i in range(nx):
                if not nav[j, i]:
                    V[k, j, i] = -np.inf
                    policy[k, j, i] = -1
                    continue
                best = -np.inf
                bs = -1
                u0 = 0.5 * (uv[k, j, i, 0] + uv[k + 1, j, i, 0])
                v0 = 0.5 * (uv[k, j, i, 1] + uv[k + 1, j, i, 1])
                vn = V[k + 1, j, i]
                if np.isfinite(vn):
                    if mode == 1:
                        p = envelope_lookup(env, env_ax, np.hypot(u0, v0), 0.0, 0.0)
                    else:
                        p = _hold_power(hold_p, hold_tws0, hold_dtws, np.hypot(u0, v0))
                    if np.isfinite(p):
                        best = p * dth + vn
                        bs = 0
                for s in range(1, k_arcs):
                    if not ok[j, i, s]:
                        continue
                    jj = j + dj[s]
                    ii = i + di[s]
                    vn = V[k + 1, jj, ii]
                    if not np.isfinite(vn):
                        continue
                    u = 0.25 * (uv[k, j, i, 0] + uv[k + 1, j, i, 0]
                                + uv[k, jj, ii, 0] + uv[k + 1, jj, ii, 0])
                    v = 0.25 * (uv[k, j, i, 1] + uv[k + 1, j, i, 1]
                                + uv[k, jj, ii, 1] + uv[k + 1, jj, ii, 1])
                    sp = np.hypot(u, v)
                    spd = length[j, i, s] / dt_s
                    psi = np.radians(heading[j, i, s])
                    if mode == 1:
                        # ground velocity in the wind frame: v_par towards the wind source
                        vx = spd * np.sin(psi)
                        vy = spd * np.cos(psi)
                        if sp > 0.0:
                            vpar = -(vx * u + vy * v) / sp
                            vperp = (vx * v - vy * u) / sp
                        else:
                            vpar = vx
                            vperp = vy
                        p = envelope_lookup(env, env_ax, sp, vpar, vperp)
                    else:
                        if spd > u_max_table:
                            continue
                        if sp > 0.0:
                            c = -(u * np.sin(psi) + v * np.cos(psi)) / sp
                            twa = np.degrees(np.arccos(min(max(c, -1.0), 1.0)))
                        else:
                            twa = 0.0
                        p = trilinear_scalar(P, ax[0], ax[1], ax[2], ax[3], ax[4], ax[5], sp,
                                             twa, spd)
                    if not np.isfinite(p):
                        continue
                    cand = p * dth + vn
                    if cand > best:
                        best = cand
                        bs = s
                V[k, j, i] = best
                policy[k, j, i] = bs
