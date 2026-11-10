"""Parametric synthetic power polar (HYPOTHESES, to be replaced by measured polars).

The model is physically motivated but deliberately simple. Every parameter below is a
HYPOTHESIS tuned so that the polar reproduces the characteristics quoted in DES-860 §1.6 and
§2.2.1 (peak ~1500/2100/>2700 kW at 18/20/22 kn, 3 MW cap, beam-reach optimum, U optimum
3-4.5 m/s, narrow angular optimum, negative net power close-hauled at high U). None of the
numbers comes from a measured ship polar.

Model (TWS ``W``, TWA ``theta``, ship speed ``U``)::

    Va      = sqrt(W^2 + 2 W U cos(theta) + kappa U^2)     effective apparent wind [m/s]
    eta     = 1 / (1 + |(theta - theta0)/w|^p) * S(theta)  angular efficiency (beam peak),
                                                         S: close-hauled smoothstep 30->50 deg
    g       = exp(-((U - U0) / sU)^2 / 2)                   ship-speed efficiency (optimum U0)
    P_gen   = softplus_cap(k_turb * eta * g * Va^3) * derate(W)
    P_net   = P_gen - c_drag U^3 - P_up(theta, U, Va)       propulsion/drag and close-hauled loss

``derate`` ramps from 1 at ``derate_start_kn`` to 0 at ``cutout_kn`` (smoothstep).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from horizon.polar.derived import softplus_cap
from horizon.polar.table import KNOT, PolarTable, default_axes

__all__ = ["SyntheticPolarParams", "synthetic_polar"]


@dataclass(frozen=True)
class SyntheticPolarParams:
    """Hypothesised parameters of the synthetic polar (all to be replaced by measurements)."""

    k_turb: float = 1.9  #: turbine gain [kW / (m/s)^3]
    twa_opt_deg: float = 93.0  #: angular optimum theta0 [deg]
    twa_width_deg: float = 22.0  #: angular half-width w of eta (eta = 0.5) [deg]
    twa_exponent: float = 2.0  #: sharpness p of eta [-]
    u_opt: float = 3.75  #: optimum ship speed U0 [m/s] (~7.3 kn)
    u_sigma: float = 1.6  #: width sU of ship-speed efficiency [m/s]
    c_drag: float = 0.12  #: propulsion/drag loss coefficient [kW / (m/s)^3]
    p_up_max: float = 190.0  #: saturation of close-hauled penalty [kW]
    twa_up_deg: float = 35.0  #: close-hauled penalty vanishes above this TWA [deg]
    up_ref: float = 100.0  #: reference U*Va for penalty saturation [(m/s)^2]
    twa_dead_deg: float = 30.0  #: no generation at or below this TWA (close-hauled) [deg]
    twa_full_deg: float = 50.0  #: close-hauled suppression of eta fully released above [deg]
    cut_in_ms: float = 1.5  #: cut-in wind scale of the turbine, tanh(W / cut_in) [m/s]
    u_coupling: float = 0.2  #: weight kappa of ship-speed term in apparent wind [-]
    cap_kw: float = 3000.0  #: generator cap [kW]
    beta: float = 0.02  #: softplus knee sharpness [1/kW]
    derate_start_kn: float = 35.0  #: start of high-wind derating [kn]
    cutout_kn: float = 42.0  #: cut-out (survival, zero generation) [kn]


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def synthetic_polar(params: SyntheticPolarParams | None = None) -> PolarTable:
    """Build the synthetic polar on the spec default grid.

    Parameters
    ----------
    params : SyntheticPolarParams, optional
        Hypothesised parameters (defaults calibrated on DES-860 §2.2.1 figures).

    Returns
    -------
    PolarTable
        ``P[TWS, TWA, U]`` [kW] on TWS 0-50 kn (m/s), TWA 0-180 deg, U 0-10 m/s.
    """
    q = params or SyntheticPolarParams()
    tws, twa, u = default_axes()
    w = tws[:, None, None]
    th = twa[None, :, None]
    s = u[None, None, :]
    c = np.cos(np.radians(th))
    va = np.sqrt(np.maximum(w**2 + 2 * w * s * c + q.u_coupling * s**2, 0.0))
    eta = 1.0 / (1.0 + np.abs((th - q.twa_opt_deg) / q.twa_width_deg) ** q.twa_exponent)
    # Close-hauled suppression: the Lorentzian tail alone would generate power head to wind,
    # contradicting DES-860 §2.2.1 item 4 (net power negative close-hauled, TWA < ~30 deg).
    eta = eta * _smoothstep((th - q.twa_dead_deg) / (q.twa_full_deg - q.twa_dead_deg))
    g0 = np.exp(-0.5 * (q.u_opt / q.u_sigma) ** 2)
    g = np.clip((np.exp(-0.5 * ((s - q.u_opt) / q.u_sigma) ** 2) - g0) / (1.0 - g0), 0.0, None)
    derate = 1.0 - _smoothstep((w / KNOT - q.derate_start_kn) / (q.cutout_kn - q.derate_start_kn))
    p_gen = softplus_cap(q.k_turb * eta * g * va**3, q.cap_kw, q.beta)
    p_gen = p_gen * np.tanh(w / q.cut_in_ms) * derate
    h = np.clip(1.0 - th / q.twa_up_deg, 0.0, 1.0) ** 2
    p_up = q.p_up_max * h * np.tanh(s * va / q.up_ref) * (w > 0)
    p = p_gen - q.c_drag * s**3 - p_up
    return PolarTable(p, tws, twa, u)
