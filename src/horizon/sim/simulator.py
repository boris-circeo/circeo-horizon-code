"""Closed-loop causal simulator = backtest harness (DES-860 §8.1).

At every replan time ``t`` the policy sees only ``weather.forecast(issue_s <= t)`` through a
:class:`ForecastProvider` (no availability latency in S1: a forecast issued at ``t`` is usable at
``t``). Between replans the ship follows the plan: it steers towards the destination of the
active arc with ground speed ``remaining distance / remaining arc time`` capped at ``u_max``.
Energy is integrated on the TRUE wind (hourly, linear in time and bilinear in space, in (u, v)
components) with the supplied :class:`~horizon.sim.power.PowerModel`. Ground motion ignores
leeway and current (as the DP).

Coast safety guard (S4). Every integration step is a straight grid-frame chord whose EXACT minimum
on the bilinear SDF (:meth:`~horizon.geo.coast.CoastModel.segment_min`, the field the DP and the
refiner use) is tested before the move. A step that would go below ``d_min`` (or below the
current clearance if the ship already is below it) is shortened to the largest admissible
fraction (the ship slows / stops at the limit) and counted as a *guard intervention*. Correct
planners never trigger it (counts are reported in :class:`MissionResult` and metrics); it is a
last line of defence, not part of the planning. The state of a run lives in :class:`SimState`
so that long missions can be advanced in segments and resumed from a checkpoint
(:mod:`horizon.sim.longrun`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from horizon.geo.coast import SDF_TOL_M, CoastModel, segment_min_bilinear
from horizon.sim.policies import Plan, Policy
from horizon.sim.power import PowerModel
from horizon.weather.fields import Ensemble, WindField

__all__ = ["CausalityError", "ForecastProvider", "MissionResult", "SimState", "advance",
           "energy_on_truth", "energy_on_truth_ex", "run_mission", "sample_wind", "track_tws",
           "truncate_horizon"]


class CausalityError(RuntimeError):
    """A policy asked for information issued after the current time."""


class ForecastProvider:
    """Causal wrapper of a weather source: refuses forecasts with ``issue_s > now_s``.

    Parameters
    ----------
    weather : object with ``forecast(issue_s, horizon_s, n_members, dt_s, seed_offset)``
    now_s : float  [s since epoch]  Current simulation time.
    mission_end_s : float  [s]  End of the mission (planning horizons may be truncated to it).
    """

    def __init__(self, weather, now_s: float, mission_end_s: float = float("inf")):
        self._weather = weather
        self.now_s = float(now_s)
        self.mission_end_s = float(mission_end_s)

    def forecast(self, issue_s: float, horizon_s: float, n_members: int, dt_s: float = 10800.0,
                 seed_offset: int = 0) -> Ensemble:
        """Forecast issued at ``issue_s`` [s]; raises :class:`CausalityError` if in the future.

        The horizon is truncated to the end of the mission / available data (``mission_end_s``):
        valid times beyond it are not requested from the weather source (the returned ensemble is
        shorter; consumers clamp to its last field, i.e. persistence, never a wrap-around).
        """
        if issue_s > self.now_s + 1e-6:
            raise CausalityError(f"forecast issued at {issue_s} s requested at t = {self.now_s} s")
        horizon_s = truncate_horizon(issue_s, horizon_s, dt_s, self.mission_end_s)
        return self._weather.forecast(issue_s, horizon_s, n_members, dt_s=dt_s,
                                      seed_offset=seed_offset)


def truncate_horizon(issue_s: float, horizon_s: float, dt_s: float, end_s: float) -> float:
    """Largest multiple of ``dt_s`` not above ``horizon_s`` with ``issue_s + h <= end_s`` [s]."""
    if issue_s + horizon_s <= end_s + 1e-6:
        return horizon_s
    return max(np.floor((end_s - issue_s) / dt_s + 1e-9), 0.0) * dt_s


@dataclass(frozen=True)
class MissionResult:
    """Outcome of a mission (``n`` simulation steps of ``sim_dt_s``).

    Attributes
    ----------
    t_s : (n+1,) [s]; x, y : (n+1,) [m] grid frame; lon, lat : (n+1,) [deg].
    power_kw : (n,) [kW]  Mean power over each step. energy_kwh : (n+1,) [kWh]  Cumulative.
    heading_deg : (n,) [deg]  Commanded true heading; speed_ms : (n,) [m/s]  Commanded ground speed.
    replan_times_s : (n_replans,) [s]. coast_violations : int  Positions with SDF < d_min.
    sim_dt_s : float [s].
    guard_interventions : int  Steps shortened by the coast safety guard (0 for correct planners).
    guard_events : tuple of (t_s, x, y, fraction) of the first interventions (at most 1000).
    min_margin_m : float [m]  Minimum over all executed chords of ``SDF - d_min`` (exact on the
        bilinear SDF; ``>= 0`` means the continuous executed track never went below ``d_min``).
    manoeuvre_kind : (n,) int8 or None  Per-step manoeuvre class (0 none, 1 tack, 2 gybe, 3 turn)
        when the manoeuvre model is enabled (:mod:`horizon.sim.manoeuvre`).
    """

    t_s: np.ndarray
    x: np.ndarray
    y: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    power_kw: np.ndarray
    energy_kwh: np.ndarray
    heading_deg: np.ndarray
    speed_ms: np.ndarray
    replan_times_s: np.ndarray
    coast_violations: int
    sim_dt_s: float
    guard_interventions: int = 0
    guard_events: tuple = ()
    min_margin_m: float = float("nan")
    manoeuvre_kind: np.ndarray | None = None

    @property
    def n_replans(self) -> int:
        return int(self.replan_times_s.size)


def sample_wind(wind: WindField, t_s, x, y) -> tuple[np.ndarray, np.ndarray]:
    """True wind ``(u, v)`` [m/s] at times [s] and grid-frame points [m] (clamped at the edges).

    Linear in time and bilinear in space, on the (u, v) components.
    """
    g = wind.grid
    t_s, x, y = np.broadcast_arrays(*(np.asarray(a, float) for a in (t_s, x, y)))
    fi = np.clip((x - g.x0) / g.dx, 0, g.nx - 1)
    fj = np.clip((y - g.y0) / g.dx, 0, g.ny - 1)
    i = np.minimum(fi.astype(int), g.nx - 2)
    j = np.minimum(fj.astype(int), g.ny - 2)
    a, b = (fi - i)[..., None], (fj - j)[..., None]
    nt = wind.times_s.size
    r = np.clip((t_s - wind.times_s[0]) / wind.dt_s, 0, nt - 1) if nt > 1 else np.zeros_like(t_s)
    k = np.minimum(r.astype(int), max(nt - 2, 0))
    w = (r - k)[..., None]
    k1 = np.minimum(k + 1, nt - 1)
    out = 0.0
    for tk, wt in ((k, 1 - w), (k1, w)):
        s = ((1 - a) * (1 - b) * wind.uv[tk, j, i] + a * (1 - b) * wind.uv[tk, j, i + 1]
             + (1 - a) * b * wind.uv[tk, j + 1, i] + a * b * wind.uv[tk, j + 1, i + 1])
        out = out + wt * s
    return out[..., 0], out[..., 1]


def _jacobian(grid) -> np.ndarray:
    """Per-cell ``[[e_east, e_north]]`` columns, shape (Ny, Nx, 2, 2) [grid m per ground m]."""
    if "jac" not in grid._cache:
        lon, lat = grid.lonlat_mesh()
        e, n = grid.local_basis(lon, lat)
        grid._cache["jac"] = np.stack([e, n], axis=-1)  # [..., xy, (east, north)]
    return grid._cache["jac"]


@dataclass
class SimState:
    """Mutable kinematic state of a mission (everything needed to resume it).

    Attributes
    ----------
    step : int  Number of integration steps done (time = ``step * sim_dt_s``).
    x, y : float  [m]  Position. plan : Plan or None  Active plan. next_replan : float  [s].
    replans : list of float  Replan times so far [s].
    guard_interventions : int. guard_events : list of (t, x, y, fraction).
    min_margin_m : float  Running minimum of ``SDF - d_min`` over executed chords [m].
    """

    step: int
    x: float
    y: float
    plan: Plan | None = None
    next_replan: float = 0.0
    replans: list = field(default_factory=list)
    guard_interventions: int = 0
    guard_events: list = field(default_factory=list)
    min_margin_m: float = float("inf")


def advance(policy: Policy, weather, coast: CoastModel, state: SimState, n_steps: int,
            end_s: float, replan_s: float = 6 * 3600.0, sim_dt_s: float = 900.0,
            u_max: float = 8.0, d_min_m: float = 20e3, guard: bool = True):
    """Advance ``state`` by ``n_steps`` integration steps (in place).

    Returns ``(xs, ys, ve, vn)``: positions ``(n_steps + 1,)`` [m] starting at the state position
    and the executed ground velocity ``(n_steps,)`` (east, north) [m/s] of every step.
    ``end_s`` [s] is the end of the mission as seen by the policies (forecast horizons are
    truncated to it, e.g. the end of the data).
    """
    g = coast.grid
    jac = _jacobian(g)
    thr = d_min_m - SDF_TOL_M
    sdf = coast.sdf
    xs, ys = np.empty(n_steps + 1), np.empty(n_steps + 1)
    ve, vn = np.empty(n_steps), np.empty(n_steps)
    xs[0], ys[0] = state.x, state.y
    for s in range(n_steps):
        t = (state.step + s) * sim_dt_s
        x, y = xs[s], ys[s]
        if t >= state.next_replan - 1e-6 or state.plan is None:
            state.plan = policy.plan(t, x, y, ForecastProvider(weather, t, end_s))
            state.replans.append(t)
            while state.next_replan <= t + 1e-6:
                state.next_replan += replan_s
        xd, yd, t_end = state.plan.dest_at(t)
        j, i = (int(np.clip(a, 0, m - 1)) for a, m in zip(g.index_of(x, y), g.shape, strict=True))
        jm = jac[j, i]
        gv = np.linalg.solve(jm, [xd - x, yd - y])  # ground displacement to go (east, north) [m]
        dist = float(np.hypot(*gv))
        speed = min(dist / max(t_end - t, sim_dt_s), u_max)
        step = gv * (min(speed * sim_dt_s, dist) / dist) if dist > 0 else np.zeros(2)
        dxy = jm @ step
        xn, yn = x + dxy[0], y + dxy[1]
        if guard:
            m0 = segment_min_bilinear(sdf, g.x0, g.y0, g.dx, x, y, x, y)
            floor = min(thr, m0) if m0 == m0 else thr
            mc = segment_min_bilinear(sdf, g.x0, g.y0, g.dx, x, y, xn, yn)
            if not mc >= floor - 1e-9:  # also catches NaN (leaving the grid)
                lo, hi = 0.0, 1.0
                for _ in range(40):  # largest admissible fraction (min along a prefix is monotone)
                    mid = 0.5 * (lo + hi)
                    mm = segment_min_bilinear(sdf, g.x0, g.y0, g.dx, x, y, x + mid * dxy[0],
                                              y + mid * dxy[1])
                    if mm >= floor - 1e-9:
                        lo = mid
                    else:
                        hi = mid
                state.guard_interventions += 1
                if len(state.guard_events) < 1000:
                    state.guard_events.append((t, x, y, lo))
                step = step * lo
                dxy = dxy * lo
                xn, yn = x + dxy[0], y + dxy[1]
                mc = segment_min_bilinear(sdf, g.x0, g.y0, g.dx, x, y, xn, yn)
            state.min_margin_m = min(state.min_margin_m, float(mc) - d_min_m)
        ve[s], vn[s] = step / sim_dt_s
        xs[s + 1], ys[s + 1] = xn, yn
    state.step += n_steps
    state.x, state.y = float(xs[-1]), float(ys[-1])
    return xs, ys, ve, vn


def energy_on_truth_ex(truth: WindField, power_model: PowerModel, t_start_s: float,
                       sim_dt_s: float, xs, ys, ve, vn, manoeuvre=None, prev=None):
    """As :func:`energy_on_truth` plus manoeuvre losses; returns ``(p_kw, kind, new_prev)``.

    ``manoeuvre`` : :class:`~horizon.sim.manoeuvre.ManoeuvreModel` or None / disabled (then
    ``kind`` is all zeros and ``p_kw`` is bit-identical to the Sprint-4 value). ``prev`` is the
    detector state carried across segments (see :func:`horizon.sim.manoeuvre.detect_manoeuvres`).
    """
    n = ve.size
    t_mid = t_start_s + sim_dt_s * (np.arange(n) + 0.5)
    u, v = sample_wind(truth, t_mid, 0.5 * (xs[:-1] + xs[1:]), 0.5 * (ys[:-1] + ys[1:]))
    p = np.asarray(power_model.power_kw(u, v, ve, vn), dtype=float)
    if manoeuvre is None or not manoeuvre.enabled:
        return p, np.zeros(n, np.int8), prev
    from horizon.sim.manoeuvre import apply_manoeuvre_losses, detect_manoeuvres
    from horizon.sim.power import HOLD_SPEED_MS

    moving = np.hypot(ve, vn) >= HOLD_SPEED_MS
    psi = np.degrees(np.arctan2(ve, vn)) % 360.0
    kind, new_prev = detect_manoeuvres(psi, u, v, moving, manoeuvre, prev)
    return apply_manoeuvre_losses(p, kind, sim_dt_s, manoeuvre), kind, new_prev


def track_tws(truth: WindField, t_start_s: float, sim_dt_s: float, xs, ys) -> np.ndarray:
    """True wind speed [m/s] experienced at mid-step / mid-chord (exposure metrics)."""
    n = len(xs) - 1
    t_mid = t_start_s + sim_dt_s * (np.arange(n) + 0.5)
    u, v = sample_wind(truth, t_mid, 0.5 * (xs[:-1] + xs[1:]), 0.5 * (ys[:-1] + ys[1:]))
    return np.hypot(u, v)


def energy_on_truth(truth: WindField, power_model: PowerModel, t_start_s: float, sim_dt_s: float,
                    xs, ys, ve, vn) -> np.ndarray:
    """Mean power [kW] of each step on the true wind (mid-step time and mid-chord position)."""
    return energy_on_truth_ex(truth, power_model, t_start_s, sim_dt_s, xs, ys, ve, vn)[0]


def run_mission(policy: Policy, weather, truth: WindField, start_lonlat: tuple[float, float],
                duration_s: float, power_model: PowerModel, coast: CoastModel,
                replan_s: float = 6 * 3600.0, sim_dt_s: float = 900.0, u_max: float = 8.0,
                d_min_m: float = 20e3, guard: bool = True, manoeuvre=None) -> MissionResult:
    """Run one closed-loop mission.

    Parameters
    ----------
    policy : Policy  Called every ``replan_s`` with a causal :class:`ForecastProvider`.
    weather : SyntheticWeather-like  Forecast source (``forecast`` and ``grid``).
    truth : WindField  True wind (covers ``[0, duration_s]``), used for energy only.
    start_lonlat : tuple  ``(lon, lat)`` [deg].
    duration_s : float  [s]  Mission length T.
    power_model : PowerModel
    coast : CoastModel  Clearance field: the executed track must keep ``coast.sdf >= d_min_m``
        (with a port corridor this is the relaxed SDF, see
        :func:`horizon.geo.coast.port_corridor`). Used by the safety guard and the violation count.
    replan_s, sim_dt_s : float  [s]  Replan period (multiple of ``sim_dt_s``) and Euler step.
    u_max : float  [m/s]  Ground-speed cap.
    d_min_m : float  [m]
    guard : bool  Enable the coast safety guard (default; disable only to diagnose planners).
    manoeuvre : ManoeuvreModel, optional  Charge manoeuvre losses (None / disabled = Sprint 4).

    Returns
    -------
    MissionResult
    """
    g = coast.grid
    n = int(round(duration_s / sim_dt_s))
    x0, y0 = g.to_xy(*start_lonlat)
    state = SimState(0, float(x0), float(y0))
    xs, ys, ve, vn = advance(policy, weather, coast, state, n, duration_s, replan_s, sim_dt_s,
                             u_max, d_min_m, guard)
    t_grid = sim_dt_s * np.arange(n + 1)
    p, kind, _ = energy_on_truth_ex(truth, power_model, 0.0, sim_dt_s, xs, ys, ve, vn, manoeuvre)
    energy = np.concatenate([[0.0], np.cumsum(p * sim_dt_s / 3600.0)])
    lon, lat = g.to_lonlat(xs, ys)
    viol = int(np.count_nonzero(~(coast.sdf_at(xs, ys) >= d_min_m - SDF_TOL_M)))
    return MissionResult(t_grid, xs, ys, np.asarray(lon), np.asarray(lat), p, energy,
                         np.degrees(np.arctan2(ve, vn)) % 360.0, np.hypot(ve, vn),
                         np.array(state.replans), viol, float(sim_dt_s),
                         state.guard_interventions, tuple(state.guard_events),
                         float(state.min_margin_m),
                         kind if (manoeuvre is not None and manoeuvre.enabled) else None)
