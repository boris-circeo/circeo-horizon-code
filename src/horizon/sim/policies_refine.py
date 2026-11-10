"""Refined receding-horizon policy: DP plan + continuous NLP refinement (DES-860 §4.10, §7.5).

The base policy (e.g. :class:`~horizon.sim.policies.DeterministicMPCPolicy`) solves the coarse DP
and exposes its :class:`~horizon.dp.solver.DPResult` as ``last_result``. This wrapper refines the
first ``horizon_h`` hours of the DP route at ``dt_s`` resolution with
:func:`horizon.refine.refine_plan`, using the DP value at ``t + horizon_h`` as terminal value, and
returns an ordinary :class:`~horizon.sim.policies.Plan` (arc destinations every ``dt_s``), which
the unmodified simulator executes. If the refinement is not possible the base plan is returned.
"""

from __future__ import annotations

import numpy as np

from horizon.dp.solver import _envelope_for
from horizon.refine import refine_plan
from horizon.sim.policies import Plan

__all__ = ["RefinedMPCPolicy"]


class RefinedMPCPolicy:
    """Wrap a DP-based policy and refine the first hours of its plan.

    Parameters
    ----------
    base_policy : policy with attributes ``last_result`` (DPResult), ``coast``, ``polar``,
        ``hold``, ``d_min`` (as :class:`~horizon.sim.policies.DeterministicMPCPolicy`).
    horizon_h : float [h]  Refined horizon (48). dt_s : float [s]  Refiner stage (1800).
    wind_dt_s : float [s]  Time step of the forecast requested for the refiner (3600).
    rho : (float, float) [kWh/(m/s)^2]  Velocity-increment / curvature penalties (100, 100).
    max_iter, max_cpu_s : IPOPT limits. margin_m : float [m]  Bounding-box margin.

    Attributes
    ----------
    last_refine : RefineResult or None  Latest refinement (None if the base plan was returned).
    results : list of RefineResult  All refinements of the mission (diagnostics).
    """

    def __init__(self, base_policy, horizon_h: float = 48.0, dt_s: float = 1800.0,
                 wind_dt_s: float = 3600.0, rho=(100.0, 100.0), max_iter: int = 200,
                 max_cpu_s: float = 20.0, margin_m: float = 120e3):
        self.base = base_policy
        self.horizon_s = horizon_h * 3600.0
        self.dt_s = dt_s
        self.wind_dt_s = wind_dt_s
        self.rho = rho
        self.max_iter, self.max_cpu_s, self.margin_m = max_iter, max_cpu_s, margin_m
        self.envelope = _envelope_for(base_policy.polar, base_policy.hold.f_avail)
        self.last_refine = None
        self.results: list = []

    def plan(self, t_s, x, y, provider) -> Plan:
        base_plan = self.base.plan(t_s, x, y, provider)
        self.last_refine = None
        res = self.base.last_result
        dp_dt = base_plan.dt_s
        h = min(self.horizon_s, base_plan.x.size * dp_dt, provider.mission_end_s - t_s)
        k_dp = int(np.floor(h / dp_dt + 1e-9))
        n = int(np.floor(k_dp * dp_dt / self.dt_s + 1e-9))
        if k_dp < 1 or n < 4:
            return base_plan
        h = n * self.dt_s
        ens = provider.forecast(issue_s=t_s, horizon_s=h, n_members=1, dt_s=self.wind_dt_s)
        tx = np.concatenate([[t_s], t_s + dp_dt * np.arange(1, base_plan.x.size + 1)])
        tn = t_s + self.dt_s * np.arange(n + 1)
        warm = (np.interp(tn, tx, np.concatenate([[x], base_plan.x])),
                np.interp(tn, tx, np.concatenate([[y], base_plan.y])))
        term = np.where(np.isfinite(res.V[k_dp]), res.V[k_dp], -np.inf).astype(float)
        r = refine_plan(ens.member(0), x, y, t_s, term, self.envelope, self.base.coast, warm,
                        horizon_s=h, dt_s=self.dt_s, d_min=self.base.d_min, rho=self.rho,
                        max_iter=self.max_iter, max_cpu_s=self.max_cpu_s,
                        margin_m=self.margin_m)
        self.last_refine = r
        self.results.append(r)
        return Plan(t_s, self.dt_s, r.x[1:], r.y[1:], r.objective_kwh)


class _TruthProvider:
    """Provider whose "forecast" is the truth (hindsight), sampled at the requested times."""

    def __init__(self, truth, mission_end_s: float):
        self.truth = truth
        self.mission_end_s = float(mission_end_s)

    def forecast(self, issue_s, horizon_s, n_members=1, dt_s=10800.0, seed_offset=0):
        from horizon.dp.solver import resample_wind
        from horizon.weather.fields import Ensemble

        t = issue_s + np.arange(int(round(horizon_s / dt_s)) + 1) * dt_s
        uv = resample_wind(self.truth, t)[None]
        return Ensemble(self.truth.grid, self.truth.epoch, float(issue_s), t, uv, np.ones(1))


class OracleRefinedPolicy:
    """Hindsight policy with receding refinement (``Oracle_REF``, upper bound for REF policies).

    At every replan: DP on the TRUTH from now to the mission end (terminal 0), then refinement of
    the first 48 h on the truth wind, exactly as :class:`RefinedMPCPolicy` but with perfect
    information. Not causal (it is handed the truth).

    Parameters
    ----------
    truth : WindField  True wind covering the mission.
    polar, hold_curve, coast : see :func:`horizon.dp.solve_dp`.
    duration_s : float  [s]  Mission length. Other keywords go to :class:`RefinedMPCPolicy`.
    """

    def __init__(self, truth, polar, hold_curve, coast, duration_s: float, d_min_m: float = 20e3,
                 **refine_kw):
        from horizon.sim.policies import DeterministicMPCPolicy

        self.truth = truth
        base = DeterministicMPCPolicy(polar, hold_curve, coast,
                                      horizon_days=duration_s / 86400.0 + 1.0, d_min_m=d_min_m)
        self.refined = RefinedMPCPolicy(base, **refine_kw)

    @property
    def results(self):
        return self.refined.results

    def plan(self, t_s, x, y, provider) -> Plan:
        return self.refined.plan(t_s, x, y, _TruthProvider(self.truth, provider.mission_end_s))
