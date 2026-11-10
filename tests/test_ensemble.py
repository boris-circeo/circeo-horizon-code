"""Tests of the ensemble reduction: vector EOF, PAM, reduce_ensemble (DES-860 §4.5, §6.13)."""

import itertools

import numpy as np
import pytest

from horizon.ensemble import choose_k, pam, reduce_ensemble, vector_eof
from horizon.ensemble.pam import pairwise_distances
from horizon.geo.grid import Grid
from horizon.weather.fields import Ensemble

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")


def brute_force_cost(d, k, w):
    return min(float((w * d[:, list(c)].min(axis=1)).sum())
               for c in itertools.combinations(range(d.shape[0]), k))


# ------------------------------------------------------------------------------------ PAM
@pytest.mark.parametrize("seed", range(5))
def test_pam_optimal_on_clustered_toy(seed):
    rng = np.random.default_rng(seed)
    centres = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])
    x = np.concatenate([c + rng.normal(0, 0.8, (3, 2)) for c in centres])
    d = pairwise_distances(x)
    w = np.full(9, 1 / 9)
    for k in (1, 2, 3):
        r = pam(d, k)
        assert r.cost == pytest.approx(brute_force_cost(d, k, w), rel=1e-9)
    assert pam(d, 9).cost == pytest.approx(0.0, abs=1e-12)


def test_pam_weighted_and_structure():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(12, 3))
    d = pairwise_distances(x)
    w = rng.random(12)
    w /= w.sum()
    r = pam(d, 4, w)
    assert len(set(r.medoids.tolist())) == 4 and r.medoids.max() < 12  # distinct real members
    assert r.weights.sum() == pytest.approx(1.0) and np.all(np.diff(r.weights) <= 1e-15)
    assert np.all(r.labels[r.medoids] == np.arange(4))
    assert r.weights == pytest.approx(np.bincount(r.labels, weights=w, minlength=4))
    # local optimality: no single swap improves
    base = (w * d[:, r.medoids].min(1)).sum()
    for a in range(4):
        for h in set(range(12)) - set(r.medoids.tolist()):
            m = r.medoids.copy()
            m[a] = h
            assert (w * d[:, m].min(1)).sum() >= base - 1e-12
    r2 = pam(d, 4, w)
    assert np.array_equal(r.medoids, r2.medoids) and r.cost == r2.cost


def test_pam_bad_k_and_choose_k():
    d = pairwise_distances(np.arange(6.0)[:, None])
    with pytest.raises(ValueError):
        pam(d, 0)
    with pytest.raises(ValueError):
        pam(d, 7)
    rng = np.random.default_rng(0)
    x = np.concatenate([c + rng.normal(0, 0.1, (5, 2)) for c in ([0, 0], [9, 0], [0, 9], [9, 9])])
    assert choose_k(pairwise_distances(x), k_min=2, k_max=8, explained=0.95) == 4


# ------------------------------------------------------------------------------------ EOF
def _toy_uv(m=8, t=4, ny=5, nx=6, seed=0):
    return np.random.default_rng(seed).normal(0, 3, (m, t, ny, nx, 2)).astype(np.float32)


def test_eof_preserves_distances_and_variance():
    uv = _toy_uv()
    alpha = np.array([1.0, 0.7, 0.5, 0.3])
    r = vector_eof(uv, time_weights=alpha, var_target=1.0, max_modes=100, n_modes=8)
    assert r.explained.sum() == pytest.approx(1.0) and np.all(np.diff(r.explained) <= 1e-12)
    a = (uv - uv.mean(0)).astype(np.float64) * np.sqrt(alpha)[None, :, None, None, None]
    flat = a.reshape(8, -1)
    d_full = pairwise_distances(flat)
    assert pairwise_distances(r.pcs) == pytest.approx(d_full, rel=1e-8, abs=1e-8)
    assert r.total_variance == pytest.approx((flat ** 2).sum())
    # rank M-1 (centred): last PC is numerically zero
    assert np.abs(r.pcs[:, -1]).max() < 1e-6 * np.abs(r.pcs[:, 0]).max()


