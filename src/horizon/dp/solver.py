"""Backward dynamic-programming solver on the spatio-temporal graph (DES-860 §6.1-§6.2, §6.11)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from horizon.dp.kernel import arc_feasibility, backward_recursion
from horizon.dp.stencil import Stencil, build_stencil
from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar.derived import HoldCurve
from horizon.polar.envelope import EnvelopeTable, build_envelope
from horizon.polar.table import PolarTable
from horizon.weather.fields import WindField

__all__ = ["DPResult", "Path", "solve_dp", "resample_wind"]

_ENV_CACHE: dict = {}


def _envelope_for(polar: PolarTable, fa: float) -> EnvelopeTable:
    key = (hashlib.md5(polar.p.tobytes()).hexdigest(), polar.p.shape, round(fa, 9))
    if key not in _ENV_CACHE:
        _ENV_CACHE[key] = build_envelope(polar, f_avail_override=fa)
    return _ENV_CACHE[key]


def resample_wind(wind: WindField, times_s: np.ndarray) -> np.ndarray:
    """Wind at arbitrary times, linear in (u, v) components, clamped outside the source range.

    Parameters
    ----------
    wind : WindField
    times_s : ndarray (M,)  [s since epoch]

    Returns
    -------
    ndarray float32 (M, Ny, Nx, 2)  [m/s]
    """
    out = np.empty((len(times_s),) + wind.uv.shape[1:], dtype=np.float32)
    for m, t in enumerate(times_s):
        k, w = wind.time_index(float(t))
        if w == 0.0 or wind.uv.shape[0] == 1:
            out[m] = wind.uv[k]
        else:
            out[m] = (1.0 - w) * wind.uv[k] + w * wind.uv[k + 1]
    return out


@dataclass(frozen=True)
class Path:
    """Forward-extracted route; one entry per arc.

    Attributes
    ----------
    k, j, i : ndarray int (n,)  Source node (time index, row, column) of each arc.
    offset : ndarray int (n,)  Stencil index (0 = hold).
    speed : ndarray float (n,)  [m/s]  Ground speed ``length / dt`` (0 for hold).
    heading : ndarray float (n,)  [deg]  Mean true heading (NaN for hold).
    reward : ndarray float (n,)  [kWh]  ``V[k, c] - V[k+1, c']`` (arc energy).
    j_end, i_end : ndarray int (n,)  Destination cell.
    """

    k: np.ndarray
    j: np.ndarray
    i: np.ndarray
    offset: np.ndarray
    speed: np.ndarray
    heading: np.ndarray
    reward: np.ndarray
    j_end: np.ndarray
    i_end: np.ndarray

    @property
    def energy_kwh(self) -> float:
        """Total energy of the route [kWh]."""
        return float(self.reward.sum())


@dataclass(frozen=True)
class DPResult:
    """Output of :func:`solve_dp`.

    Attributes
    ----------
    V : float32 (n+1, Ny, Nx)  [kWh]  Value function (-inf on land / buffer / unreachable).
    policy : int16 (n, Ny, Nx)  Argmax stencil index (0 = hold, -1 = no feasible arc).
    stencil : Stencil
    times_s : ndarray (n+1,)  [s since epoch]  DP time nodes.
    grid : Grid
    nav : bool (Ny, Nx)  Navigable cells (SDF >= d_min).
    """

    V: np.ndarray
    policy: np.ndarray
    stencil: Stencil
    times_s: np.ndarray
    grid: Grid
    nav: np.ndarray

    @property
    def n_steps(self) -> int:
        return self.policy.shape[0]

    def path(self, j0: int, i0: int, k0: int = 0) -> Path:
        """Forward extraction of the optimal route from node ``(k0, j0, i0)``.

        Raises
        ------
        ValueError
            If the start node has no feasible continuation (V = -inf).
        """
        st = self.stencil
        if k0 >= self.n_steps or self.policy[k0, j0, i0] < 0:
            raise ValueError("no feasible route from the start node")
        ks, js, is_, offs, spd, hdg, rew, je, ie = ([] for _ in range(9))
        j, i = int(j0), int(i0)
        for k in range(k0, self.n_steps):
            s = int(self.policy[k, j, i])
            if s < 0:
                break
            jn, in_ = j + int(st.dj[s]), i + int(st.di[s])
            ks.append(k), js.append(j), is_.append(i), offs.append(s)
            spd.append(float(st.length_m[j, i, s]) / st.dt_s)
            hdg.append(float(st.heading_deg[j, i, s]))
            rew.append(float(self.V[k, j, i]) - float(self.V[k + 1, jn, in_]))
            je.append(jn), ie.append(in_)
            j, i = jn, in_
        return Path(np.array(ks), np.array(js), np.array(is_), np.array(offs), np.array(spd),
                    np.array(hdg), np.array(rew), np.array(je), np.array(ie))

    def value_at(self, x, y, k) -> np.ndarray:
        """Bilinear value [kWh] at projected points ``(x, y)`` [m] and time index ``k``.

        NaN outside the grid; -inf if a corner with non-zero weight is -inf.
        """
        g = self.grid
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        fi, fj = (x - g.x0) / g.dx, (y - g.y0) / g.dx
        inside = (fi >= 0) & (fj >= 0) & (fi <= g.nx - 1) & (fj <= g.ny - 1)
        i = np.clip(np.floor(np.where(inside, fi, 0)).astype(int), 0, g.nx - 2)
        j = np.clip(np.floor(np.where(inside, fj, 0)).astype(int), 0, g.ny - 2)
        a, b = fi - i, fj - j
        out = np.zeros(x.shape)
        bad = np.zeros(x.shape, dtype=bool)
        for dj_, di_, w in ((0, 0, (1 - a) * (1 - b)), (0, 1, a * (1 - b)),
                            (1, 0, (1 - a) * b), (1, 1, a * b)):
            v = self.V[k, j + dj_, i + di_].astype(float)
            pos = w > 1e-12
            bad |= pos & ~np.isfinite(v)
            out += np.where(pos & np.isfinite(v), w * v, 0.0)
        out = np.where(bad, -np.inf, out)
        return np.where(inside, out, np.nan)[()]


def solve_dp(wind: WindField, t0_s: float, n_steps: int, dt_s: float, polar: PolarTable,
             hold_curve: HoldCurve, coast: CoastModel, terminal=None, d_min: float = 20e3,
             u_bounds=(0.5, 8.0), stencil: Stencil | None = None,
             reward_model: str = "envelope", envelope: EnvelopeTable | None = None) -> DPResult:
    """Deterministic backward DP maximising energy over ``n_steps`` steps of ``dt_s``.

    Parameters
    ----------
    wind : WindField
        Wind (u, v "toward") [m/s] on the same grid as ``coast``; may have another time step,
        interpolated linearly in components (clamped outside its range).
    t0_s : float  [s since epoch]  Start of the horizon.
    n_steps : int  Number of DP steps; time nodes are ``t0_s + k * dt_s``.
    dt_s : float  [s]
    polar : PolarTable
    hold_curve : HoldCurve
        Station-keeping power [kW] vs TWS (uniform axis), used for the hold arc.
    coast : CoastModel
        Provides the SDF [m]; cells with ``SDF < d_min`` are excluded, as are arcs whose
        interior samples violate it.
    terminal : ndarray (Ny, Nx), optional  [kWh]  Terminal value (default zeros).
    d_min : float  [m]  Minimum distance to coast (DES-860 A.1).
    u_bounds : tuple  [m/s]  Allowed ground speed ``(u_min, u_max)``.
    stencil : Stencil, optional  Precomputed (must match grid, ``dt_s``, ``u_bounds``).
    reward_model : {"envelope", "direct"}
        ``"envelope"`` (default): arc reward = upper concave envelope of the polar at the arc's
        ground velocity in the wind frame, tack mixtures penalised by ``hold_curve.f_avail``;
        hold is ``v = 0`` (:mod:`horizon.polar.envelope`). ``"direct"``: single heading at the
        arc's mean heading; hold from ``hold_curve``.
    envelope : EnvelopeTable, optional  Precomputed table (default: built and cached).

    Returns
    -------
    DPResult
    """
    grid = coast.grid
    if wind.grid != grid:
        raise ValueError("wind and coast must share the same grid")
    st = stencil if stencil is not None else build_stencil(grid, dt_s, u_bounds)
    times = t0_s + dt_s * np.arange(n_steps + 1)
    uv = np.ascontiguousarray(resample_wind(wind, times))
    nav = np.ascontiguousarray(coast.sdf >= d_min)
    ok = arc_feasibility(st.valid, st.di, st.dj, st.length_m, coast.sdf, grid.x0, grid.y0,
                         grid.dx, float(d_min))
    V = np.empty((n_steps + 1, grid.ny, grid.nx), dtype=np.float32)
    term = np.zeros(grid.shape, np.float32) if terminal is None else np.asarray(terminal)
    if term.shape != grid.shape:
        raise ValueError("terminal must have shape (Ny, Nx)")
    V[n_steps] = np.where(nav, term, -np.inf)
    policy = np.full((n_steps, grid.ny, grid.nx), -1, dtype=np.int16)
    if reward_model not in ("envelope", "direct"):
        raise ValueError("reward_model must be 'envelope' or 'direct'")
    mode = 1 if reward_model == "envelope" else 0
    env = envelope if envelope is not None else (
        _envelope_for(polar, hold_curve.f_avail) if mode else None)
    env_t = env.reward if env is not None else np.zeros((2, 2, 2), np.float32)
    env_ax = env.axes if env is not None else np.zeros(5)
    hold_d = float((hold_curve.tws[-1] - hold_curve.tws[0]) / (hold_curve.tws.size - 1))
    backward_recursion(
        V, policy, uv, st.di, st.dj, st.length_m, st.heading_deg, ok, nav,
        polar.p, np.array(polar.axis_params), float(polar.u[-1]),
        np.ascontiguousarray(hold_curve.p_hold, dtype=np.float64),
        float(hold_curve.tws[0]), hold_d, float(dt_s), mode, env_t, env_ax,
    )
    return DPResult(V, policy, st, times, grid, nav)
