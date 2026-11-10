"""Climatological terminal value of the routing problem (DES-860 §10, phase 1).

Phase-1 terminal value: at the end of the optimisation horizon the ship is worth the energy it
would harvest by station keeping for the remaining horizon under the *climatological* wind of its
position. Per cell ``x``::

    P_clim(x) = mean over archive hours of  P_hold(|W(x, t)|)        [kW]
    V_T(x)    = P_clim(x) * H                                         [kWh],  H in hours

``P_hold(TWS)`` is the best mean power at zero ground velocity: the velocity-space envelope
(:mod:`horizon.polar.envelope`) evaluated at ``v = 0`` (``reward`` = ``max(direct, f_avail * E)``),
which captures both alternating-tack holding and, for the real polar, the stopped ship.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from horizon.polar.envelope import EnvelopeTable
from horizon.weather.fields import WindField

__all__ = ["climatological_hold_power", "hold_power_vs_tws", "terminal_value"]


def hold_power_vs_tws(env: EnvelopeTable) -> tuple[np.ndarray, np.ndarray]:
    """Best station-keeping power per TWS: the envelope reward at ``v = 0``.

    Parameters
    ----------
    env : EnvelopeTable

    Returns
    -------
    tws : numpy.ndarray  [m/s]
    p_hold : numpy.ndarray  [kW]
        NaN where ``v = 0`` is not reachable.
    """
    ip = int(round(-env.vp0 / env.dv))
    tws = env.tws0 + env.dtws * np.arange(env.reward.shape[0])
    return tws, env.reward[:, ip, 0].astype(np.float64)


def climatological_hold_power(winds: WindField | Sequence[WindField],
                              env: EnvelopeTable) -> np.ndarray:
    """Mean station-keeping power per cell over one or several wind archives.

    Parameters
    ----------
    winds : WindField or sequence of WindField
        Archive(s) (e.g. one or several ERA5 months) on a common grid. Every time sample has
        equal weight.
    env : EnvelopeTable
        Polar envelope (see :func:`horizon.polar.envelope.build_envelope`).

    Returns
    -------
    numpy.ndarray, shape (Ny, Nx), float32  [kW]
        ``P_clim``; TWS outside the table is clamped.
    """
    fields = [winds] if isinstance(winds, WindField) else list(winds)
    if not fields:
        raise ValueError("at least one WindField is required")
    tws_ax, p_ax = hold_power_vs_tws(env)
    ok = np.isfinite(p_ax)
    shape = fields[0].uv.shape[1:3]
    acc = np.zeros(shape, dtype=np.float64)
    n = 0
    for f in fields:
        if f.uv.shape[1:3] != shape:
            raise ValueError("all WindFields must share the same grid")
        for k in range(f.uv.shape[0]):
            w = np.hypot(f.uv[k, ..., 0], f.uv[k, ..., 1]).astype(np.float64)
            acc += np.interp(w, tws_ax[ok], p_ax[ok])
            n += 1
    return (acc / n).astype(np.float32)


def terminal_value(p_clim_kw, horizon_h: float):
    """Terminal value [kWh] = climatological hold power [kW] x remaining horizon [h].

    Parameters
    ----------
    p_clim_kw : array_like  [kW]
        Output of :func:`climatological_hold_power`.
    horizon_h : float  [h]
        Time remaining after the end of the optimisation window (>= 0).

    Returns
    -------
    numpy.ndarray  [kWh], float32
    """
    if horizon_h < 0:
        raise ValueError("horizon_h must be >= 0")
    return (np.asarray(p_clim_kw, dtype=np.float64) * float(horizon_h)).astype(np.float32)
