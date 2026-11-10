"""ERA5 10 m wind ingestion: monthly GRIB1 -> planning grid, cached as compressed ``.npz``.

The client ERA5 files (``wind_YYYY_MM.grib``, hourly ``u10``/``v10``, 0.25 deg) are PROPRIETARY and
CONFIDENTIAL: they are read from a directory outside the repository and the regridded cache is
written under ``data/cache/era5/`` (git-ignored). Never commit data files.

Conventions (docs/CONVENTIONS.md, DES-860 §7.1, §7.5)
* ``u10`` is the eastward and ``v10`` the northward component of the air motion ("toward"
  convention) and are kept as **true east/north components** on the planning grid. They are
  interpolated bilinearly **in (u, v) components**, never in (speed, direction).
* All times are UTC (``numpy.datetime64[s]``); ERA5 valid times are UTC.
* Regridding is bilinear in the (lon, lat) index space of the regular ERA5 grid, evaluated at the
  geographic position of each planning-grid cell centre. Cells of the (LAEA) planning grid lying
  outside the ERA5 box (corners) are filled with the nearest edge value (index clamping); the
  fraction of such cells is available as :attr:`ERA5Archive.frac_outside`.

Reading GRIB needs the optional dependencies ``xarray`` and ``cfgrib`` (+ ``eccodes``), see
``pip install horizon-router[data]``. Reading an existing cache needs only numpy.
"""

from __future__ import annotations

import hashlib
import time
import warnings
from collections import OrderedDict
from pathlib import Path

import numpy as np

from horizon.geo.grid import Grid
from horizon.weather.fields import WindField

__all__ = ["ERA5Archive", "ERA5_BOX", "DEFAULT_CACHE_DIR", "regrid_indices", "regrid_uv",
           "grid_signature"]

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = _REPO / "data" / "cache" / "era5"
_HOUR = 3600.0
ERA5_BOX = (-32.0, 5.0, 38.0, 65.0)
"""Lon/lat box ``(lon_min, lon_max, lat_min, lat_max)`` [deg] of the client ERA5 files."""


def grid_signature(grid: Grid) -> str:
    """Short hash identifying a planning grid (used in cache file names)."""
    s = f"{grid.crs_wkt}|{grid.x0:.3f}|{grid.y0:.3f}|{grid.dx:.3f}|{grid.nx}|{grid.ny}"
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def regrid_indices(grid: Grid, lon_src: np.ndarray, lat_src: np.ndarray):
    """Bilinear stencil from a regular lon/lat source grid to the cell centres of ``grid``.

    Parameters
    ----------
    grid : Grid
        Target planning grid.
    lon_src, lat_src : ndarray (1-D)  [deg]
        Source axes, regular and strictly monotonic (latitude may be descending as in ERA5).

    Returns
    -------
    j0, i0 : ndarray int (Ny, Nx)
        Lower-left source indices (``lat``, ``lon`` axes).
    wj, wi : ndarray float64 (Ny, Nx)
        Fractional offsets in ``[0, 1]`` along the lat and lon axes.
    outside : ndarray bool (Ny, Nx)
        True where the cell centre lies outside the source box (values clamped to the edge).
    """
    lon, lat = grid.lonlat_mesh()
    dlon = (lon_src[-1] - lon_src[0]) / (lon_src.size - 1)
    dlat = (lat_src[-1] - lat_src[0]) / (lat_src.size - 1)
    fi = (lon - lon_src[0]) / dlon
    fj = (lat - lat_src[0]) / dlat
    outside = (fi < 0) | (fi > lon_src.size - 1) | (fj < 0) | (fj > lat_src.size - 1)
    fi = np.clip(fi, 0.0, lon_src.size - 1.0)
    fj = np.clip(fj, 0.0, lat_src.size - 1.0)
    i0 = np.minimum(np.floor(fi).astype(np.int64), lon_src.size - 2)
    j0 = np.minimum(np.floor(fj).astype(np.int64), lat_src.size - 2)
    return j0, i0, fj - j0, fi - i0, outside


def regrid_uv(u: np.ndarray, v: np.ndarray, stencil) -> np.ndarray:
    """Bilinear regridding of source ``(T, Nlat, Nlon)`` component fields.

    Parameters
    ----------
    u, v : ndarray (T, Nlat, Nlon)  [m/s]
        True eastward / northward components on the source grid.
    stencil : tuple
        Output of :func:`regrid_indices`.

    Returns
    -------
    ndarray float32 (T, Ny, Nx, 2)  [m/s]
        Components interpolated **in (u, v)**; bilinear interpolation is exact on linear fields.
    """
    j0, i0, wj, wi, _ = stencil
    out = np.empty((u.shape[0],) + j0.shape + (2,), np.float32)
    w00 = ((1 - wj) * (1 - wi)).astype(np.float32)
    w01 = ((1 - wj) * wi).astype(np.float32)
    w10 = (wj * (1 - wi)).astype(np.float32)
    w11 = (wj * wi).astype(np.float32)
    for c, a in enumerate((u, v)):
        a = np.asarray(a, np.float32)
        out[..., c] = (a[:, j0, i0] * w00 + a[:, j0, i0 + 1] * w01
                       + a[:, j0 + 1, i0] * w10 + a[:, j0 + 1, i0 + 1] * w11)
    return out


