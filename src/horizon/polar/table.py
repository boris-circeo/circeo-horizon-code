"""Tabulated 3-D power polar ``P[TWS, TWA, U]`` (DES-860 §2.2.2, §7.3.3).

All quantities follow ``docs/CONVENTIONS.md``: speeds in m/s, power in kW, TWA in degrees in
[0, 180] (0 = head to wind). Axes are stored in SI (TWS and U in m/s); knots appear only in the
CSV loader and the default-grid helpers.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numba import njit

from horizon.core.units import KNOT

__all__ = [
    "KNOT",
    "P_MAX_KW",
    "P_MIN_KW",
    "PolarTable",
    "default_axes",
    "trilinear_many",
    "trilinear_scalar",
]

P_MIN_KW = -500.0  #: lower sanity bound of net power [kW] (DES-860 §7.5.8)
P_MAX_KW = 3000.0  #: upper sanity bound = generator cap [kW]


def default_axes() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Spec default grid (DES-860 §2.2.2).

    Returns
    -------
    tws, twa, u : numpy.ndarray
        TWS 0-50 kn step 1 kn [m/s] (51 pts), TWA 0-180 deg step 2.5 deg (73 pts),
        U 0-10 m/s step 0.25 m/s (41 pts). All float64.
    """
    tws = np.arange(0, 51) * KNOT
    twa = np.arange(0, 73) * 2.5
    u = np.arange(0, 41) * 0.25
    return tws, twa, u


@njit(cache=True)
def trilinear_scalar(P, x0, dx, y0, dy, z0, dz, tws, twa, u):  # pragma: no cover - jitted
    """Trilinear interpolation of ``P`` at one point, clamped at the table bounds.

    Parameters
    ----------
    P : float32[nx, ny, nz]
        Table, axes (TWS, TWA, U).
    x0, dx, y0, dy, z0, dz : float
        Origin and (uniform) step of the TWS [m/s], TWA [deg], U [m/s] axes.
    tws, twa, u : float
        Query point: TWS [m/s], TWA [deg] (sign ignored), U [m/s].

    Returns
    -------
    float
        Interpolated power [kW]; NaN if any input is non-finite.
    """
    nx, ny, nz = P.shape
    y = abs(twa)
    if not (np.isfinite(tws) and np.isfinite(y) and np.isfinite(u)):
        return np.nan
    fx = min(max((tws - x0) / dx, 0.0), nx - 1.0)
    fy = min(max((y - y0) / dy, 0.0), ny - 1.0)
    fz = min(max((u - z0) / dz, 0.0), nz - 1.0)
    i = min(int(fx), nx - 2)
    j = min(int(fy), ny - 2)
    k = min(int(fz), nz - 2)
    ax = fx - i
    ay = fy - j
    az = fz - k
    c00 = P[i, j, k] * (1 - az) + P[i, j, k + 1] * az
    c01 = P[i, j + 1, k] * (1 - az) + P[i, j + 1, k + 1] * az
    c10 = P[i + 1, j, k] * (1 - az) + P[i + 1, j, k + 1] * az
    c11 = P[i + 1, j + 1, k] * (1 - az) + P[i + 1, j + 1, k + 1] * az
    c0 = c00 * (1 - ay) + c01 * ay
    c1 = c10 * (1 - ay) + c11 * ay
    return c0 * (1 - ax) + c1 * ax


@njit(cache=True)
def trilinear_many(P, x0, dx, y0, dy, z0, dz, tws, twa, u, out):  # pragma: no cover - jitted
    """Vectorised :func:`trilinear_scalar` over 1-D float64 arrays; fills ``out`` [kW]."""
    for n in range(tws.shape[0]):
        out[n] = trilinear_scalar(P, x0, dx, y0, dy, z0, dz, tws[n], twa[n], u[n])


