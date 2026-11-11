"""Manoeuvre production losses charged by the simulator (Sprint 5, "v2 environment").

Client remark: abrupt heading changes necessarily reduce production during the manoeuvre. The
simulator detects, on the EXECUTED track (one commanded heading per integration step), three kinds
of events between consecutive moving steps ``s-1 -> s``:

* **tack**: the signed TWA changes sign through head-to-wind (the shorter heading arc between the
  two steps crosses TWA = 0; ``|rel_prev| + |rel_cur| < 180``);
* **gybe**: idem through downwind (TWA = 180; ``|rel_prev| + |rel_cur| > 180``);
* **large turn**: no sign change but ``|heading change| > turn_deg`` (default 30 deg) within a step.

A wind shift that moves the wind across the ship's axis counts as a tack/gybe as well (the ship has
to manoeuvre). During ``tau`` (tack 4 min, gybe 3 min, turn 2 min; ``tau_scale`` multiplies all) the
POSITIVE power is multiplied by ``rho`` (0.3): the loss charged to step ``s`` is
``(1 - rho) * min(tau/dt, 1) * max(P, 0)`` per event (negative power, i.e. a cost, is not
relieved), plus an optional fixed energy penalty ``fixed_kwh`` per event. Hold steps (ground speed
< 0.5 m/s) have no heading: they reset the detector (entering / leaving station keeping is not
charged; the hold curve already contains its own tack mixing).

No double counting with the envelope. The DP envelope / hold curve contain an AVAILABILITY factor
``f_avail`` (``build_envelope(tau_m, rho_m, t_leg)``) that models the tack mixing needed INSIDE a
planning step to realise a velocity no single heading gives. That is a planning model of sub-step
manoeuvres; the simulator's chord is a straight constant-heading step whose power is the same
envelope value. The manoeuvre model here charges only the manoeuvres actually OBSERVED between
steps of the executed track (heading / TWA-side changes), which the envelope does not see. A
residual overlap exists if the envelope's mixing is itself realised by the tracker as heading
flips between steps (then the observed flips are charged too): the effect is the object of the
sensitivity experiments (manoeuvre model OFF / ON / tau x 2.5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from horizon.core import wind as W

__all__ = ["ManoeuvreModel", "detect_manoeuvres", "apply_manoeuvre_losses", "KIND_NAMES"]

KIND_NAMES = {0: "none", 1: "tack", 2: "gybe", 3: "turn"}


@dataclass(frozen=True)
class ManoeuvreModel:
    """Manoeuvre-loss parameters. ``enabled=False`` reproduces the Sprint-4 environment."""

    enabled: bool = True
    tau_tack_s: float = 240.0
    tau_gybe_s: float = 180.0
    tau_turn_s: float = 120.0
    rho: float = 0.3
    turn_deg: float = 30.0
    fixed_kwh: float = 0.0
    tau_scale: float = 1.0

    def tau_s(self, kind: int) -> float:
        return self.tau_scale * {1: self.tau_tack_s, 2: self.tau_gybe_s, 3: self.tau_turn_s}[kind]

    def signature(self) -> dict:
        return asdict(self)


def detect_manoeuvres(psi_deg, u, v, moving, model: ManoeuvreModel, prev=None):
    """Classify the manoeuvre taking place at the START of each step.

    Parameters
    ----------
    psi_deg : (n,) commanded heading [deg true]; u, v : (n,) true wind (toward) [m/s];
    moving : (n,) bool, ground speed >= hold threshold; prev : None or ``(psi, rel)`` of the last
        step of the previous segment (None after a hold or at the start).

    Returns
    -------
    kind : (n,) int8 (0 none, 1 tack, 2 gybe, 3 turn); new_prev : tuple or None.
    """
    psi = np.asarray(psi_deg, float)
    rel = np.asarray(W.twa_signed(u, v, psi), float)
    n = psi.size
    kind = np.zeros(n, np.int8)
    if n == 0:
        return kind, prev
    psi_p = np.empty(n)
    rel_p = np.empty(n)
    ok = np.zeros(n, bool)
    psi_p[1:], rel_p[1:] = psi[:-1], rel[:-1]
    ok[1:] = moving[:-1] & moving[1:]
    if prev is not None:
        psi_p[0], rel_p[0] = prev
        ok[0] = bool(moving[0])
    dpsi = np.abs((psi - psi_p + 180.0) % 360.0 - 180.0)
    flip = (np.sign(rel) * np.sign(rel_p) < 0)
    thru0 = (np.abs(rel) + np.abs(rel_p)) < 180.0
    kind[ok & flip & thru0] = 1
    kind[ok & flip & ~thru0] = 2
    kind[ok & ~flip & (dpsi > model.turn_deg)] = 3
    new_prev = (float(psi[-1]), float(rel[-1])) if moving[-1] else None
    return kind, new_prev


def apply_manoeuvre_losses(p_kw, kind, dt_s: float, model: ManoeuvreModel) -> np.ndarray:
    """Power [kW] per step after the manoeuvre losses (see module docstring)."""
    p = np.asarray(p_kw, float).copy()
    for k in (1, 2, 3):
        m = kind == k
        if not m.any():
            continue
        frac = min(model.tau_s(k) / dt_s, 1.0)
        p[m] = p[m] - (1.0 - model.rho) * frac * np.maximum(p[m], 0.0)
        if model.fixed_kwh:
            p[m] = p[m] - model.fixed_kwh * 3600.0 / dt_s
    return p
