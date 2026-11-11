"""Sprint-5 baselines and forecast transforms (hypothesis register E-11 / E-12 / H-9-1).

* :class:`ForecastTransformPolicy`: runs any policy on a TRANSFORMED forecast: the ensemble MEAN
  (``B1m``: tests whether ensemble gains are only "the mean beats the control") or a lead-blended
  forecast (control up to ``blend_h``, ensemble mean beyond).
* :class:`GreedyPolicy`: 20-line routers v1 dismissed. ``mode="hold24"``: go to the cell of best
  mean forecast station-keeping power over the next ``window_h`` hours that is reachable within
  ``reach_h`` hours (straight chord clear of the coast), then hold / track it at the next replan.
  ``mode="maxwind"``: same but the score is the mean forecast TWS (capped at ``tws_cap``, since
  the ship saturates at rated power) of the reachable cell.
* :func:`storm_penalty_polar`: router polar / hold curve with a steep penalty above a storm
  wind speed (``survival constraint``, penalty form of a ban; the truth power is untouched).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from horizon.geo.coast import segment_min_bilinear
from horizon.polar.table import PolarTable
from horizon.sim.policies import Plan
from horizon.weather.fields import Ensemble

__all__ = ["ForecastTransformPolicy", "GreedyPolicy", "storm_penalty_polar"]

KN = 0.514444


class _MeanProvider:
    def __init__(self, provider, n_members: int, blend_h: float | None):
        self.p, self.n, self.blend_s = provider, n_members, blend_h
        self.mission_end_s = provider.mission_end_s
        self.now_s = provider.now_s

    def forecast(self, issue_s, horizon_s, n_members=1, dt_s=10800.0, seed_offset=0):
        e = self.p.forecast(issue_s, horizon_s, self.n, dt_s=dt_s, seed_offset=seed_offset)
        mean = e.uv.mean(axis=0, dtype=np.float64)
        if self.blend_s is not None:
            lead = e.times_s - self.now_s
            use_ctrl = (lead <= self.blend_s * 3600.0)[:, None, None, None]
            mean = np.where(use_ctrl, e.uv[0], mean)
        return Ensemble(e.grid, e.epoch, e.issue_s, e.times_s, mean[None].astype(np.float32),
                        np.ones(1))


class ForecastTransformPolicy:
    """Run ``inner`` on the mean of ``n_members`` members (``blend_h``: control up to that lead)."""

    def __init__(self, inner, n_members: int = 10, blend_h: float | None = None):
        self.inner, self.n_members, self.blend_h = inner, n_members, blend_h

    def plan(self, t_s, x, y, provider):
        return self.inner.plan(t_s, x, y, _MeanProvider(provider, self.n_members, self.blend_h))

    def __getattr__(self, name):  # n_dp_fallback, results, ...
        return getattr(self.__dict__["inner"], name)


class GreedyPolicy:
    """Greedy "best reachable cell" router (see module docstring)."""

    def __init__(self, hold_curve, coast, mode: str = "hold24", reach_h: float = 24.0,
                 window_h: float = 24.0, d_min_m: float = 20e3, speed: float = 6.0,
                 dt_s: float = 10800.0, tws_cap: float = 14.0):
        if mode not in ("hold24", "maxwind"):
            raise ValueError(mode)
        self.hold, self.coast, self.mode = hold_curve, coast, mode
        self.reach_s, self.window_s = reach_h * 3600.0, window_h * 3600.0
        self.d_min, self.speed, self.dt_s, self.cap = d_min_m, speed, dt_s, tws_cap
        self.n_dp_fallback = 0

    def plan(self, t_s, x, y, provider):
        g = self.coast.grid
        n = max(int(np.ceil(min(self.reach_s + self.window_s, provider.mission_end_s - t_s)
                            / self.dt_s)), 1)
        ens = provider.forecast(issue_s=t_s, horizon_s=n * self.dt_s, n_members=1, dt_s=self.dt_s)
        uv = ens.uv[0]
        sel = ens.times_s >= t_s - 1e-6
        tws = np.hypot(uv[..., 0], uv[..., 1])[sel]
        t_loc = ens.times_s[sel]
        X, Y = g.xy_mesh()
        dist = np.hypot(X - x, Y - y)
        arr = dist / self.speed                      # arrival time per cell [s]
        reach = (dist <= self.speed * self.reach_s) & (self.coast.sdf >= self.d_min)
        if self.mode == "hold24":
            pw = np.interp(tws, self.hold.tws, self.hold.p_hold)
        else:
            pw = np.minimum(tws, self.cap)
        k_arr = np.clip(np.searchsorted(t_loc - t_s, arr), 0, t_loc.size - 1)
        w_end = np.minimum(arr + self.window_s, t_loc[-1] - t_s)
        score = np.full(g.shape, -np.inf)
        cum = np.cumsum(pw, axis=0)
        k_end = np.clip(np.searchsorted(t_loc - t_s, w_end), 0, t_loc.size - 1)
        jj, ii = np.nonzero(reach)
        c0 = np.where(k_arr[jj, ii] > 0, cum[k_arr[jj, ii] - 1, jj, ii], 0.0)
        cnt = np.maximum(k_end[jj, ii] - k_arr[jj, ii] + 1, 1)
        score[jj, ii] = (cum[k_end[jj, ii], jj, ii] - c0) / cnt
        order = np.argsort(-score, axis=None)
        tgt = (x, y)
        for flat in order[:400]:  # best first; chord must clear the coast
            j, i = np.unravel_index(flat, g.shape)
            if not np.isfinite(score[j, i]):
                break
            xd, yd = X[j, i], Y[j, i]
            m = segment_min_bilinear(self.coast.sdf, g.x0, g.y0, g.dx, x, y, xd, yd)
            if m >= self.d_min - 1.0:
                tgt = (float(xd), float(yd))
                break
        d = float(np.hypot(tgt[0] - x, tgt[1] - y))
        m = max(int(np.ceil(d / (self.speed * self.dt_s))) + 1, 2)
        s = np.minimum(self.speed * self.dt_s * np.arange(1, m + 1), d)
        f = s / d if d > 0 else np.zeros(m)
        return Plan(t_s, self.dt_s, x + f * (tgt[0] - x), y + f * (tgt[1] - y))


def storm_penalty_polar(polar: PolarTable, hold, storm_kn: float = 45.0,
                        penalty_kw: float = -1.0e4):
    """(polar, hold curve) of the router with power ``penalty_kw`` for TWS > ``storm_kn``."""
    thr = storm_kn * KN
    p = np.array(polar.p, np.float32)
    bad = (polar.tws > thr)[:, None, None] & polar.feasible
    pen = penalty_kw - 200.0 * polar.u[None, None, :] * np.ones_like(p)  # non-degenerate hull
    p[bad] = pen[bad]
    pp = PolarTable(p, polar.tws, polar.twa, polar.u, strict=False, feasible=polar.feasible,
                    meta=polar.meta, p_bounds=(min(polar.p_bounds[0], penalty_kw * 1.01),
                                               polar.p_bounds[1]))
    hp = np.array(hold.p_hold, np.float32)
    hp[hold.tws > thr] = penalty_kw
    return pp, replace(hold, p_hold=hp)
