"""Neighbour stencil of the spatio-temporal graph (DES-860 §4.7.4, §6.1.1, §7.3.2).

On a regular grid the neighbourhood is a constant table of integer offsets ``(di, dj)``. Offset
``k = 0`` is always the *hold* arc ``(0, 0)`` (station keeping, DES-860 §6.6.1); the others are
all non-zero integer offsets whose ground speed ``L / dt`` lies in ``[u_min, u_max]``.

Consistency condition (DES-860 §4.7.4): neighbouring cells must be reachable in one step,
``dx <= u_max * dt``; the stencil radius in cells is ``R = u_max * dt / dx`` (``build_stencil``
raises if no arc fits). Both coprime and non-coprime offsets are kept: ``(2, 0)`` and ``(1, 0)``
share a heading but give two distinct arc speeds, which the polar distinguishes.

Macro arcs (``max_span`` m > 1): an arc may span ``m`` DP steps (ground speed ``L / (m dt)``), so
the reachable radius grows to ``m u_max dt / dx`` cells and the heading set can be made fine
(:func:`build_stencil`, "pruning"). With ``max_span = 1`` the stencil is the plain ring below.

Angular resolution of the plain ring is ``~ 1/R`` radians at the outer ring (about 45 deg for
``R < 2``, ~20 deg for ``R ~ 3``): the DP cannot steer finer than that, which
:attr:`Stencil.angular_resolution_deg` reports. Ground lengths and true headings are
precomputed per cell and per arc because LAEA grid metres differ from ground metres by up to
~3 % (Sprint 0 finding).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import gcd

import numpy as np
from pyproj import Geod

from horizon.geo.grid import Grid

__all__ = ["Stencil", "build_stencil", "macro_arcs", "stencil_offsets"]


def stencil_offsets(dx: float, dt_s: float, u_bounds=(0.5, 8.0), slack: float = 0.05):
    """Nominal stencil offsets for cell size ``dx`` [m] and step ``dt_s`` [s].

    Parameters
    ----------
    dx : float  [m]
    dt_s : float  [s]
    u_bounds : tuple of float  [m/s]
        ``(u_min, u_max)`` ground-speed bounds of an arc (DES-860 A.1).
    slack : float  [-]
        Relative margin on the nominal (grid-metre) length so that cells where the ground length
        differs from the grid length keep their admissible arcs; the exact per-cell test is made
        on ground length in :func:`build_stencil`.

    Returns
    -------
    di, dj : ndarray of int32
        Hold ``(0, 0)`` first, then offsets sorted by increasing length and angle.
    """
    u_min, u_max = u_bounds
    n = int(np.floor(u_max * dt_s / dx * (1.0 + slack)))
    rng = np.arange(-n, n + 1)
    di, dj = np.meshgrid(rng, rng)
    di, dj = di.ravel(), dj.ravel()
    r = np.hypot(di, dj) * dx
    keep = (r > 0) & (r >= u_min * dt_s * (1 - slack)) & (r <= u_max * dt_s * (1 + slack))
    if not keep.any():
        raise ValueError(
            f"consistency condition violated: dx={dx:g} m > u_max*dt={u_max * dt_s:g} m "
            "(DES-860 §4.7.4)"
        )
    di, dj, r = di[keep], dj[keep], r[keep]
    order = np.lexsort((np.arctan2(dj, di), np.round(r, 6)))
    di = np.concatenate([[0], di[order]]).astype(np.int32)
    dj = np.concatenate([[0], dj[order]]).astype(np.int32)
    return di, dj


def macro_arcs(dx: float, dt_s: float, u_bounds=(0.5, 8.0), max_span: int = 3,
               slack: float = 0.05, gap_deg: float = 9.0, n_speeds: int = 2,
               band=(2.0, 7.6), targets=(2.5, 3.75, 5.5)):
    """Pruned multi-step arc set ``(di, dj, span)`` (hold first).

    1. Candidates: every ``(di, dj, m)``, ``m <= max_span``, with nominal ground speed
       ``|d| dx / (m dt)`` in the speed bounds.
    2. Directions: among the *useful-speed* candidates (speed in ``band`` [m/s], where the polar
       is productive) the lattice directions are thinned, on one octant and replicated by the 8
       lattice symmetries (no orientation bias), greedily keeping the farthest direction within
       ``gap_deg`` of the previous one.
    3. Speeds: for each kept direction keep the ``n_speeds`` (offset multiple, span) pairs whose
       speed is closest (log scale) to ``targets`` [m/s]; the 8 one-cell, one-step neighbours
       are always kept (they are the only arcs available close to the horizon end).
    """
    u_min, u_max = u_bounds
    cand = []
    for m in range(1, max_span + 1):
        n = int(np.floor(u_max * m * dt_s / dx * (1.0 + slack)))
        for a in range(-n, n + 1):
            for b in range(-n, n + 1):
                if a == b == 0:
                    continue
                u = np.hypot(a, b) * dx / (m * dt_s)
                if u_min * (1 - slack) <= u <= u_max * (1 + slack):
                    cand.append((a, b, m, u))
    if not cand:
        raise ValueError(
            f"consistency condition violated: dx={dx:g} m > u_max*dt={u_max * dt_s:g} m "
            "(DES-860 §4.7.4)")
    # directions (octant 0 <= b <= a) available at useful speeds
    prim = {}
    for a, b, _m, u in cand:
        if band[0] <= u <= band[1] and 0 <= b <= a:
            g = gcd(a, b)
            prim[(a // g, b // g)] = np.degrees(np.arctan2(b, a))
    keep = []
    if prim:
        ang = sorted(prim.items(), key=lambda kv: kv[1])
        keep = [ang[0]]
        for idx in range(1, len(ang)):
            if idx == len(ang) - 1 or ang[idx + 1][1] - keep[-1][1] > gap_deg:
                keep.append(ang[idx])
    dirs = set()
    for (a, b), _ in keep:
        for sa in (1, -1):
            for sb in (1, -1):
                dirs.add((sa * a, sb * b))
                dirs.add((sb * b, sa * a))
    byvec = {}
    for a, b, m, u in cand:
        byvec.setdefault((a, b), []).append((m, u))
    arcs = set()
    for (pa, pb) in dirs:
        opts = []
        for kk in range(1, 2 * max_span * int(np.ceil(u_max * dt_s / dx)) + 2):
            for m, u in byvec.get((kk * pa, kk * pb), []):
                opts.append((kk * pa, kk * pb, m, u))
        chosen = []
        for t in targets[:n_speeds]:
            best = min((o for o in opts if o not in chosen),
                       key=lambda o: abs(np.log(o[3] / t)), default=None)
            if best is not None:
                chosen.append(best)
        arcs.update((o[0], o[1], o[2]) for o in chosen)
    for a, b, m, _u in cand:
        if m == 1 and max(abs(a), abs(b)) == 1:
            arcs.add((a, b, 1))
    arcs = sorted(arcs, key=lambda t: (t[2], np.hypot(t[0], t[1]), np.arctan2(t[1], t[0])))
    di = np.array([0] + [t[0] for t in arcs], dtype=np.int32)
    dj = np.array([0] + [t[1] for t in arcs], dtype=np.int32)
    span = np.array([1] + [t[2] for t in arcs], dtype=np.int32)
    return di, dj, span


@dataclass(frozen=True)
class Stencil:
    """Stencil with per-cell geodesic arc geometry.

    Attributes
    ----------
    di, dj : ndarray int32 (K,)
        Offsets in cells (i = x, j = y); index 0 is the hold arc.
    dx, dt_s : float  [m], [s]
    u_bounds : tuple  [m/s]
    length_m : ndarray float32 (Ny, Nx, K)  [m]
        Geodesic ground length of each arc (0 for hold, NaN if leaving the grid).
    heading_deg : ndarray float32 (Ny, Nx, K)  [deg]
        Mean true heading of the arc, clockwise from true north, circular mean of the departure
        and arrival azimuths (NaN for hold / invalid).
    valid : ndarray bool (Ny, Nx, K)
        Destination inside the grid and ground speed within ``u_bounds``. Hold is True.
    span : ndarray int32 (K,)
        Number of DP steps spanned by each arc (1 for hold and for ``max_span = 1``); the
        ground speed of an arc is ``length_m / (span * dt_s)``.
    """

    di: np.ndarray
    dj: np.ndarray
    dx: float
    dt_s: float
    u_bounds: tuple
    length_m: np.ndarray
    heading_deg: np.ndarray
    valid: np.ndarray
    span: np.ndarray | None = None
    sin_h: np.ndarray = field(init=False, repr=False, compare=False)
    cos_h: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.span is None:
            object.__setattr__(self, "span", np.ones(self.di.size, dtype=np.int32))
        psi = np.radians(self.heading_deg)
        object.__setattr__(self, "sin_h", np.sin(psi))
        object.__setattr__(self, "cos_h", np.cos(psi))

    @property
    def n_arcs(self) -> int:
        """Number of stencil entries K (hold included)."""
        return int(self.di.size)

    @property
    def radius_cells(self) -> float:
        """Largest nominal arc length in cells [-]."""
        return float(np.hypot(self.di, self.dj).max())

    @property
    def nominal_length_m(self) -> np.ndarray:
        """Nominal (grid-metre) arc lengths [m], shape (K,)."""
        return np.hypot(self.di, self.dj) * self.dx

    @property
    def nominal_speed(self) -> np.ndarray:
        """Nominal arc ground speeds [m/s], shape (K,)."""
        return self.nominal_length_m / (self.span * self.dt_s)

    def angular_gap_deg(self, speed_range=None) -> float:
        """Largest angular gap [deg] between neighbouring distinct arc directions.

        Parameters
        ----------
        speed_range : tuple of float, optional  [m/s]
            Only arcs with nominal speed in this range count (e.g. the productive band).
        """
        sel = np.ones(self.di.size, bool)
        sel[0] = False
        if speed_range is not None:
            sel &= (self.nominal_speed >= speed_range[0]) & (self.nominal_speed <= speed_range[1])
        a = np.unique(np.round(np.degrees(np.arctan2(self.dj[sel], self.di[sel])) % 360.0, 6))
        gaps = np.diff(np.concatenate([a, [a[0] + 360.0]]))
        return float(gaps.max())

    @property
    def angular_resolution_deg(self) -> float:
        """Largest angular gap [deg] between neighbouring distinct arc directions."""
        return self.angular_gap_deg()


def build_stencil(grid: Grid, dt_s: float, u_bounds=(0.5, 8.0), slack: float = 0.05,
                  max_span: int = 2, **prune) -> Stencil:
    """Build the stencil and its per-cell geodesic lengths and headings.

    Parameters
    ----------
    grid : Grid
    dt_s : float  [s]  DP time step.
    u_bounds : tuple of float  [m/s]  ``(u_min, u_max)`` ground speed of an arc.
    slack : float  [-]  See :func:`stencil_offsets`.
    max_span : int
        Maximum number of DP steps spanned by one arc (1 = plain ring, ``stencil_offsets``;
        > 1 = pruned macro arcs, :func:`macro_arcs`, whose keyword options go in ``prune``).

    Returns
    -------
    Stencil
    """
    if max_span <= 1:
        di, dj = stencil_offsets(grid.dx, dt_s, u_bounds, slack)
        span = np.ones(di.size, dtype=np.int32)
    else:
        di, dj, span = macro_arcs(grid.dx, dt_s, u_bounds, max_span, slack, **prune)
    ny, nx, k = grid.ny, grid.nx, di.size
    lon, lat = grid.lonlat_mesh()
    geod = Geod(ellps="WGS84")
    length = np.full((ny, nx, k), np.nan, dtype=np.float32)
    head = np.full((ny, nx, k), np.nan, dtype=np.float32)
    valid = np.zeros((ny, nx, k), dtype=bool)
    length[..., 0] = 0.0
    valid[..., 0] = True
    for s in range(1, k):
        a, b = int(di[s]), int(dj[s])
        js = slice(max(0, -b), ny - max(0, b))
        is_ = slice(max(0, -a), nx - max(0, a))
        jd = slice(max(0, b), ny + min(0, b))
        id_ = slice(max(0, a), nx + min(0, a))
        if js.start >= js.stop or is_.start >= is_.stop:
            continue
        lo1, la1, lo2, la2 = lon[js, is_], lat[js, is_], lon[jd, id_], lat[jd, id_]
        az12, az21, dist = geod.inv(lo1.ravel(), la1.ravel(), lo2.ravel(), la2.ravel())
        az12, az21, dist = (np.asarray(v).reshape(lo1.shape) for v in (az12, az21, dist))
        back = np.radians(az21 + 180.0)
        fwd = np.radians(az12)
        h = np.degrees(np.arctan2(np.sin(fwd) + np.sin(back), np.cos(fwd) + np.cos(back))) % 360.0
        length[js, is_, s] = dist
        head[js, is_, s] = h
        u = dist / (span[s] * dt_s)
        valid[js, is_, s] = (u >= u_bounds[0]) & (u <= u_bounds[1])
    return Stencil(di, dj, float(grid.dx), float(dt_s), tuple(u_bounds), length, head, valid, span)
