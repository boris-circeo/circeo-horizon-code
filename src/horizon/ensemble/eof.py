"""Weighted EOF / PCA of the vector wind over an ensemble (DES-860 §4.5.2, §6.13).

The members are the "samples", the (time, y, x, [u, v]) values the "variables". Since the number
of members M (~20-51) is far smaller than the state dimension, the exact SVD of the anomaly
matrix is obtained from the M x M Gram matrix (method of snapshots), accumulated one time slice
at a time: memory stays O(M * Ny * Nx) and the result is the plain (not randomised) SVD.

Area weighting: the planning grid is Lambert azimuthal equal-area (DES-860 §4.7.2), so every
cell has the same area and the spatial weight is uniform by default. A lat-lon grid would need
``cos(lat)``; pass it through ``space_weights``. The vector character is kept by stacking
``(u, v)`` as two variables per cell, so a displaced front is a displaced vector pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["EOFResult", "vector_eof"]


@dataclass(frozen=True)
class EOFResult:
    """Principal components of the member anomalies.

    Attributes
    ----------
    pcs : float64 (M, n_modes)  [m/s, weighted]  Member scores; Euclidean distances between rows
        equal the weighted L2 distance between member wind fields restricted to the kept modes.
    explained : float64 (n_modes,)  Fraction of the total variance carried by each mode.
    total_variance : float  [m^2/s^2, weighted sum over time and space]
    n_modes : int
    """

    pcs: np.ndarray
    explained: np.ndarray
    total_variance: float
    n_modes: int

    @property
    def cumulative(self) -> np.ndarray:
        """Cumulative explained variance fraction (n_modes,)."""
        return np.cumsum(self.explained)


def vector_eof(uv: np.ndarray, member_weights: np.ndarray | None = None,
               time_weights: np.ndarray | None = None, space_weights: np.ndarray | None = None,
               var_target: float = 0.9, max_modes: int = 40,
               n_modes: int | None = None, time_index: np.ndarray | None = None) -> EOFResult:
    """EOF/PCA of an ensemble of vector wind fields.

    Parameters
    ----------
    uv : ndarray (M, T, Ny, Nx, 2)  [m/s]  Member wind (u east, v north).
    member_weights : ndarray (M,), optional  Probabilities used to centre (default uniform).
    time_weights : ndarray (T,), optional  alpha_t of DES-860 §4.5.2 (default 1).
    space_weights : ndarray (Ny, Nx), optional  beta_x (default 1: equal-area grid).
    var_target : float  Keep the fewest modes reaching this cumulative variance fraction.
    max_modes : int  Upper bound on the number of modes (spec: 20-40).
    n_modes : int, optional  Force the number of modes (overrides ``var_target``).
    time_index : int ndarray (T',), optional  Use only these time slices (no copy of ``uv``);
        ``time_weights`` then has length ``T'``.

    Returns
    -------
    EOFResult
    """
    m = uv.shape[0]
    tix = np.arange(uv.shape[1]) if time_index is None else np.asarray(time_index)
    t = tix.size
    w = np.full(m, 1.0 / m) if member_weights is None else np.asarray(member_weights, float)
    w = w / w.sum()
    a_t = np.ones(t) if time_weights is None else np.asarray(time_weights, float)
    sw = None if space_weights is None else np.sqrt(np.asarray(space_weights, float))[..., None]
    gram = np.zeros((m, m))
    for k in range(t):
        x = uv[:, tix[k]].astype(np.float64)
        x -= np.tensordot(w, x, axes=1)
        if sw is not None:
            x *= sw
        x = x.reshape(m, -1)
        gram += a_t[k] * (x @ x.T)
    lam, vec = np.linalg.eigh(gram)
    lam, vec = np.clip(lam[::-1], 0.0, None), vec[:, ::-1]
    total = float(lam.sum())
    frac = lam / total if total > 0 else np.zeros_like(lam)
    cap = max(min(max_modes, m - 1), 1)
    if n_modes is None:
        n = int(np.searchsorted(np.cumsum(frac), var_target - 1e-12) + 1)
        n = min(max(n, 1), cap)
    else:
        n = min(max(int(n_modes), 1), m)
    pcs = vec[:, :n] * np.sqrt(lam[:n])
    return EOFResult(pcs, frac[:n], total, n)
