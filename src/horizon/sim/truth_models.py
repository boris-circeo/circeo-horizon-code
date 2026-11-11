"""True-power models that may differ from the router's polar (Sprint 5, WP3 / A3).

The router always keeps the NOMINAL BETA polar (DP, envelope, refiner). The simulator values the
executed track with a TRUTH power model built here, optionally from a perturbed polar:

* ``scale``: multiplies the POSITIVE power (``p > 0``) of every node (0.9 / 1.1: the real ship
  produces 10 % less / more than the router believes); costs (negative power) are untouched;
* ``twa_shift_deg``: shifts the productive lobe in TWA: ``P_true(TWA) = P_nominal(TWA - shift)``
  (positive = lobe moves towards downwind), rounded to the polar's TWA axis step (edge nodes are
  replicated; infeasible nodes move with the lobe).

The truth envelope and hold curve are rebuilt from the perturbed polar (same ``build_envelope`` /
``hold_power_curve`` defaults as the router), so with ``scale = 1`` and ``shift = 0`` the result is
the nominal model exactly. "Manoeuvre-aware truth" is the simulator's manoeuvre model
(:class:`horizon.sim.manoeuvre.ManoeuvreModel`), independent of this module.
"""

from __future__ import annotations

import numpy as np

from horizon.polar import hold_power_curve
from horizon.polar.envelope import build_envelope
from horizon.polar.table import PolarTable
from horizon.sim.power import DirectPowerModel, EnvelopePowerModel, FeasiblePowerModel

__all__ = ["perturb_polar", "make_power_model"]


def perturb_polar(polar: PolarTable, scale: float = 1.0, twa_shift_deg: float = 0.0) -> PolarTable:
    """Polar with scaled positive power and a shifted productive lobe (see module docstring)."""
    p = np.array(polar.p, dtype=np.float32)
    feas = np.array(polar.feasible, dtype=bool)
    if twa_shift_deg:
        step = float(polar.twa[1] - polar.twa[0])
        k = int(round(twa_shift_deg / step))
        idx = np.clip(np.arange(polar.twa.size) - k, 0, polar.twa.size - 1)
        p = p[:, idx, :]
        feas = feas[:, idx, :]
    if scale != 1.0:
        with np.errstate(invalid="ignore"):
            p = np.where(p > 0, p * np.float32(scale), p)
    return PolarTable(p, polar.tws, polar.twa, polar.u, strict=False, feasible=feas,
                      meta=polar.meta, p_bounds=(polar.p_bounds[0], max(polar.p_bounds[1],
                                                                       3000.0 * max(scale, 1.0))))


def make_power_model(polar: PolarTable, scale: float = 1.0, twa_shift_deg: float = 0.0):
    """``FeasiblePowerModel(Envelope(fallback=Direct))`` of the (perturbed) polar."""
    pp = perturb_polar(polar, scale, twa_shift_deg) if (scale != 1.0 or twa_shift_deg) else polar
    hold = hold_power_curve(pp)
    env = build_envelope(pp)
    return FeasiblePowerModel(EnvelopePowerModel(env, fallback=DirectPowerModel(pp, hold)))
