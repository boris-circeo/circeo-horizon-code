"""Regular planning grids in a projected (equal-area) CRS.

Planning never happens on a lat-lon grid (DES-860 §4.7.2): cell areas and neighbour distances
would vary with latitude and bias the dynamic programme. A :class:`Grid` is a regular raster in a
Lambert Azimuthal Equal-Area projection centred on the basin.

Layout convention (see docs/CONVENTIONS.md): arrays are indexed ``[j, i]`` = ``[y, x]``, x eastward,
y northward, metres. Cell ``(j, i)`` has its centre at ``(x0 + i*dx, y0 + j*dx)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
from pyproj import CRS, Proj, Transformer

__all__ = ["Grid", "laea_crs"]


def laea_crs(lat0: float, lon0: float) -> CRS:
    """Lambert Azimuthal Equal-Area CRS centred on ``(lat0, lon0)`` [deg], WGS84 ellipsoid."""
    return CRS.from_proj4(
        f"+proj=laea +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"
    )


@dataclass(frozen=True)
class Grid:
    """Regular square-cell grid in a projected CRS.

    Parameters
    ----------
    crs_wkt : str
        WKT of the projected CRS.
    x0, y0 : float
        Projected coordinates of the centre of cell ``(0, 0)`` [m].
    dx : float
        Cell size (square cells) [m].
    nx, ny : int
        Number of cells along x and y.
    """

    crs_wkt: str
    x0: float
    y0: float
    dx: float
    nx: int
    ny: int
    _cache: dict = field(default_factory=dict, compare=False, repr=False, hash=False)

    # ------------------------------------------------------------------ constructors
    @classmethod
    def from_bbox(
        cls,
        lon_min: float,
        lon_max: float,
        lat_min: float,
        lat_max: float,
        dx: float,
        lat0: float | None = None,
        lon0: float | None = None,
    ) -> Grid:
        """Smallest grid of cell size ``dx`` [m] covering a lon/lat bounding box [deg].

        The projection is centred on the box centre unless ``lat0``/``lon0`` are given.
        """
        if not (lon_min < lon_max and lat_min < lat_max):
            raise ValueError("empty bounding box")
        if not (-180.0 <= lon_min and lon_max <= 180.0):
            raise ValueError("longitudes must lie in [-180, 180] (antimeridian not supported)")
        lat0 = 0.5 * (lat_min + lat_max) if lat0 is None else lat0
        lon0 = 0.5 * (lon_min + lon_max) if lon0 is None else lon0
        crs = laea_crs(lat0, lon0)
        tr = Transformer.from_crs(CRS.from_epsg(4326), crs, always_xy=True)
        # sample the box boundary densely: LAEA maps parallels to curves
        n = 200
        lons = np.concatenate([
            np.linspace(lon_min, lon_max, n), np.full(n, lon_max),
            np.linspace(lon_max, lon_min, n), np.full(n, lon_min),
        ])
        lats = np.concatenate([
            np.full(n, lat_min), np.linspace(lat_min, lat_max, n),
            np.full(n, lat_max), np.linspace(lat_max, lat_min, n),
        ])
        xs, ys = tr.transform(lons, lats)
        xmin, xmax, ymin, ymax = xs.min(), xs.max(), ys.min(), ys.max()
        nx = int(np.ceil((xmax - xmin) / dx)) + 1
        ny = int(np.ceil((ymax - ymin) / dx)) + 1
        return cls(crs.to_wkt(), float(xmin), float(ymin), float(dx), nx, ny)

    def coarsen(self, factor: int) -> Grid:
        """Grid with cells ``factor`` times larger covering (at least) the same extent."""
        if factor < 1:
            raise ValueError("factor must be >= 1")
        nx = int(np.ceil(self.nx / factor))
        ny = int(np.ceil(self.ny / factor))
        off = 0.5 * (factor - 1) * self.dx
        return Grid(self.crs_wkt, self.x0 + off, self.y0 + off, self.dx * factor, nx, ny)

    # ------------------------------------------------------------------ projection helpers
    @cached_property
    def crs(self) -> CRS:
        return CRS.from_wkt(self.crs_wkt)

    @cached_property
    def _fwd(self) -> Transformer:
        return Transformer.from_crs(CRS.from_epsg(4326), self.crs, always_xy=True)

    @cached_property
    def _inv(self) -> Transformer:
        return Transformer.from_crs(self.crs, CRS.from_epsg(4326), always_xy=True)

    def to_xy(self, lon, lat):
        """Geographic [deg] -> projected [m]. Returns ``(x, y)``."""
        return self._fwd.transform(lon, lat)

    def to_lonlat(self, x, y):
        """Projected [m] -> geographic [deg]. Returns ``(lon, lat)``."""
        return self._inv.transform(x, y)

    # ------------------------------------------------------------------ cell geometry
    @property
    def shape(self) -> tuple[int, int]:
        """Array shape ``(ny, nx)``."""
        return (self.ny, self.nx)

    @property
    def x(self) -> np.ndarray:
        """Cell-centre x coordinates [m], shape ``(nx,)``."""
        return self.x0 + self.dx * np.arange(self.nx)

    @property
    def y(self) -> np.ndarray:
        """Cell-centre y coordinates [m], shape ``(ny,)``."""
        return self.y0 + self.dx * np.arange(self.ny)

    def xy_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        """Cell-centre coordinates ``(X, Y)`` [m], each of shape ``(ny, nx)``."""
        return np.meshgrid(self.x, self.y)

    def lonlat_mesh(self) -> tuple[np.ndarray, np.ndarray]:
        """Cell-centre geographic coordinates ``(LON, LAT)`` [deg], each ``(ny, nx)``."""
        if "lonlat" not in self._cache:
            X, Y = self.xy_mesh()
            lon, lat = self.to_lonlat(X, Y)
            self._cache["lonlat"] = (np.asarray(lon), np.asarray(lat))
        return self._cache["lonlat"]

    def index_of(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """Nearest cell indices ``(j, i)`` of projected points [m] (no bounds clipping)."""
        i = np.rint((np.asarray(x) - self.x0) / self.dx).astype(np.int64)
        j = np.rint((np.asarray(y) - self.y0) / self.dx).astype(np.int64)
        return j, i

    def contains(self, x, y) -> np.ndarray:
        """True where projected points [m] fall inside the grid extent (cell edges included)."""
        x = np.asarray(x)
        y = np.asarray(y)
        h = 0.5 * self.dx
        return (
            (x >= self.x0 - h) & (x <= self.x0 + (self.nx - 1) * self.dx + h)
            & (y >= self.y0 - h) & (y <= self.y0 + (self.ny - 1) * self.dx + h)
        )

    def grid_convergence(self, lon, lat) -> np.ndarray:
        """Meridian convergence ``gamma`` [deg] as returned by PROJ ``meridian_convergence``.

        The grid bearing of true north is ``-gamma``. Informative only: LAEA is equal-area, not
        conformal, so headings other than north are *not* converted by a pure rotation (errors up
        to ~1 deg at basin edges). Use :meth:`local_basis` / the heading helpers instead.
        """
        f = Proj(self.crs).get_factors(np.asarray(lon, float), np.asarray(lat, float))
        return np.asarray(f.meridian_convergence)

    def local_basis(self, lon, lat) -> tuple[np.ndarray, np.ndarray]:
        """Grid-frame images of the local true east and north directions.

        Returns
        -------
        e_east, e_north : ndarray, shape ``(..., 2)``
            Grid-frame images (grid metres per ground metre) of a unit ground displacement towards
            true east and true north: the columns of the local projection Jacobian, obtained by
            projecting 10 m geodesic steps. Not unit-length and not orthogonal in general
            (LAEA is equal-area, not conformal).
        """
        from pyproj import Geod

        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        s = 10.0
        geod = Geod(ellps="WGS84")
        lon_e, lat_e, _ = geod.fwd(lon, lat, np.full_like(lon, 90.0), np.full_like(lon, s))
        lon_n, lat_n, _ = geod.fwd(lon, lat, np.zeros_like(lon), np.full_like(lon, s))
        x0, y0 = self.to_xy(lon, lat)
        xe, ye = self.to_xy(lon_e, lat_e)
        xn, yn = self.to_xy(lon_n, lat_n)
        e = np.stack([np.asarray(xe) - x0, np.asarray(ye) - y0], axis=-1) / s
        n = np.stack([np.asarray(xn) - x0, np.asarray(yn) - y0], axis=-1) / s
        return e, n

    def grid_vector_to_true_heading(self, gx, gy, lon, lat) -> np.ndarray:
        """True heading [deg, cw from true north] of a displacement ``(gx, gy)`` in grid frame.

        Solves ``(gx, gy) = a * e_east + b * e_north`` and returns ``atan2(a, b)``.
        """
        e, n = self.local_basis(lon, lat)
        gx = np.asarray(gx, float)
        gy = np.asarray(gy, float)
        det = e[..., 0] * n[..., 1] - e[..., 1] * n[..., 0]
        a = (gx * n[..., 1] - gy * n[..., 0]) / det
        b = (e[..., 0] * gy - e[..., 1] * gx) / det
        return np.mod(np.degrees(np.arctan2(a, b)), 360.0)

    def true_to_grid_heading(self, psi_true, lon, lat) -> np.ndarray:
        """Convert a true heading [deg, cw from true north] to a grid heading [deg, cw from +y]."""
        e, n = self.local_basis(lon, lat)
        p = np.radians(np.asarray(psi_true, float))
        g = np.sin(p)[..., None] * e + np.cos(p)[..., None] * n
        return np.mod(np.degrees(np.arctan2(g[..., 0], g[..., 1])), 360.0)

    def grid_to_true_heading(self, psi_grid, lon, lat) -> np.ndarray:
        """Inverse of :meth:`true_to_grid_heading`."""
        p = np.radians(np.asarray(psi_grid, float))
        return self.grid_vector_to_true_heading(np.sin(p), np.cos(p), lon, lat)
