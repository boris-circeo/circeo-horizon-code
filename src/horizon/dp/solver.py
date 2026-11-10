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
    """Forward-extracted route, expanded to one entry per DP step.

    A macro arc spanning ``m`` steps contributes ``m`` consecutive entries sharing ``offset``,
    ``speed`` and ``heading``; its positions advance linearly (fractional cell indices) and its
    energy is split equally over its sub-steps. For one-step arcs everything is integer-valued.

    Attributes
    ----------
    k : ndarray int (n,)  DP step index of each entry.
    j, i : ndarray float (n,)  Row / column (fractional) at the start of the step.
    offset : ndarray int (n,)  Stencil index of the arc (0 = hold).
    speed : ndarray float (n,)  [m/s]  Ground speed ``length / (span dt)`` (0 for hold).
    heading : ndarray float (n,)  [deg]  Mean true heading (NaN for hold).
    reward : ndarray float (n,)  [kWh]  Arc energy ``V[k] - V[k+m]`` divided by ``m``.
    j_end, i_end : ndarray float (n,)  Row / column (fractional) at the end of the step.
    arc_k, arc_j, arc_i, arc_offset, arc_span : ndarray int (n_arcs,)
        Arc-level source node, stencil index and span.
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
    arc_k: np.ndarray
    arc_j: np.ndarray
    arc_i: np.ndarray
    arc_offset: np.ndarray
    arc_span: np.ndarray

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
        cols = {n: [] for n in ("k", "j", "i", "offset", "speed", "heading", "reward", "j_end",
                                "i_end", "ak", "aj", "ai", "ao", "am")}
        j, i = int(j0), int(i0)
        k = int(k0)
        while k < self.n_steps:
            s = int(self.policy[k, j, i])
            if s < 0:
                break
            m = int(st.span[s])
            jn, in_ = j + int(st.dj[s]), i + int(st.di[s])
            r = (float(self.V[k, j, i]) - float(self.V[k + m, jn, in_])) / m
            spd = float(st.length_m[j, i, s]) / (m * st.dt_s)
            hdg = float(st.heading_deg[j, i, s])
            for q in range(m):
                f0, f1 = q / m, (q + 1) / m
                for name, val in (("k", k + q), ("j", j + f0 * (jn - j)), ("i", i + f0 * (in_ - i)),
                                  ("offset", s), ("speed", spd), ("heading", hdg), ("reward", r),
                                  ("j_end", j + f1 * (jn - j)), ("i_end", i + f1 * (in_ - i))):
                    cols[name].append(val)
            cols["ak"].append(k), cols["aj"].append(j), cols["ai"].append(i)
            cols["ao"].append(s), cols["am"].append(m)
            j, i, k = jn, in_, k + m
        a = {n: np.array(v) for n, v in cols.items()}
        return Path(a["k"], a["j"], a["i"], a["offset"], a["speed"], a["heading"], a["reward"],
                    a["j_end"], a["i_end"], a["ak"], a["aj"], a["ai"], a["ao"], a["am"])

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
             u_bounds=(0.5, 8.0), stencil: Stencil | None = None, max_span: int = 2,
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
    max_span : int
        Maximum DP steps spanned by one arc when ``stencil`` is not given (default 2; 3 gives
        ~3 % more energy and finer headings at ~2x the cost; 1 = plain one-step ring). Arcs
        overshooting the horizon end are forbidden.
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
    st = stencil if stencil is not None else build_stencil(grid, dt_s, u_bounds, max_span=max_span)
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
        float(hold_curve.tws[0]), hold_d, float(dt_s), mode, env_t, env_ax, st.span,
        np.ascontiguousarray(0.5 * (uv[:-1] + uv[1:])), st.sin_h, st.cos_h,
    )
    return DPResult(V, policy, st, times, grid, nav)
