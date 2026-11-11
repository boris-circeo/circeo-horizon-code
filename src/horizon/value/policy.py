"""B1 variants for the value-function work: shared DP across ships, learned terminal value."""

from __future__ import annotations

import numpy as np

from horizon.dp import solve_dp
from horizon.sim.policies import (
    DeterministicMPCPolicy,
    _hold_plan,
    _plan_from_path,
    _safe_start,
)

__all__ = ["TerminalFnMPCPolicy"]


class TerminalFnMPCPolicy(DeterministicMPCPolicy):
    """:class:`DeterministicMPCPolicy` with an optional callable terminal value and a DP cache.

    Parameters
    ----------
    terminal_fn : callable ``f(t_s, tau_s, provider) -> (Ny, Nx) [kWh]`` or None. If given it
        replaces the climatological terminal value (``tau_s`` = end of the DP window).
    dp_cache : dict or None. The DP result depends on ``(t_s, n_steps)`` only, not on the ship
        position: ships released together share it (rollout collection). The cache must only be
        shared between ships that see the same forecasts.
    Other arguments: see :class:`DeterministicMPCPolicy`.
    """

    def __init__(self, *args, terminal_fn=None, dp_cache: dict | None = None, **kw):
        super().__init__(*args, **kw)
        self.terminal_fn = terminal_fn
        self.dp_cache = dp_cache

    def plan(self, t_s, x, y, provider):
        n = max(int(np.ceil(min(self.horizon_s, provider.mission_end_s - t_s) / self.dt_s)), 1)
        key = (round(float(t_s), 3), n)
        res = self.dp_cache.get(key) if self.dp_cache is not None else None
        if res is None:
            ens = provider.forecast(issue_s=t_s, horizon_s=n * self.dt_s, n_members=1,
                                    dt_s=self.dt_s)
            term = None
            if self.terminal_fn is not None:
                term = self.terminal_fn(t_s, t_s + n * self.dt_s, provider)
            elif self.terminal_clim_kw is not None:
                from horizon.polar.climatology import terminal_value
                left_h = max(provider.mission_end_s - (t_s + n * self.dt_s), 0.0) / 3600.0
                term = terminal_value(self.terminal_clim_kw, min(self.terminal_days * 24.0, left_h))
            res = solve_dp(ens.member(0), t_s, n, self.dt_s, self.polar, self.hold, self.coast,
                           terminal=term, d_min=self.d_min, stencil=self._stencil,
                           reward_model=self.reward_model)
            if self.dp_cache is not None:
                self.dp_cache[key] = res
        self.last_result = res
        st = _safe_start(self.coast, self.d_min, np.isfinite(res.V[0]),
                         lambda j, i: res.path(j, i, 0), x, y)
        if st is None:
            return _hold_plan(t_s, self.dt_s, x, y)
        j0, i0, path = st
        return _plan_from_path(self.coast.grid, path, t_s, self.dt_s, float(res.V[0, j0, i0]))
