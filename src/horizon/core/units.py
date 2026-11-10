"""Unit constants and conversion helpers (the only place conversion constants live).

Internal units are SI-like (m/s, m, s, kW, kWh, degrees in public APIs); see docs/CONVENTIONS.md.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "KNOT", "NM", "SECONDS_PER_HOUR",
    "kn_to_ms", "ms_to_kn", "nm_to_m", "m_to_nm",
    "energy_kwh", "mean_power_kw",
    "wrap360", "wrap180",
]

NM: float = 1852.0
"""Nautical mile [m]."""
SECONDS_PER_HOUR: float = 3600.0
KNOT: float = NM / SECONDS_PER_HOUR
"""Knot [m/s], exactly 1852/3600."""


def kn_to_ms(v_kn):
    """Knots -> metres per second.

    Parameters
    ----------
    v_kn : float or ndarray  [kn]
    """
    return np.asarray(v_kn, dtype=float) * KNOT


def ms_to_kn(v_ms):
    """Metres per second -> knots.

    Parameters
    ----------
    v_ms : float or ndarray  [m/s]
    """
    return np.asarray(v_ms, dtype=float) / KNOT


def nm_to_m(d_nm):
    """Nautical miles -> metres. ``d_nm`` [NM]."""
    return np.asarray(d_nm, dtype=float) * NM


def m_to_nm(d_m):
    """Metres -> nautical miles. ``d_m`` [m]."""
    return np.asarray(d_m, dtype=float) / NM


def energy_kwh(power_kw, duration_s):
    """Energy [kWh] of a constant power ``power_kw`` [kW] over ``duration_s`` [s]."""
    return power_kw * duration_s / SECONDS_PER_HOUR


def mean_power_kw(energy_kwh_, duration_s):
    """Mean power [kW] for ``energy_kwh_`` [kWh] delivered over ``duration_s`` [s] (> 0)."""
    return energy_kwh_ * SECONDS_PER_HOUR / duration_s


def wrap360(angle_deg):
    """Wrap an angle [deg] to [0, 360)."""
    out = np.mod(angle_deg, 360.0)
    # np.mod of a tiny negative float can return exactly 360.0
    out = np.where(out >= 360.0, 0.0, out)
    return out if np.ndim(out) else float(out)


def wrap180(angle_deg):
    """Wrap an angle [deg] to (-180, 180]."""
    out = 180.0 - np.mod(180.0 - np.asarray(angle_deg, dtype=float), 360.0)
    return out if np.ndim(out) else float(out)
