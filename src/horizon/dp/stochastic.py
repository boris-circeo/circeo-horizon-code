"""Two-stage stochastic DP with a non-anticipative trunk and CVaR aggregation.

Implements the online recursion (DES-860 Annex A.2, §5.3.3, §6.3, §4.9):

1. ``t > t_split``: one deterministic backward DP per scenario ``s`` -> ``V_s(n, t_split)``;
2. at the split, per cell: ``Vbar = sum_s w_s V_s - gamma (sum_s w_s V_s - CVaR_alpha({V_s}))``
   (= ``(1-gamma) E + gamma CVaR``: expectation penalised by the lower-tail dispersion);
3. ``t <= t_split``: ONE deterministic DP on the short-range field with terminal ``Vbar``.

Non-anticipativity is structural: the trunk is a single backward recursion on one field, so a
single decision is shared by all scenarios until the split.

CVaR convention: lower tail of the (energy) value, ``CVaR_alpha`` = weighted mean of the worst
``alpha`` probability mass (fractional atom at the boundary), so ``CVaR <= E`` and ``Vbar`` is
non-increasing in ``gamma``. Cells that are infeasible (``-inf``) in any scenario of positive
weight are set to ``-inf`` in ``Vbar``: a common-trunk position must remain feasible in every
scenario (conservative; in practice infeasibility is scenario-independent: land and buffer).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from horizon.dp.solver import DPResult, Path, solve_dp
from horizon.dp.stencil import Stencil, build_stencil
from horizon.geo.coast import CoastModel
from horizon.polar.derived import HoldCurve
from horizon.polar.table import PolarTable
from horizon.weather.fields import WindField

__all__ = ["RiskSpec", "StochasticDPResult", "aggregate_values", "solve_stochastic_dp",
           "weighted_cvar"]


@dataclass(frozen=True)
class RiskSpec:
    """Risk aggregation parameters (DES-860 §4.9.2, §6.3.3).

    Attributes
    ----------
    gamma : float  Penalty weight in [0, 1]; 0 = risk neutral (expectation only).
    alpha : float  Tail probability in (0, 1] (0.2 = worst 20 %).
    """

    gamma: float = 0.3
    alpha: float = 0.2

    def __post_init__(self):
        if not 0.0 <= self.gamma <= 1.0:
            raise ValueError("gamma must be in [0, 1]")
        if not 0.0 < self.alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")


def weighted_cvar(values: np.ndarray, weights: np.ndarray, alpha: float) -> np.ndarray:
    """Lower-tail CVaR of a discrete weighted distribution, along axis 0.

    ``CVaR_alpha = (1/alpha) * integral_0^alpha q(u) du`` (Rockafellar-Uryasev), i.e. the
    weighted mean of the worst ``alpha`` mass, splitting the boundary atom.

    Parameters
    ----------
    values : ndarray (S, ...)  Outcomes (``-inf`` allowed; the result is ``-inf`` if the tail
        contains one).
    weights : ndarray (S,)  Probabilities, sum to 1.
    alpha : float  Tail mass in (0, 1].

    Returns
    -------
    ndarray (...)  Same units as ``values``.
    """
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    order = np.argsort(v, axis=0, kind="stable")
    vs = np.take_along_axis(v, order, axis=0)
    ws = np.take_along_axis(np.broadcast_to(w.reshape((-1,) + (1,) * (v.ndim - 1)), v.shape),
                            order, axis=0)
    before = np.cumsum(ws, axis=0) - ws
    eff = np.clip(np.minimum(ws, alpha - before), 0.0, None)
    with np.errstate(invalid="ignore"):
        return np.where(eff > 0, eff * vs, 0.0).sum(axis=0) / alpha


def aggregate_values(values: np.ndarray, weights: np.ndarray, risk: RiskSpec):
    """Annex A.2 aggregation ``E - gamma (E - CVaR)`` along axis 0.

    Parameters
    ----------
    values : ndarray (S, ...)  [kWh]  ``V_s`` at the split.
    weights : ndarray (S,)  Scenario probabilities.
    risk : RiskSpec

    Returns
    -------
    vbar, mean, cvar : ndarray (...)  [kWh]  ``-inf`` where any positive-weight scenario is
        infeasible (``mean`` / ``cvar`` also ``-inf`` there).
    """
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    wb = w.reshape((-1,) + (1,) * (v.ndim - 1))
    pos = wb > 0
    feasible = np.all(np.isfinite(v) | ~pos, axis=0)
    vf = np.where(np.isfinite(v), v, 0.0)
    mean = np.where(pos, wb * vf, 0.0).sum(axis=0)
    cvar = weighted_cvar(vf, w, risk.alpha)
    vbar = np.where(feasible, mean - risk.gamma * (mean - cvar), -np.inf)
    return vbar, np.where(feasible, mean, -np.inf), np.where(feasible, cvar, -np.inf)


@dataclass(frozen=True)
class StochasticDPResult:
    """Output of :func:`solve_stochastic_dp`.

    Attributes
    ----------
    v_bar : float32 (Ny, Nx)  [kWh]  Aggregated value at the split time (interface to the
        continuous refiner, Annex A.4).
    v_mean, v_cvar : float32 (Ny, Nx)  [kWh]  Weighted mean and CVaR of the scenario values.
    scenario_values : float32 (S, Ny, Nx)  [kWh]  ``V_s(., t_split)``.
    weights : float64 (S,)
    short : DPResult  Trunk DP over ``[t0, t_split]`` (single policy for all scenarios).
    split_time_s : float  [s since epoch]
    risk : RiskSpec
    """

    v_bar: np.ndarray
    v_mean: np.ndarray
    v_cvar: np.ndarray
    scenario_values: np.ndarray
    weights: np.ndarray
    short: DPResult
    split_time_s: float
    risk: RiskSpec

    @property
    def v_t0(self) -> np.ndarray:
        """Value at ``t0`` [kWh] (Ny, Nx): trunk energy + ``v_bar`` at the split."""
        return self.short.V[0]

    def path(self, j0: int, i0: int) -> Path:
        """First-stage (trunk) route from cell ``(j0, i0)`` at ``t0`` up to the split."""
        return self.short.path(j0, i0, 0)

    def expected_value_at_split(self, j: int, i: int) -> float:
        """Expected scenario value-to-go [kWh] at split cell ``(j, i)``."""
        return float(self.v_mean[j, i])


def solve_stochastic_dp(scenarios: Sequence[WindField], weights: Sequence[float],
                        deterministic_short: WindField, t0_s: float, horizon_s: float,
                        dt_s: float, polar: PolarTable, hold_curve: HoldCurve, coast: CoastModel,
                        split_s: float = 48 * 3600.0, risk: RiskSpec | None = None,
                        terminal: np.ndarray | Sequence[np.ndarray] | None = None,
                        d_min: float = 20e3, u_bounds=(0.5, 8.0), stencil: Stencil | None = None,
                        reward_model: str = "envelope") -> StochasticDPResult:
    """Two-stage DP: common trunk on ``[t0, t0 + split_s]``, scenario branches up to the horizon.

    Parameters
    ----------
    scenarios : sequence of WindField  Reduced ensemble (medoid members) [m/s]; each must cover
        ``[t0 + split_s, t0 + horizon_s]`` (clamped otherwise).
    weights : sequence (S,)  Scenario probabilities, sum to 1.
    deterministic_short : WindField  Short-range field (control member) for the trunk.
    t0_s : float  [s since epoch]  Start of the horizon.
    horizon_s, dt_s, split_s : float  [s]  Horizon, DP step, trunk length (multiples of ``dt_s``).
    polar, hold_curve, coast, d_min, u_bounds, stencil, reward_model : see
        :func:`horizon.dp.solve_dp`.
    risk : RiskSpec, optional  Default ``RiskSpec()`` (gamma 0.3, alpha 0.2).
    terminal : ndarray (Ny, Nx) or sequence of S such arrays, optional  [kWh]  Value at the
        horizon (shared or per scenario; the learned ``V_theta`` of Annex A.2). Default 0.

    Returns
    -------
    StochasticDPResult
    """
    risk = RiskSpec() if risk is None else risk
    w = np.asarray(weights, float)
    if len(scenarios) == 0 or w.shape != (len(scenarios),) or not np.isclose(w.sum(), 1.0):
        raise ValueError("weights must have one entry per scenario and sum to 1")
    n_tot, n_split = int(round(horizon_s / dt_s)), int(round(split_s / dt_s))
    if not 1 <= n_split < n_tot:
        raise ValueError("need 1 <= split < horizon (in DP steps)")
    st = stencil if stencil is not None else build_stencil(coast.grid, dt_s, u_bounds)
    t_split = t0_s + n_split * dt_s
    per_scen = terminal is not None and not isinstance(terminal, np.ndarray)
    vals = np.empty((len(scenarios),) + coast.grid.shape, dtype=np.float32)
    for s, wind in enumerate(scenarios):
        term = terminal[s] if per_scen else terminal
        res = solve_dp(wind, t_split, n_tot - n_split, dt_s, polar, hold_curve, coast,
                       terminal=term, d_min=d_min, stencil=st, reward_model=reward_model)
        vals[s] = res.V[0]
    vbar, mean, cvar = aggregate_values(vals, w, risk)
    short = solve_dp(deterministic_short, t0_s, n_split, dt_s, polar, hold_curve, coast,
                     terminal=vbar.astype(np.float32), d_min=d_min, stencil=st,
                     reward_model=reward_model)
    return StochasticDPResult(vbar.astype(np.float32), mean.astype(np.float32),
                              cvar.astype(np.float32), vals, w, short, t_split, risk)
