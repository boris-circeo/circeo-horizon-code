"""Assembly of the E0 / V_theta data set from the collected per-release-time files."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from horizon.value.collect import load_track, track_samples
from horizon.value.features import FEATURE_NAMES, feature_matrix, month_of

__all__ = ["Dataset", "assemble", "build_X", "sample_map"]

DAY = 86400.0


def sample_map(grid, field, x, y) -> np.ndarray:
    """Bilinear sample of ``field (Ny, Nx)`` (NaN = invalid cell) at ``(x, y)`` [m]; invalid
    corners are dropped and the weights renormalised (NaN if all four are invalid)."""
    fi, fj = (np.asarray(x) - grid.x0) / grid.dx, (np.asarray(y) - grid.y0) / grid.dx
    i0 = np.clip(np.floor(fi).astype(int), 0, grid.nx - 2)
    j0 = np.clip(np.floor(fj).astype(int), 0, grid.ny - 2)
    a, b = np.clip(fi - i0, 0, 1), np.clip(fj - j0, 0, 1)
    num, den = 0.0, 0.0
    for dj, di, w in ((0, 0, (1 - a) * (1 - b)), (0, 1, a * (1 - b)), (1, 0, (1 - a) * b),
                      (1, 1, a * b)):
        v = field[j0 + dj, i0 + di]
        ok = np.isfinite(v)
        num = num + np.where(ok, w * np.where(ok, v, 0.0), 0.0)
        den = den + np.where(ok, w, 0.0)
    return np.where(den > 1e-9, num / np.maximum(den, 1e-9), np.nan)


class Dataset:
    """Rows = decision states. Arrays (n,): ``src`` (0 = rollout, 1.. = track run index),
    ``k`` (release index), ``tau`` [s], ``x, y`` [m], ``month``; ``E`` (n, 3): realised energy
    over H = 2, 5, 10 d [kWh] (NaN if unavailable); ``V`` (n, 3): clairvoyant ``V_hind`` for the
    same horizons. ``fc_all (n_k, 6, Ny, Nx)``, ``hind_all (n_k, 3, Ny, Nx)``, ``s_k (n_k,)``."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __len__(self):
        return len(self.x)

    def subset(self, mask) -> Dataset:
        m = np.asarray(mask)
        d = {k: (v[m] if isinstance(v, np.ndarray) and v.shape[:1] == (len(self),) else v)
             for k, v in self.__dict__.items()}
        return Dataset(**d)

    @property
    def has_fc(self):
        return np.isfinite(self.fc_all[self.k, 0, 0, 0])


def assemble(cache_dir, grid, run_dirs=(), epoch="2015-01-01T00:00:00", step_days: float = 3.0,
             extra_cells_per_k: int = 0, seed: int = 0) -> Dataset:
    """Load ``k_XXX.npz`` files and track samples.

    ``extra_cells_per_k``: add that many random navigable cells per release with the hindsight
    values only (``E`` = NaN): used to train hindsight-target models on more data.
    """
    files = sorted(Path(cache_dir).glob("k_[0-9][0-9][0-9].npz"))
    if not files:
        raise FileNotFoundError(cache_dir)
    ks, s_k, hind_all, fc_all, rows = [], [], [], [], []
    rng = np.random.default_rng(seed)
    for f in files:
        z = np.load(f)
        kk = len(ks)
        ks.append(int(f.stem.split("_")[1]))
        s_k.append(float(z["s_k"]))
        hind_all.append(z["hind"])
        fc_all.append(z["fc"])
        c = z["cells"]
        E = np.full((len(c), 3), np.nan)
        E[:, 0], E[:, 1] = z["E"][:, 1], z["E"][:, 4]
        rows.append((0, kk, z["x0"], z["y0"], E))
        if extra_cells_per_k:
            ok = np.argwhere(np.isfinite(z["hind"][1]))
            sel = ok[rng.choice(len(ok), min(extra_cells_per_k, len(ok)), replace=False)]
            rows.append((-1, kk, grid.x0 + sel[:, 1] * grid.dx, grid.y0 + sel[:, 0] * grid.dx,
                         np.full((len(sel), 3), np.nan)))
    s_k = np.array(s_k)
    for ri, rd in enumerate(run_dirs, start=1):
        x, y, ce = load_track(rd)
        keep, xs, ys, E = track_samples(x, y, ce, s_k, (2, 5, 10))
        idx = np.flatnonzero(keep)
        for q, kk in enumerate(idx):
            rows.append((ri, int(kk), xs[q:q + 1], ys[q:q + 1], E[q:q + 1]))
    src = np.concatenate([np.full(len(r[2]), r[0]) for r in rows])
    k = np.concatenate([np.full(len(r[2]), r[1]) for r in rows])
    x = np.concatenate([r[2] for r in rows])
    y = np.concatenate([r[3] for r in rows])
    E = np.concatenate([r[4] for r in rows])
    hind_all = np.stack(hind_all)
    V = np.empty((len(x), 3))
    for kk in np.unique(k):
        m = k == kk
        for h in range(3):
            V[m, h] = sample_map(grid, hind_all[kk, h], x[m], y[m])
    tau = s_k[k]
    return Dataset(src=src, k=k, tau=tau, x=x, y=y, month=month_of(tau, epoch), E=E, V=V,
                   fc_all=np.stack(fc_all), hind_all=hind_all, s_k=s_k, epoch=epoch)


def build_X(ds: Dataset, grid, clim_kw, sdf) -> np.ndarray:
    """Feature matrix (n, len(FEATURE_NAMES)) with the climatology ``clim_kw`` (NaN rows where the
    forecast features are unavailable)."""
    X = np.full((len(ds), len(FEATURE_NAMES)), np.nan, np.float32)
    for kk in np.unique(ds.k):
        m = ds.k == kk
        if not np.isfinite(ds.fc_all[kk, 0, 0, 0]):
            continue
        X[m] = feature_matrix(grid, ds.x[m], ds.y[m], ds.s_k[kk], ds.epoch, clim_kw, sdf,
                              ds.fc_all[kk])
    return X
