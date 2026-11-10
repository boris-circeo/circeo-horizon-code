"""Closed-loop causal simulator = backtest harness (DES-860 §8.1).

At every replan time ``t`` the policy sees only ``weather.forecast(issue_s <= t)`` through a
:class:`ForecastProvider` (no availability latency in S1: a forecast issued at ``t`` is usable at
``t``). Between replans the ship follows the plan: it steers towards the destination of the
active arc with ground speed ``remaining distance / remaining arc time`` capped at ``u_max``.
Energy is integrated on the TRUE wind (hourly, linear in time and bilinear in space, in (u, v)
components) with the supplied :class:`~horizon.sim.power.PowerModel`. Ground motion ignores
leeway and current (as the DP).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from horizon.geo.coast import CoastModel
from horizon.sim.policies import Plan, Policy
from horizon.sim.power import PowerModel
from horizon.weather.fields import Ensemble, WindField

__all__ = ["CausalityError", "ForecastProvider", "MissionResult", "run_mission", "sample_wind"]


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
        """Forecast issued at ``issue_s`` [s]; raises :class:`CausalityError` if in the future."""
        if issue_s > self.now_s + 1e-6:
            raise CausalityError(f"forecast issued at {issue_s} s requested at t = {self.now_s} s")
        return self._weather.forecast(issue_s, horizon_s, n_members, dt_s=dt_s,
                                      seed_offset=seed_offset)


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


def run_mission(policy: Policy, weather, truth: WindField, start_lonlat: tuple[float, float],
                duration_s: float, power_model: PowerModel, coast: CoastModel,
                replan_s: float = 6 * 3600.0, sim_dt_s: float = 900.0, u_max: float = 8.0,
                d_min_m: float = 20e3) -> MissionResult:
    """Run one closed-loop mission.

    Parameters
    ----------
    policy : Policy  Called every ``replan_s`` with a causal :class:`ForecastProvider`.
    weather : SyntheticWeather-like  Forecast source (``forecast`` and ``grid``).
    truth : WindField  True wind (covers ``[0, duration_s]``), used for energy only.
    start_lonlat : tuple  ``(lon, lat)`` [deg].
    duration_s : float  [s]  Mission length T.
    power_model : PowerModel
    coast : CoastModel  Used to count violations of ``SDF >= d_min_m``.
    replan_s, sim_dt_s : float  [s]  Replan period (multiple of ``sim_dt_s``) and Euler step.
    u_max : float  [m/s]  Ground-speed cap.
    d_min_m : float  [m]

    Returns
    -------
    MissionResult
    """
    g = coast.grid
    n = int(round(duration_s / sim_dt_s))
    jac = _jacobian(g)
    xs, ys = np.empty(n + 1), np.empty(n + 1)
    xs[0], ys[0] = g.to_xy(*start_lonlat)
    ve, vn = np.empty(n), np.empty(n)
    replans: list[float] = []
    plan: Plan | None = None
    next_replan = 0.0
    for s in range(n):
        t = s * sim_dt_s
        x, y = xs[s], ys[s]
        if t >= next_replan - 1e-6:
            plan = policy.plan(t, x, y, ForecastProvider(weather, t, duration_s))
            replans.append(t)
            next_replan += replan_s
        xd, yd, t_end = plan.dest_at(t)
        j, i = (int(np.clip(a, 0, m - 1)) for a, m in zip(g.index_of(x, y), g.shape, strict=True))
        jm = jac[j, i]
        gv = np.linalg.solve(jm, [xd - x, yd - y])  # ground displacement to go (east, north) [m]
        dist = float(np.hypot(*gv))
        speed = min(dist / max(t_end - t, sim_dt_s), u_max)
        step = gv * (min(speed * sim_dt_s, dist) / dist) if dist > 0 else np.zeros(2)
        ve[s], vn[s] = step / sim_dt_s
        xs[s + 1], ys[s + 1] = np.array([x, y]) + jm @ step
    t_grid = sim_dt_s * np.arange(n + 1)
    u, v = sample_wind(truth, t_grid[:-1] + 0.5 * sim_dt_s, 0.5 * (xs[:-1] + xs[1:]),
                       0.5 * (ys[:-1] + ys[1:]))
    p = np.asarray(power_model.power_kw(u, v, ve, vn), dtype=float)
    energy = np.concatenate([[0.0], np.cumsum(p * sim_dt_s / 3600.0)])
    lon, lat = g.to_lonlat(xs, ys)
    viol = int(np.count_nonzero(~(coast.sdf_at(xs, ys) >= d_min_m)))
    return MissionResult(t_grid, xs, ys, np.asarray(lon), np.asarray(lat), p, energy,
                         np.degrees(np.arctan2(ve, vn)) % 360.0, np.hypot(ve, vn),
                         np.array(replans), viol, float(sim_dt_s))
