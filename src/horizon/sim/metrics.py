"""Mission metrics: energy, capacity factor, regret (DES-860 §3.3, §8.1)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from horizon.sim.power import HOLD_SPEED_MS

__all__ = ["MissionMetrics", "mission_metrics", "regret"]


@dataclass(frozen=True)
class MissionMetrics:
    """Summary of one mission.

    Attributes
    ----------
    energy_kwh : float  [kWh]  Net energy J.
    capacity_factor : float  [-]  ``J / (P_rated T)``.
    mean_power_kw : float  [kW]
    distance_km : float  [km]  Ground distance sailed.
    hold_fraction : float  [-]  Fraction of time with ground speed below 0.5 m/s.
    """

    energy_kwh: float
    capacity_factor: float
    mean_power_kw: float
    distance_km: float
    hold_fraction: float


def regret(j_hind_kwh: float, j_kwh: float) -> float:
    """Relative regret ``(J_hind - J) / J_hind`` [-] (DES-860 §3.3)."""
    return (j_hind_kwh - j_kwh) / j_hind_kwh


def mission_metrics(res, p_rated_kw: float = 3000.0) -> MissionMetrics:
    """Metrics of a :class:`horizon.sim.simulator.MissionResult`.

    Parameters
    ----------
    res : MissionResult
    p_rated_kw : float  [kW]  Rated power for the capacity factor (3000 kW).
    """
    dt = res.sim_dt_s
    hours = res.power_kw.size * dt / 3600.0
    j = float(res.energy_kwh[-1])
    return MissionMetrics(
        energy_kwh=j,
        capacity_factor=j / (p_rated_kw * hours),
        mean_power_kw=j / hours,
        distance_km=float(res.speed_ms.sum() * dt / 1e3),
        hold_fraction=float(np.mean(res.speed_ms < HOLD_SPEED_MS)),
    )
