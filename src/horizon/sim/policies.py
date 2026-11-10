"""Routing policies: baselines B0/B1 and the hindsight oracle (DES-860 §3.2, §8.1-8.2).

A policy maps ``(t, x, y, provider)`` to a :class:`Plan`: a sequence of arcs, each given by its
destination point (projected metres) and a uniform time step. The simulator executes the plan
between replans. ``provider`` is a causal :class:`horizon.sim.simulator.ForecastProvider`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import numpy as np
from pyproj import Geod

from horizon.dp import build_stencil, solve_dp
from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar.derived import HoldCurve
from horizon.polar.table import PolarTable
from horizon.weather.fields import WindField

if TYPE_CHECKING:  # pragma: no cover
    from horizon.sim.power import PowerModel
    from horizon.sim.simulator import ForecastProvider

__all__ = ["Plan", "Policy", "HoldAtPointPolicy", "DeterministicMPCPolicy", "OraclePolicy",
           "best_climatological_point"]

DT_PLAN_S = 3 * 3600.0


@dataclass(frozen=True)
class Plan:
    """Sequence of arcs ``k = 0..n-1`` over ``[t0 + k dt, t0 + (k+1) dt]``.

    Attributes
    ----------
    t0_s : float  [s since epoch]  Start of the first arc.
    dt_s : float  [s]  Arc duration.
    x, y : ndarray (n,)  [m]  Destination of each arc in the grid frame (hold = current cell).
    value_kwh : float  Planned energy [kWh] (NaN if not available), informative only.
    """

    t0_s: float
    dt_s: float
    x: np.ndarray
    y: np.ndarray
    value_kwh: float = float("nan")

    def dest_at(self, t_s: float) -> tuple[float, float, float]:
        """Destination ``(x, y)`` [m] and end time [s] of the arc active at ``t_s``.

        After the last arc the ship holds the final destination (end time = ``t_s``).
        """
        n = self.x.size
        k = int(np.floor((t_s - self.t0_s) / self.dt_s + 1e-9))
        k = max(k, 0)
        if k >= n:
            return float(self.x[-1]), float(self.y[-1]), t_s
        return float(self.x[k]), float(self.y[k]), self.t0_s + (k + 1) * self.dt_s


class Policy(Protocol):
    """Routing policy protocol."""

    def plan(self, t_s: float, x: float, y: float, provider: ForecastProvider) -> Plan:
        """Plan from position ``(x, y)`` [m] at time ``t_s`` [s] using only causal information."""
        ...


def _nearest_cell(grid: Grid, mask: np.ndarray, x: float, y: float) -> tuple[int, int]:
    """Indices ``(j, i)`` of the cell with ``mask`` True nearest to ``(x, y)`` [m]."""
    X, Y = grid.xy_mesh()
    d2 = np.where(mask, (X - x) ** 2 + (Y - y) ** 2, np.inf)
    j, i = np.unravel_index(int(np.argmin(d2)), d2.shape)
    return int(j), int(i)


def _plan_from_path(grid: Grid, path, t0_s: float, dt_s: float, value: float) -> Plan:
    return Plan(t0_s, dt_s, grid.x0 + grid.dx * path.i_end, grid.y0 + grid.dx * path.j_end, value)


class HoldAtPointPolicy:
    """B0: transit straight to a fixed point, then station-keep forever (DES-860 §8.3).

    Parameters
    ----------
    x_target, y_target : float  [m]  Target in the grid frame.
    transit_speed : float  [m/s]  Transit speed.
    dt_s : float  [s]  Arc duration of the generated plan.
    """

    def __init__(self, x_target: float, y_target: float, transit_speed: float = 4.0,
                 dt_s: float = DT_PLAN_S):
        self.target = (float(x_target), float(y_target))
        self.speed = transit_speed
        self.dt_s = dt_s

    def plan(self, t_s, x, y, provider):
        d = np.hypot(self.target[0] - x, self.target[1] - y)
        n = int(np.ceil(d / (self.speed * self.dt_s))) + 1
        s = np.minimum(self.speed * self.dt_s * np.arange(1, n + 1), d)
        f = s / d if d > 0 else np.zeros(n)
        return Plan(t_s, self.dt_s, x + f * (self.target[0] - x), y + f * (self.target[1] - y))


def best_climatological_point(truths: list[WindField], power_model: PowerModel, coast: CoastModel,
                              start_xy: tuple[float, float], sdf_min_m: float = 50e3,
                              d_min_m: float = 20e3, bbox=(-45.0, 5.0, 35.0, 65.0),
                              max_range_m: float = 800 * 1852.0) -> tuple[float, float, float]:
    """Cell maximising the mean hold power over training truths (B0 point).

    Candidates lie in the nominal basin ``bbox`` (lon_min, lon_max, lat_min, lat_max) [deg],
    within ``max_range_m`` [m] (geodesic, default 800 NM) of the start, have
    ``SDF >= sdf_min_m`` and a straight grid-frame line from ``start_xy`` that keeps
    ``SDF >= d_min_m`` (best candidates are tested in decreasing order of mean power).

    Parameters
    ----------
    truths : list of WindField  Training winters (seeds disjoint from evaluation).
    power_model : PowerModel  Hold power is ``power_kw(u, v, 0, 0)``.
    coast : CoastModel
    start_xy : tuple  [m]  Start position, grid frame.
    sdf_min_m, d_min_m : float  [m]
    bbox : tuple  [deg]  Nominal basin. max_range_m : float  [m]  Operational range from the start.

    Returns
    -------
    x, y : float  [m]  Cell centre. mean_kw : float  [kW]  Training-mean hold power there.
    """
    grid = coast.grid
    acc = np.zeros(grid.shape)
    for tr in truths:
        acc += power_model.power_kw(tr.uv[..., 0], tr.uv[..., 1], 0.0, 0.0).mean(axis=0)
    mean = acc / len(truths)
    lon, lat = grid.lonlat_mesh()
    lon0, lat0 = grid.to_lonlat(*start_xy)
    _, _, dist = Geod(ellps="WGS84").inv(np.full(lon.shape, lon0), np.full(lon.shape, lat0),
                                         lon, lat)
    ok = ((coast.sdf >= sdf_min_m) & (lon >= bbox[0]) & (lon <= bbox[1]) & (lat >= bbox[2])
          & (lat <= bbox[3]) & (dist <= max_range_m))
    cand = np.where(ok, mean, -np.inf)
    for flat in np.argsort(cand, axis=None)[::-1]:
        j, i = np.unravel_index(flat, cand.shape)
        if not np.isfinite(cand[j, i]):
            break
        x, y = grid.x0 + i * grid.dx, grid.y0 + j * grid.dx
        m = max(int(np.ceil(np.hypot(x - start_xy[0], y - start_xy[1]) / (0.5 * grid.dx))), 1)
        f = np.linspace(0.0, 1.0, m + 1)
        sdf = coast.sdf_at(start_xy[0] + f * (x - start_xy[0]), start_xy[1] + f * (y - start_xy[1]))
        if np.all(sdf >= d_min_m):
            return float(x), float(y), float(mean[j, i])
    raise ValueError("no admissible hold point")


class DeterministicMPCPolicy:
    """B1: receding-horizon DP on the control forecast only (DES-860 §8.3).

    At each replan: forecast control member (``n_members = 1``), DP over
    ``min(horizon, mission end - t)`` with zero terminal value, plan = optimal path.

    Parameters
    ----------
    polar, hold_curve, coast : see :func:`horizon.dp.solve_dp`.
    horizon_days : float  [d]  Planning horizon (5 or 15).
    dt_s : float  [s]  DP step (3 h).
    d_min_m : float  [m]  Coast clearance.
    reward_model : str  DP reward model (``"envelope"`` default).
    """

    def __init__(self, polar: PolarTable, hold_curve: HoldCurve, coast: CoastModel,
                 horizon_days: float = 5.0, dt_s: float = DT_PLAN_S, d_min_m: float = 20e3,
                 reward_model: str = "envelope"):
        self.polar, self.hold, self.coast = polar, hold_curve, coast
        self.horizon_s = horizon_days * 86400.0
        self.dt_s = dt_s
        self.d_min = d_min_m
        self.reward_model = reward_model
        self._stencil = build_stencil(coast.grid, dt_s)

    def plan(self, t_s, x, y, provider):
        n = max(int(np.ceil(min(self.horizon_s, provider.mission_end_s - t_s) / self.dt_s)), 1)
        ens = provider.forecast(issue_s=t_s, horizon_s=n * self.dt_s, n_members=1, dt_s=self.dt_s)
        res = solve_dp(ens.member(0), t_s, n, self.dt_s, self.polar, self.hold, self.coast,
                       d_min=self.d_min, stencil=self._stencil, reward_model=self.reward_model)
        j0, i0 = _nearest_cell(self.coast.grid, np.isfinite(res.V[0]), x, y)
        return _plan_from_path(self.coast.grid, res.path(j0, i0, 0), t_s, self.dt_s,
                               float(res.V[0, j0, i0]))


class OraclePolicy:
    """Hindsight oracle: one DP on the TRUTH over the whole mission, executed open-loop (§8.2).

    Not a causal policy (it is handed the truth); it provides the upper bound ``J_hind`` of the
    regret. The plan is computed at the first call and returned unchanged at every replan.

    Parameters
    ----------
    truth : WindField  True wind covering ``[0, duration_s]``.
    polar, hold_curve, coast : see :func:`horizon.dp.solve_dp`.
    duration_s : float  [s]  Mission length.
    """

    def __init__(self, truth: WindField, polar: PolarTable, hold_curve: HoldCurve,
                 coast: CoastModel, duration_s: float, dt_s: float = DT_PLAN_S,
                 d_min_m: float = 20e3, reward_model: str = "envelope"):
        self.truth, self.polar, self.hold, self.coast = truth, polar, hold_curve, coast
        self.duration_s, self.dt_s, self.d_min = duration_s, dt_s, d_min_m
        self.reward_model = reward_model
        self._plan: Plan | None = None

    @property
    def dp_value_kwh(self) -> float:
        """DP optimum [kWh] from the start cell (NaN before the first plan)."""
        return float("nan") if self._plan is None else self._plan.value_kwh

    def plan(self, t_s, x, y, provider):
        if self._plan is None:
            n = int(np.ceil(self.duration_s / self.dt_s))
            res = solve_dp(self.truth, t_s, n, self.dt_s, self.polar, self.hold, self.coast,
                           d_min=self.d_min, reward_model=self.reward_model)
            j0, i0 = _nearest_cell(self.coast.grid, np.isfinite(res.V[0]), x, y)
            self._plan = _plan_from_path(self.coast.grid, res.path(j0, i0, 0), t_s, self.dt_s,
                                         float(res.V[0, j0, i0]))
        return self._plan
