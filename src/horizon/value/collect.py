"""Data collection for E0 / V_theta: hindsight values, policy rollouts, track samples.

Everything is organised by *release time* ``s_k`` (a grid of times, e.g. every 3 days):

* :func:`hindsight_maps`: ``V_hind(x, s_k; H)`` for all cells at once (one backward DP on the
  TRUTH per horizon, zero terminal value, 3 h steps): the clairvoyant energy-to-go.
* :func:`rollout_group`: many ships released at ``s_k`` from random cells and flown by the same
  causal policy (B1, forecast control member, no refiner) for ``H_max``; the DP result of a
  replan does not depend on the ship, so it is shared across the group. Records the cumulative
  realised energy [kWh] (true wind, true power model) at 1..``H_max`` days: the
  policy-consistent value ``V_pol(x, s_k; H)``.
* :func:`track_samples`: realised energy-to-go along existing year-run tracks (segment files).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from horizon.dp import build_stencil, solve_dp
from horizon.sim.simulator import SimState, advance, energy_on_truth
from horizon.value.policy import TerminalFnMPCPolicy

__all__ = ["hindsight_maps", "load_track", "rollout_group", "track_samples"]


def hindsight_maps(truth, t0_s: float, horizons_d, polar, hold, coast, stencil=None,
                   dt_s: float = 10800.0, d_min: float = 20e3) -> np.ndarray:
    """``V_hind(., t0; H)`` [kWh] for each ``H`` (days) as ``(len(H), Ny, Nx)`` float32;
    NaN where the cell is not navigable. ``truth`` must cover ``[t0, t0 + max H]``."""
    st = stencil if stencil is not None else build_stencil(coast.grid, dt_s)
    out = []
    for h in horizons_d:
        n = int(round(h * 86400.0 / dt_s))
        r = solve_dp(truth, t0_s, n, dt_s, polar, hold, coast, d_min=d_min, stencil=st)
        v = r.V[0].astype(np.float32)
        out.append(np.where(np.isfinite(v), v, np.nan))
    return np.stack(out)


def rollout_group(weather, truth_win, power_model, coast, polar, hold, s_k: float, cells_ji,
                  h_days: float = 5.0, replan_s: float = 6 * 3600.0, sim_dt_s: float = 900.0,
                  d_min_m: float = 20e3, end_s: float | None = None) -> dict:
    """Fly one B1 ship from each cell of ``cells_ji`` (array (n, 2) of ``(j, i)``) released at
    ``s_k`` [s] for ``h_days``; returns ``x0, y0 (n,)`` and cumulative energy ``E (n, h_days)``
    [kWh] at the end of days 1..h_days (true wind ``truth_win`` covering the window).

    ``weather`` is the forecast source (shared by all ships); ``end_s`` the data end seen by the
    policies (default ``weather.duration_s``).
    """
    g = coast.grid
    end_s = weather.duration_s if end_s is None else end_s
    pol = TerminalFnMPCPolicy(polar, hold, coast, horizon_days=5.0, dp_cache={})
    n_steps = int(round(h_days * 86400.0 / sim_dt_s))
    k0 = int(round(s_k / sim_dt_s))
    cells = np.asarray(cells_ji)
    x0 = g.x0 + cells[:, 1] * g.dx
    y0 = g.y0 + cells[:, 0] * g.dx
    per_day = int(round(86400.0 / sim_dt_s))
    E = np.empty((len(cells), int(h_days)))
    for s in range(len(cells)):
        st = SimState(k0, float(x0[s]), float(y0[s]))
        st.next_replan = s_k
        xs, ys, ve, vn = advance(pol, weather, coast, st, n_steps, end_s, replan_s, sim_dt_s,
                                 d_min_m=d_min_m)
        p = energy_on_truth(truth_win, power_model, s_k, sim_dt_s, xs, ys, ve, vn)
        c = np.cumsum(p) * sim_dt_s / 3600.0
        E[s] = c[per_day - 1::per_day][:E.shape[1]]
    return {"x0": x0, "y0": y0, "E": E}


def load_track(run_dir, sim_dt_s: float = 900.0):
    """Concatenate the segments of a year run: ``(x, y, cum_energy_kwh)`` with ``n+1`` samples
    (position at the start of each step, cumulative energy at the same instants)."""
    parts = []
    for f in sorted(Path(run_dir).glob("seg_*.npz")):
        if not f.with_suffix(".json").exists():
            break
        parts.append(np.load(f))
    if not parts:
        raise FileNotFoundError(run_dir)
    x = np.concatenate([z["x"] for z in parts])
    y = np.concatenate([z["y"] for z in parts])
    p = np.concatenate([z["power_kw"] for z in parts])
    return x, y, np.concatenate([[0.0], np.cumsum(p) * sim_dt_s / 3600.0])


def track_samples(x, y, cum_e, times_s, h_days, sim_dt_s: float = 900.0):
    """Realised energy-to-go along a track.

    Returns ``(keep, xs, ys, E)`` for the release times ``times_s`` whose window
    ``[t, t + max H]`` lies inside the track: ``E (n_keep, len(h_days))`` [kWh]."""
    hmax = max(h_days) * 86400.0
    i0 = np.round(np.asarray(times_s) / sim_dt_s).astype(int)
    keep = (i0 >= 0) & (i0 + int(round(hmax / sim_dt_s)) < len(cum_e))
    i0 = i0[keep]
    E = np.stack([cum_e[i0 + int(round(h * 86400.0 / sim_dt_s))] - cum_e[i0] for h in h_days], 1)
    return keep, x[i0], y[i0], E