def _check_uniform(name: str, ax: np.ndarray) -> float:
    if ax.ndim != 1 or ax.size < 2:
        raise ValueError(f"axis {name} must be 1-D with at least 2 points")
    d = np.diff(ax)
    step = (ax[-1] - ax[0]) / (ax.size - 1)
    if step <= 0 or not np.allclose(d, step, rtol=1e-6, atol=1e-9 * abs(step)):
        raise ValueError(f"axis {name} must be strictly increasing and uniformly spaced")
    return float(step)


@dataclass(eq=False)
class PolarTable:
    """Net power polar on a uniform (TWS, TWA, U) grid.

    Parameters
    ----------
    p : array_like, shape (nTWS, nTWA, nU)
        Net power [kW]; stored as float32.
    tws : array_like  [m/s]
        True wind speed axis, uniform, increasing.
    twa : array_like  [deg]
        True wind angle axis in [0, 180], uniform (0 = head to wind).
    u : array_like  [m/s]
        Ship speed through water axis, uniform.
    strict : bool
        If True (default) values outside [-500, 3000] kW or non-finite raise ``ValueError``;
        otherwise a warning is emitted.

    Notes
    -----
    Port/starboard symmetry is assumed (CONVENTIONS §3): signed TWA is folded with ``abs``.
    """

    p: np.ndarray
    tws: np.ndarray
    twa: np.ndarray
    u: np.ndarray
    strict: bool = True

    def __post_init__(self) -> None:
        self.p = np.ascontiguousarray(self.p, dtype=np.float32)
        self.tws = np.asarray(self.tws, dtype=np.float64)
        self.twa = np.asarray(self.twa, dtype=np.float64)
        self.u = np.asarray(self.u, dtype=np.float64)
        if self.p.shape != (self.tws.size, self.twa.size, self.u.size):
            raise ValueError(
                f"p shape {self.p.shape} does not match axes "
                f"({self.tws.size}, {self.twa.size}, {self.u.size})"
            )
        self.d_tws = _check_uniform("tws", self.tws)
        self.d_twa = _check_uniform("twa", self.twa)
        self.d_u = _check_uniform("u", self.u)
        if self.twa[0] < 0 or self.twa[-1] > 180:
            raise ValueError("twa axis must lie within [0, 180] degrees")
        if self.tws[0] < 0 or self.u[0] < 0:
            raise ValueError("tws and u axes must be non-negative")
        self._validate_values()

    def _validate_values(self) -> None:
        msg = None
        if not np.all(np.isfinite(self.p)):
            msg = "polar contains non-finite values"
        else:
            lo, hi = float(self.p.min()), float(self.p.max())
            if lo < P_MIN_KW or hi > P_MAX_KW:
                msg = f"polar values [{lo:.1f}, {hi:.1f}] kW outside [{P_MIN_KW}, {P_MAX_KW}] kW"
        if msg:
            if self.strict:
                raise ValueError(msg)
            warnings.warn(msg, stacklevel=3)

    @property
    def axis_params(self) -> tuple[float, float, float, float, float, float]:
        """``(tws0, dtws, twa0, dtwa, u0, du)`` for direct use with the Numba kernels."""
        return (
            float(self.tws[0]),
            self.d_tws,
            float(self.twa[0]),
            self.d_twa,
            float(self.u[0]),
            self.d_u,
        )

    def __call__(self, tws, twa, u):
        """Trilinear power [kW], clamped at the table bounds.

        Parameters
        ----------
        tws : array_like  [m/s]
        twa : array_like  [deg]
            Signed TWA accepted; ``abs`` is applied. Values > 180 are clamped, not wrapped.
        u : array_like  [m/s]

        Returns
        -------
        numpy.float64 or numpy.ndarray
            Net power [kW] with the broadcast shape of the inputs (float64).
        """
        a, b, c = np.broadcast_arrays(
            np.asarray(tws, dtype=np.float64),
            np.asarray(twa, dtype=np.float64),
            np.asarray(u, dtype=np.float64),
        )
        shape = a.shape
        out = np.empty(a.size, dtype=np.float64)
        trilinear_many(
            self.p,
            *self.axis_params,
            np.ascontiguousarray(a).ravel(),
            np.ascontiguousarray(b).ravel(),
            np.ascontiguousarray(c).ravel(),
            out,
        )
        return out.reshape(shape)[()]

    def reduced(self) -> tuple[np.ndarray, np.ndarray]:
        """Reduced polar over ship speed (DES-860 §2.2.2).

        Returns
        -------
        p_dagger : numpy.ndarray, shape (nTWS, nTWA)
            ``max_U P`` [kW], float32.
        u_dagger : numpy.ndarray, shape (nTWS, nTWA)
            Argmax ship speed [m/s], float32 (first maximum on ties).
        """
        k = np.argmax(self.p, axis=2)
        p_dag = np.take_along_axis(self.p, k[..., None], axis=2)[..., 0]
        return p_dag, self.u[k].astype(np.float32)

    def save_npz(self, path: str | Path) -> None:
        """Write the table and axes to a compressed ``.npz`` file."""
        np.savez_compressed(
            path, p=self.p, tws=self.tws, twa=self.twa, u=self.u, format_version=np.int32(1)
        )

    @classmethod
    def load_npz(cls, path: str | Path, strict: bool = True) -> PolarTable:
        """Load a table written by :meth:`save_npz`."""
        with np.load(path) as f:
            return cls(f["p"], f["tws"], f["twa"], f["u"], strict=strict)

    @classmethod
    def from_long_csv(cls, path: str | Path, strict: bool = True) -> PolarTable:
        """Load a long-format CSV (one row per grid node).

        Format
        ------
        Header ``tws_kn,twa_deg,u_ms,p_kw`` (any column order; ``#`` comment lines allowed);
        TWS in knots (converted to m/s), TWA in degrees in [0, 180], U in m/s, P in kW.

        Assumptions
        -----------
        The rows must form a full Cartesian product of the unique axis values, without
        duplicates (row order is free). If an axis is not uniformly spaced, the table is
        regridded by linear interpolation onto a uniform axis spanning the same range, using the
        spec default step (1 kn, 2.5 deg, 0.25 m/s) or the file's own step when it is
        uniform. Out-of-range values then follow ``strict``.
        """
        from scipy.interpolate import RegularGridInterpolator

        lines = [
            ln.strip()
            for ln in Path(path).read_text().splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        header = [h.strip() for h in lines[0].split(",")]
        names = ("tws_kn", "twa_deg", "u_ms", "p_kw")
        if not set(names) <= set(header):
            raise ValueError(f"CSV must have columns {list(names)}")
        raw = np.array([[float(v) for v in ln.split(",")] for ln in lines[1:]], dtype=np.float64)
        data = {n: raw[:, header.index(n)] for n in names}
        ax = [np.unique(data[n]) for n in ("tws_kn", "twa_deg", "u_ms")]
        shape = tuple(a.size for a in ax)
        if int(np.prod(shape)) != raw.shape[0]:
            raise ValueError("CSV rows do not form a full Cartesian grid")
        keys = ("tws_kn", "twa_deg", "u_ms")
        idx = tuple(np.searchsorted(a, data[n]) for a, n in zip(ax, keys, strict=True))
        p = np.full(shape, np.nan)
        p[idx] = data["p_kw"]
        if np.isnan(p).any():
            raise ValueError("CSV rows contain duplicates or non-finite power values")
        defaults = (1.0, 2.5, 0.25)
        new_ax = []
        for a, dflt in zip(ax, defaults, strict=True):
            try:
                _check_uniform("csv", a)
                new_ax.append(a)
            except ValueError:
                n = int(round((a[-1] - a[0]) / dflt)) + 1
                new_ax.append(np.linspace(a[0], a[-1], max(n, 2)))
        if any(n.size != a.size or not np.allclose(n, a) for n, a in zip(new_ax, ax, strict=True)):
            grid = np.meshgrid(*new_ax, indexing="ij")
            interp = RegularGridInterpolator(ax, p, method="linear")
            p = interp(np.stack([g.ravel() for g in grid], axis=-1)).reshape(grid[0].shape)
        return cls(p, new_ax[0] * KNOT, new_ax[1], new_ax[2], strict=strict)