def _month_hours(year: int, month: int) -> int:
    t0 = np.datetime64(f"{year:04d}-{month:02d}", "M")
    d = (t0 + np.timedelta64(1, "M")).astype("datetime64[h]") - t0.astype("datetime64[h]")
    return int(d / np.timedelta64(1, "h"))


class ERA5Archive:
    """Hourly ERA5 10 m wind of one year on a planning grid, backed by a per-month ``.npz`` cache.

    Parameters
    ----------
    source : str or Path
        Directory holding either the raw ``wind_YYYY_MM.grib`` files (then the cache goes to
        ``cache_dir``) or an already built cache (``era5_uv_*.npz``).
    grid : Grid
        Planning grid (any resolution; e.g. ``Grid.from_bbox(-32, 5, 38, 65, 40e3)``).
    cache_dir : str or Path, optional
        Cache directory; default ``data/cache/era5`` of the repository (git-ignored).
    year : int, optional
        Year of the files; autodetected from the file names if omitted.
    max_cached_months : int
        Number of months kept decompressed in memory (LRU).

    Attributes
    ----------
    outside : ndarray bool (Ny, Nx)
        Cells whose centre lies outside the ERA5 box (value = nearest edge); ``frac_outside`` is
        their fraction (about 26 % on the 40 km LAEA basin grid: the bounding rectangle of the
        curved lon/lat box has empty corners).

    Notes
    -----
    Cached values are float32 ``(T_month, Ny, Nx, 2)`` true (east, north) wind [m/s].
    """

    def __init__(self, source, grid: Grid, cache_dir=None, year: int | None = None,
                 max_cached_months: int = 3):
        self.source = Path(source)
        self.grid = grid
        self.cache_dir = Path(cache_dir) if cache_dir is not None else (
            DEFAULT_CACHE_DIR if list(self.source.glob("wind_*.grib")) else self.source)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sig = grid_signature(grid)
        self.year = year if year is not None else self._detect_year()
        self._lru: OrderedDict[int, np.ndarray] = OrderedDict()
        self._max = max_cached_months
        self._hours = [_month_hours(self.year, m) for m in range(1, 13)]
        self._offset = np.concatenate([[0], np.cumsum(self._hours)])
        self.start = np.datetime64(f"{self.year:04d}-01-01T00:00:00", "s")
        self.end = np.datetime64(f"{self.year + 1:04d}-01-01T00:00:00", "s") - np.timedelta64(
            3600, "s")
        lon, lat = grid.lonlat_mesh()
        lo, hi, la, lb = ERA5_BOX
        self.outside = (lon < lo) | (lon > hi) | (lat < la) | (lat > lb)
        self.frac_outside = float(self.outside.mean())
        self.ingest_seconds: dict[int, float] = {}

    # ------------------------------------------------------------------ files
    def _detect_year(self) -> int:
        for pat, pos in (("wind_*_??.grib", 1), ("era5_uv_*_??_*.npz", 1)):
            for f in sorted(self.source.glob(pat)):
                try:
                    return int(f.stem.split("_")[pos])
                except ValueError:
                    continue
        for f in sorted(self.cache_dir.glob("era5_uv_*_??_*.npz")):
            return int(f.stem.split("_")[2])
        raise FileNotFoundError(f"no ERA5 GRIB or cache files found in {self.source}")

    def cache_path(self, month: int) -> Path:
        """Cache file of ``month`` (1-12) for this grid."""
        return self.cache_dir / (
            f"era5_uv_{self.year}_{month:02d}_dx{int(round(self.grid.dx))}_{self._sig}.npz")

    def grib_path(self, month: int) -> Path:
        """Raw GRIB file of ``month`` (1-12)."""
        return self.source / f"wind_{self.year}_{month:02d}.grib"

    # ------------------------------------------------------------------ ingestion
    def build_month(self, month: int, force: bool = False) -> float:
        """Regrid one GRIB month and write its cache file.

        Returns
        -------
        float
            Wall time [s] (0.0 if the cache already existed and ``force`` is False).
        """
        path = self.cache_path(month)
        if path.exists() and not force:
            return 0.0
        gp = self.grib_path(month)
        if not gp.exists():
            raise FileNotFoundError(f"neither cache {path.name} nor GRIB {gp} available")
        import xarray as xr  # optional dependency

        t0 = time.perf_counter()
        ds = xr.open_dataset(gp, engine="cfgrib", backend_kwargs={"indexpath": ""})
        try:
            lat = np.asarray(ds["latitude"].values, float)
            lon = np.asarray(ds["longitude"].values, float)
            vt = np.asarray(ds["valid_time"].values).astype("datetime64[s]")
            exp = (np.datetime64(f"{self.year:04d}-{month:02d}-01T00:00:00", "s")
                   + np.arange(self._hours[month - 1]) * np.timedelta64(3600, "s"))
            if vt.shape != exp.shape or not np.array_equal(vt, exp):
                raise ValueError(f"{gp.name}: valid times are not the expected hourly UTC month")
            stencil = regrid_indices(self.grid, lon, lat)
            uv = regrid_uv(ds["u10"].values, ds["v10"].values, stencil)
        finally:
            ds.close()
        tmp = path.with_name(path.name + ".tmp.npz")
        np.savez_compressed(tmp, uv=uv, year=self.year, month=month)
        tmp.replace(path)
        dt = time.perf_counter() - t0
        self.ingest_seconds[month] = dt
        return dt

    def build_cache(self, months=range(1, 13), force: bool = False, verbose: bool = False) -> dict:
        """Build the cache for ``months``; returns ``{"seconds": total, "bytes": cache size}``."""
        t0 = time.perf_counter()
        for m in months:
            dt = self.build_month(m, force)
            if verbose:
                print(f"  month {m:02d}: {dt:6.1f} s", flush=True)
        size = sum(self.cache_path(m).stat().st_size for m in months if self.cache_path(m).exists())
        return {"seconds": time.perf_counter() - t0, "bytes": size}

    # ------------------------------------------------------------------ access
    def _month(self, month: int) -> np.ndarray:
        if month in self._lru:
            self._lru.move_to_end(month)
            return self._lru[month]
        self.build_month(month)
        with np.load(self.cache_path(month)) as z:
            uv = z["uv"]
        self._lru[month] = uv
        while len(self._lru) > self._max:
            self._lru.popitem(last=False)
        return uv

    @property
    def n_hours(self) -> int:
        """Number of hourly steps in the year."""
        return int(self._offset[-1])

    def hours(self, h0: int, h1: int) -> np.ndarray:
        """Hourly fields for global hour indices ``h0 <= h < h1`` (since 1 Jan 00 UTC).

        Spans month boundaries transparently. Returns float32 ``(h1-h0, Ny, Nx, 2)`` [m/s].
        """
        if h0 < 0 or h1 > self.n_hours or h1 <= h0:
            raise IndexError(f"hours [{h0}, {h1}) outside [0, {self.n_hours})")
        parts = []
        for m in range(12):
            lo, hi = int(self._offset[m]), int(self._offset[m + 1])
            a, b = max(h0, lo), min(h1, hi)
            if a < b:
                parts.append(self._month(m + 1)[a - lo:b - lo])
        return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)

    def fields_at(self, t_s: np.ndarray, epoch, fill: str = "error") -> np.ndarray:
        """Wind at arbitrary times, linear in time between the hourly fields.

        Parameters
        ----------
        t_s : ndarray (n,)  [s since ``epoch``]
        epoch : numpy.datetime64  UTC instant of ``t_s = 0``.
        fill : {'error', 'wrap'}
            Behaviour outside the data span (1 Jan 00 UTC .. 31 Dec 23 UTC): raise, or wrap the
            time modulo the data length (climatology-style fill; discontinuous at the seam).

        Returns
        -------
        ndarray float32 (n, Ny, Nx, 2)  [m/s]
        """
        t_s = np.asarray(t_s, float)
        h = (np.datetime64(epoch, "s") - self.start) / np.timedelta64(1, "s") / _HOUR \
            + t_s / _HOUR
        n = self.n_hours
        if h.min() < 0 or h.max() > n - 1:
            if fill == "error":
                raise ValueError("requested times outside the ERA5 data span "
                                 f"{self.start} .. {self.end} (use fill='wrap')")
            warnings.warn("ERA5 request beyond the data span: wrapping to the start of the year "
                          "(climatology-style fill)", stacklevel=2)
            h = np.mod(h, n - 1)  # keeps h in [0, n-1): last hour + fraction interpolates back
        k0 = np.minimum(np.floor(h).astype(np.int64), n - 2)
        w = (h - k0).astype(np.float32)
        lo, hi = int(k0.min()), int(k0.max()) + 2
        block = self.hours(lo, hi)
        a = block[k0 - lo]
        b = block[k0 - lo + 1]
        return a + (b - a) * w[:, None, None, None]

    def truth(self, start, end, dt_s: float = 3600.0, fill: str = "error") -> WindField:
        """Wind truth between two UTC instants, spanning month boundaries.

        Parameters
        ----------
        start, end : numpy.datetime64 (or ISO string)  UTC instants, ``end >= start``.
        dt_s : float  [s]  Output time step.
        fill : {'error', 'wrap'}  See :meth:`fields_at`.

        Returns
        -------
        WindField
            ``epoch = start``; ``times_s = 0, dt_s, ...`` up to ``end``; true (east, north) [m/s].
        """
        start = np.datetime64(start, "s")
        end = np.datetime64(end, "s")
        span = float((end - start) / np.timedelta64(1, "s"))
        if span < 0:
            raise ValueError("end before start")
        t = np.arange(0.0, span + 0.5 * dt_s, dt_s)
        return WindField(self.grid, start, t, np.ascontiguousarray(self.fields_at(t, start, fill)))
