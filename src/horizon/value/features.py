"""Features of the learned terminal value V_theta (DES-860 D2, PoC scale).

A sample is a *decision state* ``(x, y, tau)``: the ship is at ``(x, y)`` [m, grid frame] at time
``tau`` [s since epoch] and the target is the energy [kWh] harvested over ``[tau, tau + H_T]``.
Features available at decision time ``tau - H_T`` (the DP replan that would use V_theta as the
terminal value of its ``H_T`` window):

* position ``x_km, y_km`` (projected), ``sin/cos`` of the day of year of ``tau``;
* ``clim_kw``: climatological hold power at the position (months excluded by the caller);
* ``sdf_km``: distance to coast;
* forecast fields from the control member issued at ``tau - H_T`` over the valid window
  ``[tau, tau + H_T]`` (leads ``H_T .. 2 H_T``): mean hold power ``fc_hold``, mean of the first
  / last 40 % of the window ``fc_hold_early`` / ``fc_hold_late``, mean and temporal std of
  TWS, and a spatially smoothed (7 x 7 cells) ``fc_hold_smooth``.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import map_coordinates, uniform_filter

__all__ = ["FC_NAMES", "FEATURE_NAMES", "feature_matrix", "forecast_feature_fields",
           "leave_month_out_mask", "month_of"]

FC_NAMES = ("fc_hold", "fc_hold_early", "fc_hold_late", "fc_tws", "fc_tws_std", "fc_hold_smooth")
FEATURE_NAMES = ("x_km", "y_km", "sin_doy", "cos_doy", "clim_kw", "sdf_km") + FC_NAMES


def forecast_feature_fields(times_s, uv, win_start_s: float, win_end_s: float, tws_ax,
                            p_ax) -> np.ndarray:
    """Forecast-derived feature fields over the valid window.

    Parameters
    ----------
    times_s : (T,) valid times [s]. uv : (T, Ny, Nx, 2) wind [m/s] (one member).
    win_start_s, win_end_s : window [s]; valid times inside it are used (the nearest ones if the
        window is not covered, so that a truncated forecast never raises).
    tws_ax, p_ax : hold power curve ``P_hold(TWS)`` [kW] (NaN-free abscissae).

    Returns
    -------
    (len(FC_NAMES), Ny, Nx) float32, in the order of :data:`FC_NAMES`.
    """
    t = np.asarray(times_s, float)
    sel = np.flatnonzero((t >= win_start_s - 1e-6) & (t <= win_end_s + 1e-6))
    if sel.size == 0:
        sel = np.array([int(np.argmin(np.abs(t - 0.5 * (win_start_s + win_end_s))))])
    w = np.hypot(uv[sel, ..., 0], uv[sel, ..., 1]).astype(np.float64)
    p = np.interp(w, tws_ax, p_ax)
    n = sel.size
    ne = max(int(round(0.4 * n)), 1)
    hold = p.mean(0)
    out = np.stack([hold, p[:ne].mean(0), p[-ne:].mean(0), w.mean(0), w.std(0),
                    uniform_filter(hold, size=7, mode="nearest")])
    return out.astype(np.float32)


def month_of(tau_s, epoch) -> np.ndarray:
    """Calendar month (1-12) of times ``tau_s`` [s since ``epoch``]."""
    t = np.datetime64(epoch, "s") + (np.asarray(tau_s, float) * 1e3).astype("timedelta64[ms]")
    return (t.astype("datetime64[M]").astype(int) % 12 + 1).astype(int)


def leave_month_out_mask(tau_s, epoch, month: int, buffer_days: float = 5.0) -> np.ndarray:
    """Boolean mask of the samples allowed in the TRAINING set of the fold that holds out
    ``month``: ``tau`` outside ``[month start - buffer, month end + buffer)`` (the buffer is the
    target horizon, so that no training target window overlaps the held-out month)."""
    tau = np.asarray(tau_s, float)
    y = int(str(np.datetime64(epoch, "Y")))
    e0, sec = np.datetime64(epoch, "s"), np.timedelta64(1, "s")
    a = (np.datetime64(f"{y}-{month:02d}-01T00:00:00", "s") - e0) / sec
    b = (np.datetime64(f"{y + (month == 12)}-{month % 12 + 1:02d}-01T00:00:00", "s") - e0) / sec
    buf = buffer_days * 86400.0
    return (tau < a - buf) | (tau >= b + buf)


def _bilinear(field, grid, x, y):
    fi, fj = (np.asarray(x) - grid.x0) / grid.dx, (np.asarray(y) - grid.y0) / grid.dx
    return map_coordinates(field, [fj, fi], order=1, mode="nearest")


def feature_matrix(grid, x, y, tau_s, epoch, clim_kw, sdf, fc_fields) -> np.ndarray:
    """Feature matrix ``(n, len(FEATURE_NAMES))`` float32 of samples at ``(x, y)`` [m] at ``tau_s``.

    Parameters
    ----------
    grid : Grid. x, y : (n,) [m]. tau_s : (n,) or scalar [s since ``epoch``].
    clim_kw, sdf : (Ny, Nx) climatological hold power [kW], distance to coast [m].
    fc_fields : (len(FC_NAMES), Ny, Nx) for a scalar ``tau_s``, or (n, len(FC_NAMES), Ny, Nx)
        (one stack per sample; use sparingly) -- or a callable ``f(idx) -> stack``.
    """
    x = np.atleast_1d(np.asarray(x, float))
    y = np.atleast_1d(np.asarray(y, float))
    n = x.size
    tau = np.broadcast_to(np.asarray(tau_s, float), (n,))
    e = np.datetime64(epoch, "s")
    doy0 = float((e.astype("datetime64[D]") - e.astype("datetime64[Y]").astype("datetime64[D]"))
                 .astype(int))
    doy = doy0 + tau / 86400.0
    ang = 2.0 * np.pi * (doy % 365.25) / 365.25
    cols = [x / 1e3, y / 1e3, np.sin(ang), np.cos(ang), _bilinear(clim_kw, grid, x, y),
            _bilinear(sdf, grid, x, y) / 1e3]
    fc = np.asarray(fc_fields)
    for q in range(len(FC_NAMES)):
        if fc.ndim == 3:
            cols.append(_bilinear(fc[q], grid, x, y))
        else:
            cols.append(np.array([_bilinear(fc[s, q], grid, x[s:s + 1], y[s:s + 1])[0]
                                  for s in range(n)]))
    return np.stack(cols, axis=1).astype(np.float32)
