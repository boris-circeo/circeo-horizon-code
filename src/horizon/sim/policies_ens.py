"""Ensemble MPC policy: reduced ensemble + two-stage CVaR DP (DES-860 §5.3.3, §6.3, §8.3)."""

from __future__ import annotations

import time

import numpy as np

from horizon.dp import build_stencil
from horizon.dp.solver import solve_dp
from horizon.dp.stochastic import RiskSpec, solve_stochastic_dp
from horizon.ensemble import reduce_ensemble
from horizon.geo.coast import CoastModel
from horizon.polar.derived import HoldCurve
from horizon.polar.table import PolarTable
from horizon.sim.policies import DT_PLAN_S, _nearest_cell, _plan_from_path

__all__ = ["EnsembleMPCPolicy"]


class EnsembleMPCPolicy:
    """Receding-horizon policy on a reduced ensemble with a non-anticipative 48 h trunk.

    At each replan: forecast ``n_members`` members, reduce them to ``k`` medoid scenarios on the
    window ``[t + split, t + horizon]``, solve :func:`horizon.dp.stochastic.solve_stochastic_dp`
    (trunk on the control member) and return the trunk route as the plan. If the remaining
    horizon is not longer than the split, falls back to a deterministic DP on the control.

    Parameters
    ----------
    polar, hold_curve, coast : see :func:`horizon.dp.solve_dp`.
    horizon_days : float  [d]  Planning horizon.
    n_members : int  Ensemble size requested from the provider.
    k : int or None  Number of scenarios (``None`` = adaptive 5-12).
    gamma, alpha : float  CVaR penalty weight and tail mass.
    split_h : float  [h]  Trunk length (non-anticipativity window).
    dt_s : float  [s]  DP step.
    d_min_m : float  [m]  Coast clearance.
    reduction_tau_d : float  [d]  Lead-time decay of the clustering weights alpha_t.
    terminal_clim_kw : ndarray (Ny, Nx), optional  [kW]  Climatological hold power; terminal value
        at the horizon end is ``terminal_clim_kw * min(terminal_days * 24 h, mission time left)``.
    terminal_days : float  [d]

    Attributes
    ----------
    last_diagnostics : dict or None
        Plain-Python/NumPy summary of the last replan: ``issue_s``, ``members``, ``weights``,
        ``explained_variance``, ``n_modes``, ``distortion_explained``, ``vbar_*`` stats [kWh],
        ``v_t0_kwh``, ``v_mean_at_split_kwh``, ``v_cvar_at_split_kwh``, ``timing_s``.
    """

    def __init__(self, polar: PolarTable, hold_curve: HoldCurve, coast: CoastModel,
                 horizon_days: float = 15.0, n_members: int = 20, k: int | None = 7,
                 gamma: float = 0.3, alpha: float = 0.2, split_h: float = 48.0,
                 dt_s: float = DT_PLAN_S, d_min_m: float = 20e3, reward_model: str = "envelope",
                 reduction_tau_d: float = 7.0, terminal_clim_kw: np.ndarray | None = None,
                 terminal_days: float = 5.0):
        self.polar, self.hold, self.coast = polar, hold_curve, coast
        self.horizon_s = horizon_days * 86400.0
        self.n_members, self.k = n_members, k
        self.risk = RiskSpec(gamma, alpha)
        self.split_s = split_h * 3600.0
        self.dt_s, self.d_min, self.reward_model = dt_s, d_min_m, reward_model
        self.tau_s = reduction_tau_d * 86400.0
        self.terminal_clim_kw = terminal_clim_kw  # [kW] climatological hold power, or None
        self.terminal_days = terminal_days
        self._stencil = build_stencil(coast.grid, dt_s)
        self.last_diagnostics: dict | None = None
        # DPResult of the trunk (``V[n_split]`` = aggregated value v_bar): read by RefinedMPCPolicy
        self.last_result = None

    def plan(self, t_s, x, y, provider):
        grid = self.coast.grid
        n = max(int(np.ceil(min(self.horizon_s, provider.mission_end_s - t_s) / self.dt_s)), 1)
        n_split = int(round(self.split_s / self.dt_s))
        tm = {}
        t = time.perf_counter()
        ens = provider.forecast(issue_s=t_s, horizon_s=n * self.dt_s, n_members=self.n_members,
                                dt_s=self.dt_s)
        tm["forecast"] = time.perf_counter() - t
        control = ens.member(0)
        term = None
        if self.terminal_clim_kw is not None:
            from horizon.polar.climatology import terminal_value
            left_h = max(provider.mission_end_s - (t_s + n * self.dt_s), 0.0) / 3600.0
            term = terminal_value(self.terminal_clim_kw, min(self.terminal_days * 24.0, left_h))
        common = dict(polar=self.polar, hold_curve=self.hold, coast=self.coast,
                      d_min=self.d_min, stencil=self._stencil, reward_model=self.reward_model)
        if n <= n_split + 1 or ens.n_members < 2:  # nothing left to branch on
            t = time.perf_counter()
            res = solve_dp(control, t_s, n, self.dt_s, terminal=term, **common)
            tm["dp"] = time.perf_counter() - t
            self.last_result = res
            j0, i0 = _nearest_cell(grid, np.isfinite(res.V[0]), x, y)
            self.last_diagnostics = {"issue_s": float(t_s), "members": [0], "weights": [1.0],
                                     "v_t0_kwh": float(res.V[0, j0, i0]), "timing_s": tm}
            return _plan_from_path(grid, res.path(j0, i0, 0), t_s, self.dt_s,
                                   float(res.V[0, j0, i0]))
        t = time.perf_counter()
        red = reduce_ensemble(ens, self.k, window_s=(t_s + n_split * self.dt_s, ens.times_s[-1]),
                              tau_s=self.tau_s)
        tm["reduction"] = time.perf_counter() - t
        t = time.perf_counter()
        res = solve_stochastic_dp(red.scenarios(ens), red.weights, control, t_s, n * self.dt_s,
                                  self.dt_s, split_s=n_split * self.dt_s, risk=self.risk,
                                  terminal=term, **common)
        tm["dp"] = time.perf_counter() - t
        self.last_result = res.short
        j0, i0 = _nearest_cell(grid, np.isfinite(res.v_t0), x, y)
        path = res.path(j0, i0)
        je, ie = int(path.j_end[-1]), int(path.i_end[-1])
        vb = res.v_bar[np.isfinite(res.v_bar)]
        self.last_diagnostics = {
            "issue_s": float(t_s), "members": red.members.tolist(),
            "weights": red.weights.tolist(), "explained_variance": red.eof.explained.tolist(),
            "n_modes": int(red.eof.n_modes),
            "distortion_explained": float(red.distortion_explained),
            "vbar_min_kwh": float(vb.min()), "vbar_mean_kwh": float(vb.mean()),
            "vbar_max_kwh": float(vb.max()), "v_t0_kwh": float(res.v_t0[j0, i0]),
            "v_mean_at_split_kwh": float(res.v_mean[je, ie]),
            "v_cvar_at_split_kwh": float(res.v_cvar[je, ie]),
            "scenario_values_at_end_kwh": res.scenario_values[:, je, ie].astype(float).tolist(),
            "timing_s": tm,
        }
        return _plan_from_path(grid, path, t_s, self.dt_s, float(res.v_t0[j0, i0]))
