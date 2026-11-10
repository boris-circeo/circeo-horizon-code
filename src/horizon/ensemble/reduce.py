"""Ensemble reduction to k real-member scenarios (DES-860 §4.5, §6.13).

Pipeline: window the members on the scenario lead times -> weight by ``alpha_t`` (decays with
lead) and ``beta_x`` -> vector EOF (u, v stacked) -> k-medoids (PAM) in PC space -> medoid
members with Voronoi-mass weights.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from horizon.ensemble.eof import EOFResult, vector_eof
from horizon.ensemble.pam import choose_k, pairwise_distances, pam
from horizon.weather.fields import Ensemble, WindField

__all__ = ["ReducedEnsemble", "reduce_ensemble"]


@dataclass(frozen=True)
class ReducedEnsemble:
    """Reduced scenario set.

    Attributes
    ----------
    members : int (k,)  Indices of the medoid members in the source ensemble (traceable).
    weights : float (k,)  Scenario probabilities, sum to 1.
    labels : int (M,)  Cluster (index into ``members``) of every source member.
    eof : EOFResult  PCs / explained variance used for the distance.
    cost, cost_one : float  PAM distortion with k medoids / with one medoid.
    """

    members: np.ndarray
    weights: np.ndarray
    labels: np.ndarray
    eof: EOFResult
    cost: float
    cost_one: float

    @property
    def k(self) -> int:
        return int(self.members.size)

    @property
    def distortion_explained(self) -> float:
        """``1 - cost / cost_one`` in [0, 1]."""
        return 0.0 if self.cost_one <= 0 else float(1.0 - self.cost / self.cost_one)

    def scenarios(self, ens: Ensemble) -> list[WindField]:
        """The medoid members of ``ens`` as :class:`WindField` objects."""
        return [ens.member(int(m)) for m in self.members]


def reduce_ensemble(ens: Ensemble, k: int | None = 7, window_s: tuple[float, float] | None = None,
                    tau_s: float = 7 * 86400.0, space_weights: np.ndarray | None = None,
                    var_target: float = 0.9, max_modes: int = 40,
                    k_range: tuple[int, int] = (5, 12), time_stride: int = 1) -> ReducedEnsemble:
    """Reduce an ensemble to ``k`` medoid scenarios.

    Parameters
    ----------
    ens : Ensemble
    k : int or None  Number of scenarios; ``None`` = adaptive in ``k_range``
        (:func:`horizon.ensemble.pam.choose_k`). Clipped to the number of members.
    window_s : (start, end) [s since epoch], optional  Valid-time window the distance is measured
        on (default: whole ensemble). Use ``(t_issue + 48 h, end)``: before the split the plan is
        common to all scenarios, so only the later divergence matters for the scenario choice.
    tau_s : float  [s]  alpha_t = exp(-(t - window start)/tau_s), the far lead counts less
        (DES-860 §4.5.2). ``inf`` for flat weights.
    space_weights : ndarray (Ny, Nx), optional  beta_x, e.g. a reachable-domain mask (default 1).
    var_target, max_modes : see :func:`horizon.ensemble.eof.vector_eof`.
    k_range : (int, int)  Bounds of the adaptive k.
    time_stride : int  Use every n-th time of the window (cheaper Gram accumulation).

    Returns
    -------
    ReducedEnsemble
    """
    t = ens.times_s
    lo, hi = (t[0], t[-1]) if window_s is None else window_s
    idx = np.flatnonzero((t >= lo - 1e-6) & (t <= hi + 1e-6))[::max(int(time_stride), 1)]
    if idx.size == 0:
        raise ValueError("empty reduction window")
    alpha = np.exp(-(t[idx] - t[idx[0]]) / tau_s)
    eof = vector_eof(ens.uv, ens.weights, alpha, space_weights, var_target, max_modes,
                     time_index=idx)
    d = pairwise_distances(eof.pcs)
    kk = choose_k(d, ens.weights, *k_range) if k is None else min(int(k), ens.n_members)
    res = pam(d, kk, ens.weights)
    c1 = pam(d, 1, ens.weights).cost
    return ReducedEnsemble(res.medoids, res.weights, res.labels, eof, res.cost, c1)
