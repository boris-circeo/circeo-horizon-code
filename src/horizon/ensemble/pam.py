"""In-house k-medoids (PAM: BUILD + SWAP, Kaufman & Rousseeuw) — no GPL dependency.

PAM is deterministic (greedy BUILD, best-improvement SWAP, ties broken by lowest index), so
the same distance matrix always gives the same medoids (DES-860 §4.5.4: "reproducible from one
cycle to the next"). Medoids are real members (DES-860 §4.5.3).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["PAMResult", "pam", "choose_k", "pairwise_distances"]


def pairwise_distances(x: np.ndarray) -> np.ndarray:
    """Euclidean distance matrix (n, n) of the rows of ``x`` (n, d)."""
    x = np.asarray(x, float)
    d2 = ((x[:, None, :] - x[None, :, :]) ** 2).sum(-1)
    return np.sqrt(d2)


@dataclass(frozen=True)
class PAMResult:
    """Output of :func:`pam`.

    Attributes
    ----------
    medoids : int (k,)  Member indices, sorted by decreasing cluster mass.
    labels : int (n,)  Index into ``medoids`` of the cluster of each member.
    weights : float (k,)  Cluster masses (Voronoi: sum of member probabilities), sum to 1.
    cost : float  ``sum_i w_i d(i, medoid(i))``.
    """

    medoids: np.ndarray
    labels: np.ndarray
    weights: np.ndarray
    cost: float


def _cost(d: np.ndarray, w: np.ndarray, med) -> float:
    return float((w * d[:, med].min(axis=1)).sum())


def pam(d: np.ndarray, k: int, weights: np.ndarray | None = None,
        max_iter: int = 100) -> PAMResult:
    """k-medoids by PAM on a distance matrix.

    Parameters
    ----------
    d : ndarray (n, n)  Symmetric distances, zero diagonal.
    k : int  Number of medoids, ``1 <= k <= n``.
    weights : ndarray (n,), optional  Member probabilities (default ``1/n``).
    max_iter : int  SWAP iterations bound.

    Returns
    -------
    PAMResult
    """
    n = d.shape[0]
    if not 1 <= k <= n:
        raise ValueError("k must be in [1, n]")
    w = np.full(n, 1.0 / n) if weights is None else np.asarray(weights, float) / np.sum(weights)
    # BUILD: first medoid minimises the total cost, then greedy gain.
    med = [int(np.argmin(w @ d))]
    near = d[:, med[0]].copy()
    while len(med) < k:
        gain = (w[:, None] * np.maximum(near[:, None] - d, 0.0)).sum(0)
        gain[med] = -np.inf
        j = int(np.argmax(gain))
        med.append(j)
        near = np.minimum(near, d[:, j])
    best = _cost(d, w, med)
    for _ in range(max_iter):  # SWAP: best improving (medoid, non-medoid) exchange
        cand, cbest = None, best
        for a in range(k):
            for h in range(n):
                if h in med:
                    continue
                trial = med.copy()
                trial[a] = h
                c = _cost(d, w, trial)
                if c < cbest - 1e-12 * max(abs(best), 1.0):
                    cand, cbest = (a, h), c
        if cand is None:
            break
        med[cand[0]] = cand[1]
        best = cbest
    med_a = np.array(med)
    lab = np.argmin(d[:, med_a], axis=1)
    lab[med_a] = np.arange(k)  # a medoid always belongs to its own cluster
    mass = np.bincount(lab, weights=w, minlength=k)
    order = np.lexsort((med_a, -mass))
    inv = np.empty(k, int)
    inv[order] = np.arange(k)
    return PAMResult(med_a[order], inv[lab], mass[order], _cost(d, w, med_a))


def choose_k(d: np.ndarray, weights: np.ndarray | None = None, k_min: int = 5, k_max: int = 12,
             explained: float = 0.5) -> int:
    """Smallest ``k`` in ``[k_min, k_max]`` whose PAM distortion explains ``explained`` of the
    one-medoid distortion (``1 - cost_k / cost_1``); ``k_max`` if none does (DES-860 §6.13).
    """
    n = d.shape[0]
    k_max = min(k_max, n)
    c1 = pam(d, 1, weights).cost
    for k in range(min(k_min, k_max), k_max + 1):
        if c1 <= 0 or 1.0 - pam(d, k, weights).cost / c1 >= explained:
            return k
    return k_max