def test_eof_mode_selection_and_vector_character():
    uv = _toy_uv(m=10)
    r = vector_eof(uv, var_target=0.6, max_modes=40)
    assert r.cumulative[-1] >= 0.6 and (r.n_modes == 1 or r.cumulative[-2] < 0.6)
    assert vector_eof(uv, var_target=1.0, max_modes=3).n_modes == 3
    # a rotated vector pattern is distinguishable: swapping (u, v) changes the PCs
    base = np.zeros((4, 1, 4, 4, 2), np.float32)
    base[1, ..., 0] = 5.0
    base[2, ..., 1] = 5.0
    d = pairwise_distances(vector_eof(base, n_modes=3).pcs)
    assert d[1, 2] == pytest.approx(5.0 * np.sqrt(2 * 16), rel=1e-6)


def test_eof_space_weights_mask():
    uv = _toy_uv()
    mask = np.zeros(uv.shape[2:4])
    mask[:2] = 1.0
    r = vector_eof(uv, space_weights=mask, n_modes=8)
    r2 = vector_eof(uv[:, :, :2], n_modes=8)
    assert pairwise_distances(r.pcs) == pytest.approx(pairwise_distances(r2.pcs), abs=1e-8)


# ------------------------------------------------------------------------- reduce_ensemble
def planted_ensemble(per=4, seed=0):
    """3 families x ``per`` members with a displaced vortex-like pattern + small noise."""
    g = Grid.from_bbox(-8, 2, 40, 46, 80e3)
    rng = np.random.default_rng(seed)
    X, Y = g.xy_mesh()
    t = 3 * 3600.0 * np.arange(6)
    uv = []
    for fam in range(3):
        xc = (-300e3, 0.0, 300e3)[fam]
        pat = np.stack([10 * np.exp(-((X - xc) ** 2 + Y ** 2) / 2e5 ** 2),
                        -6 * np.exp(-((X - xc) ** 2 + Y ** 2) / 2e5 ** 2)], -1)
        for _ in range(per):
            uv.append(pat[None] * np.ones((6, 1, 1, 1)) + rng.normal(0, 0.3, (6,) + pat.shape))
    uv = np.array(uv, np.float32)
    m = uv.shape[0]
    return Ensemble(g, EPOCH, 0.0, t, uv, np.full(m, 1.0 / m)), np.repeat(np.arange(3), per)


def test_reduce_recovers_planted_families():
    ens, fam = planted_ensemble()
    red = reduce_ensemble(ens, k=3)
    assert red.k == 3 and red.weights.sum() == pytest.approx(1.0)
    assert sorted(fam[red.members]) == [0, 1, 2]  # one real member per family
    assert red.weights == pytest.approx([1 / 3] * 3)
    assert red.distortion_explained > 0.9
    assert all(np.array_equal(ens.member(int(i)).uv, ens.uv[i]) for i in red.members)  # real
    assert len(red.scenarios(ens)) == 3
    assert red.eof.explained.sum() <= 1.0 + 1e-12


def test_reduce_reproducible_and_adaptive_and_window():
    ens, fam = planted_ensemble(per=5, seed=2)
    a, b = reduce_ensemble(ens, k=3), reduce_ensemble(ens, k=3)
    assert np.array_equal(a.members, b.members) and np.array_equal(a.weights, b.weights)
    ad = reduce_ensemble(ens, k=None, k_range=(2, 8), window_s=(3 * 3600.0, ens.times_s[-1]))
    assert 2 <= ad.k <= 8
    assert reduce_ensemble(ens, k=100).k == ens.n_members  # clipped
    with pytest.raises(ValueError):
        reduce_ensemble(ens, k=3, window_s=(1e9, 2e9))
