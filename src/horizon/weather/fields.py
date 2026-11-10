"""Containers for wind fields exchanged between weather sources, solvers and the simulator.

Binding interface for Sprint 1 (see docs/CONVENTIONS.md):

* time is carried as **seconds since the mission epoch** (``float64``), with ``epoch`` a
  ``numpy.datetime64[s]`` (UTC) for metadata only;
* time axes are uniform (``dt_s`` constant);
* wind is ``uv[..., 0] = u`` (eastward, "toward") and ``uv[..., 1] = v`` (northward), m/s,
  stored float32, C-contiguous, time axis first (after the member axis for ensembles).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from horizon.geo.grid import Grid

__all__ = ["WindField", "Ensemble"]


def _check_axis(times_s: np.ndarray) -> float:
    if times_s.ndim != 1 or times_s.size < 1:
        raise ValueError("times_s must be a non-empty 1-D array")
    if times_s.size == 1:
        return 0.0
    d = np.diff(times_s)
    if not np.allclose(d, d[0]):
        raise ValueError("time axis must be uniform")
    return float(d[0])


@dataclass(frozen=True)
class WindField:
    """A single (deterministic) wind field on a planning grid.

    Attributes
    ----------
    grid : Grid
        Spatial grid; ``uv`` spatial dims are ``(grid.ny, grid.nx)``.
    epoch : numpy.datetime64
        UTC instant corresponding to ``t = 0`` [s].
    times_s : ndarray (T,)
        Valid times [s since epoch], uniform spacing.
    uv : ndarray float32 (T, Ny, Nx, 2)
        Wind components (u east, v north, "toward") [m/s].
    """

    grid: Grid
    epoch: np.datetime64
    times_s: np.ndarray
    uv: np.ndarray

    def __post_init__(self):
        _check_axis(self.times_s)
        if self.uv.shape != (self.times_s.size, self.grid.ny, self.grid.nx, 2):
            raise ValueError(f"uv shape {self.uv.shape} inconsistent with grid/time")
        if self.uv.dtype != np.float32:
            raise TypeError("uv must be float32")

    @property
    def dt_s(self) -> float:
        """Time step [s]."""
        return _check_axis(self.times_s)

    def time_index(self, t_s: float) -> tuple[int, float]:
        """Bracketing index ``k`` and weight ``w`` so that value = (1-w)*f[k] + w*f[k+1].

        Clamped at both ends (no extrapolation).
        """
        dt = self.dt_s
        if dt == 0.0:
            return 0, 0.0
        r = (t_s - self.times_s[0]) / dt
        k = int(np.clip(np.floor(r), 0, self.times_s.size - 2))
        w = float(np.clip(r - k, 0.0, 1.0))
        return k, w


@dataclass(frozen=True)
class Ensemble:
    """An ensemble forecast issued at ``issue_s``.

    Attributes
    ----------
    grid : Grid
    epoch : numpy.datetime64
    issue_s : float
        Issue (analysis) time [s since epoch]. Information available to a causal policy at
        time t: only ensembles with ``issue_s <= t`` (plus availability latency).
    times_s : ndarray (T,)
        Valid times [s since epoch], uniform, ``times_s[0] >= issue_s``.
    uv : ndarray float32 (M, T, Ny, Nx, 2)
        Member wind fields [m/s]. Member 0 is the control / deterministic forecast.
    weights : ndarray float64 (M,)
        Member probabilities, sum to 1.
    """

    grid: Grid
    epoch: np.datetime64
    issue_s: float
    times_s: np.ndarray
    uv: np.ndarray
    weights: np.ndarray

    def __post_init__(self):
        _check_axis(self.times_s)
        m = self.uv.shape[0]
        if self.uv.shape[1:] != (self.times_s.size, self.grid.ny, self.grid.nx, 2):
            raise ValueError(f"uv shape {self.uv.shape} inconsistent with grid/time")
        if self.uv.dtype != np.float32:
            raise TypeError("uv must be float32")
        if self.weights.shape != (m,) or not np.isclose(self.weights.sum(), 1.0):
            raise ValueError("weights must have shape (M,) and sum to 1")

    @property
    def n_members(self) -> int:
        return self.uv.shape[0]

    def member(self, m: int) -> WindField:
        """Member ``m`` as a :class:`WindField`."""
        return WindField(self.grid, self.epoch, self.times_s, self.uv[m])
