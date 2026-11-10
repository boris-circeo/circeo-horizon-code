"""Coastline, land mask and signed distance to coast (SDF) on a planning grid.

The SDF is the field used by the routing constraint ``SDF(s) >= d_min`` (DES-860 §7.1, A.1):
positive at sea (distance to the nearest land [m]), negative on land (minus the distance to the
nearest sea [m]). Land comes from Natural Earth (public domain) polygons.

Scale-factor note
-----------------
Distances are computed in *grid* metres. The LAEA projection is equal-area but not conformal: at
angular distance ``rho`` from the projection centre the radial scale is ``cos(rho/2)`` and the
tangential scale ``1/cos(rho/2)``. Over the default North-Atlantic basin (10 km grid, 355 x 453
cells) the PROJ scale factors span 0.989-1.028 (meridional) and 0.973-1.011 (parallel): grid
metres differ from ground metres by at most ~3 %, depending on the direction to the coast, and by
less than 1 % near the centre. No correction is applied: the true correction is direction
dependent, so a scalar rescaling of an isotropic EDT would be wrong in one of the two directions
anyway, the error is small against ``d_min`` safety margins, and the dynamic programme works in
the same grid metres (consistency). Use :func:`scale_factors` to quantify it, or add margin to
``d_min``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from numba import njit
from pyproj import Proj
from scipy import ndimage

from horizon.geo.grid import Grid

__all__ = [
    "CoastModel",
    "SDF_TOL_M",
    "bilinear_sdf",
    "port_corridor",
    "segment_min_bilinear",
    "build_basin_coast",
    "load_land_polygons",
    "rasterize_land",
    "scale_factors",
    "signed_distance",
]

_REPO = Path(__file__).resolve().parents[3]
_ASSET_DIR = Path(__file__).parent / "assets"
_NE_DIR = _REPO / "data" / "external" / "naturalearth"
_CACHE_DIR = _REPO / "data" / "cache"
DEFAULT_BBOX = (-45.0, 5.0, 35.0, 65.0)  # lon_min, lon_max, lat_min, lat_max [deg]
SDF_TOL_M = 1e-3  # [m] numerical tolerance of every ``SDF >= d_min`` test (float round-off only)


# ---------------------------------------------------------------------------------------- land
def load_land_polygons(path, bbox):
    """Read a Natural Earth land shapefile and clip it to a lon/lat box.

    Parameters
    ----------
    path : str or Path
        Path to ``ne_*_land.shp``.
    bbox : tuple of float
        ``(lon_min, lon_max, lat_min, lat_max)`` [deg], margin already included by the caller.

    Returns
    -------
    shapely.Geometry
        Land (multi)polygon in lon/lat [deg], clipped to ``bbox`` (possibly empty).
    """
    import shapefile  # pyshp

    lon_min, lon_max, lat_min, lat_max = bbox
    box = shapely.box(lon_min, lat_min, lon_max, lat_max)
    geoms = []
    with shapefile.Reader(str(path)) as shp:
        for shape in shp.shapes():
            if not shape.points:
                continue
            x0, y0, x1, y1 = shape.bbox
            if x1 < lon_min or x0 > lon_max or y1 < lat_min or y0 > lat_max:
                continue
            g = shapely.make_valid(shapely.geometry.shape(shape.__geo_interface__))
            geoms.append(shapely.intersection(g, box))
    return shapely.union_all(geoms) if geoms else shapely.GeometryCollection()


def rasterize_land(grid: Grid, land_geom, supersample: int = 1, chunk: int = 200_000):
    """Rasterize lon/lat land polygons onto a grid.

    Polygon edges are densified (0.05 deg) before projection to the grid CRS so that LAEA
    curvature of straight lon/lat edges is respected.

    Parameters
    ----------
    grid : Grid
        Target grid.
    land_geom : shapely.Geometry
        Land in lon/lat [deg].
    supersample : int
        Sub-samples per cell side; a cell is land if >= 50 % of its ``supersample**2`` points are
        inside (1 = test the cell centre only).
    chunk : int
        Points per ``contains_xy`` call (memory bound).

    Returns
    -------
    ndarray of bool, shape ``(ny, nx)``
        True = land.
    """
    if land_geom.is_empty:
        return np.zeros(grid.shape, dtype=bool)
    dense = shapely.segmentize(land_geom, 0.05)
    proj = shapely.transform(dense, lambda c: np.column_stack(grid.to_xy(c[:, 0], c[:, 1])))
    proj = shapely.make_valid(proj)
    shapely.prepare(proj)
    s = int(supersample)
    off = (np.arange(s) + 0.5) / s - 0.5  # sub-sample offsets in cell units
    X, Y = grid.xy_mesh()
    acc = np.zeros(grid.shape, dtype=np.int32)
    for oy in off:
        for ox in off:
            px = (X + ox * grid.dx).ravel()
            py = (Y + oy * grid.dx).ravel()
            out = np.empty(px.size, dtype=bool)
            for a in range(0, px.size, chunk):
                out[a:a + chunk] = shapely.contains_xy(proj, px[a:a + chunk], py[a:a + chunk])
            acc += out.reshape(grid.shape)
    return acc * 2 >= s * s


# ---------------------------------------------------------------------------------------- SDF
def signed_distance(grid: Grid, land_mask: np.ndarray) -> np.ndarray:
    """Signed distance to the coast [m]: positive at sea, negative on land.

    Euclidean distance transforms (``sampling=grid.dx``) give the distance between cell *centres*
    of a sea cell and the nearest land cell (and vice versa). The coast lies midway between an
    adjacent land/sea pair, so half a cell is subtracted: a sea cell next to land gets ``+dx/2``,
    a land cell next to sea gets ``-dx/2``. Distances are in grid metres (see module note).

    Parameters
    ----------
    grid : Grid
        Grid the mask lives on.
    land_mask : ndarray of bool, shape ``(ny, nx)``
        True = land.

    Returns
    -------
    ndarray of float32, shape ``(ny, nx)``  [m]
        If the mask is all sea (or all land) the distance saturates at the grid diagonal.
    """
    land = np.asarray(land_mask, dtype=bool)
    if land.shape != grid.shape:
        raise ValueError(f"mask shape {land.shape} != grid shape {grid.shape}")
    big = float(np.hypot(grid.nx, grid.ny) * grid.dx)
    half = 0.5 * grid.dx
    if land.all() or not land.any():
        return np.full(grid.shape, -big if land.all() else big, dtype=np.float32)
    d_sea = ndimage.distance_transform_edt(~land, sampling=grid.dx) - half
    d_land = ndimage.distance_transform_edt(land, sampling=grid.dx) - half
    return np.where(land, -d_land, d_sea).astype(np.float32)


def scale_factors(grid: Grid) -> tuple[np.ndarray, np.ndarray]:
    """Projection distance scales over the grid (grid metres per ground metre).

    Returns
    -------
    h, k : ndarray, shape ``(ny, nx)``
        Meridional and parallel scale factors from PROJ [-]. Their deviation from 1 bounds the
        relative error of grid-metre distances.
    """
    lon, lat = grid.lonlat_mesh()
    f = Proj(grid.crs).get_factors(lon, lat)
    return np.asarray(f.meridional_scale), np.asarray(f.parallel_scale)


# ----------------------------------------------------------------------------- interpolation
@njit(cache=True)
def bilinear_sdf(field, x0, y0, dx, x, y):
    """Bilinear interpolation of a ``[j, i]`` field at projected point ``(x, y)`` [m].

    Numba-compatible scalar kernel. Returns ``nan`` outside the cell-centre extent of the grid.

    Parameters
    ----------
    field : ndarray, shape ``(ny, nx)``
    x0, y0 : float
        Projected coordinates of cell ``(0, 0)`` centre [m].
    dx : float
        Cell size [m].
    x, y : float
        Query point [m].
    """
    fi = (x - x0) / dx
    fj = (y - y0) / dx
    ny, nx = field.shape
    if not (fi >= 0.0 and fj >= 0.0 and fi <= nx - 1 and fj <= ny - 1):
        return np.nan
    i = min(int(fi), nx - 2)
    j = min(int(fj), ny - 2)
    a = fi - i
    b = fj - j
    return (
        (1 - a) * (1 - b) * field[j, i] + a * (1 - b) * field[j, i + 1]
        + (1 - a) * b * field[j + 1, i] + a * b * field[j + 1, i + 1]
    )


@njit(cache=True)
def segment_min_bilinear(field, x0, y0, dx, xa, ya, xb, yb):
    """EXACT minimum of the bilinear interpolant of ``field`` along the segment ``a -> b``.

    Inside one grid cell the bilinear interpolant restricted to a straight line is a quadratic in
    the line parameter; the segment is cut at every grid line it crosses and the minimum of each
    quadratic piece (end points and vertex) is taken. This is the single "SDF along a chord"
    primitive shared by the DP arc feasibility, the refiner verification, the simulator guard and
    the tests, so that all of them evaluate the SAME (bilinear) field with no sampling gap.

    Returns ``nan`` if an end point lies outside the cell-centre extent of the grid.
    """
    ny, nx = field.shape
    fa = (xa - x0) / dx
    ga = (ya - y0) / dx
    fb = (xb - x0) / dx
    gb = (yb - y0) / dx
    ok = (fa >= 0.0 and ga >= 0.0 and fb >= 0.0 and gb >= 0.0 and fa <= nx - 1 and fb <= nx - 1
          and ga <= ny - 1 and gb <= ny - 1)
    if not ok:
        return np.nan
    di = fb - fa
    dj = gb - ga
    cap = int(abs(di)) + int(abs(dj)) + 6
    ts = np.empty(cap)
    n = 0
    ts[n] = 0.0
    n += 1
    ts[n] = 1.0
    n += 1
    if di != 0.0:
        k0 = int(np.ceil(min(fa, fb)))
        k1 = int(np.floor(max(fa, fb)))
        for k in range(k0, k1 + 1):
            t = (k - fa) / di
            if t > 0.0 and t < 1.0 and n < cap:
                ts[n] = t
                n += 1
    if dj != 0.0:
        k0 = int(np.ceil(min(ga, gb)))
        k1 = int(np.floor(max(ga, gb)))
        for k in range(k0, k1 + 1):
            t = (k - ga) / dj
            if t > 0.0 and t < 1.0 and n < cap:
                ts[n] = t
                n += 1
    ts = np.sort(ts[:n])
    best = np.inf
    for p in range(n - 1):
        t0 = ts[p]
        t1 = ts[p + 1]
        if t1 <= t0:
            continue
        tm = 0.5 * (t0 + t1)
        i = min(max(int(fa + di * tm), 0), nx - 2)
        j = min(max(int(ga + dj * tm), 0), ny - 2)
        a0 = fa + di * t0 - i
        b0 = ga + dj * t0 - j
        f00 = field[j, i]
        f10 = field[j, i + 1]
        f01 = field[j + 1, i]
        f11 = field[j + 1, i + 1]
        cb = f10 - f00
        cc = f01 - f00
        cd = f11 - f10 - f01 + f00
        da = di * (t1 - t0)
        db = dj * (t1 - t0)
        c0 = f00 + cb * a0 + cc * b0 + cd * a0 * b0
        c1 = cb * da + cc * db + cd * (a0 * db + b0 * da)
        c2 = cd * da * db
        v1 = c0 + c1 + c2
        if c0 < best:
            best = c0
        if v1 < best:
            best = v1
        if c2 > 0.0:
            sv = -c1 / (2.0 * c2)
            if sv > 0.0 and sv < 1.0:
                vv = c0 + c1 * sv + c2 * sv * sv
                if vv < best:
                    best = vv
    return best


@njit(cache=True)
def _segmin_many(field, x0, y0, dx, xa, ya, xb, yb, out):
    for k in range(xa.size):
        out[k] = segment_min_bilinear(field, x0, y0, dx, xa[k], ya[k], xb[k], yb[k])


@njit(cache=True)
def _bilinear_many(field, x0, y0, dx, xs, ys, out):
    for k in range(xs.size):
        out[k] = bilinear_sdf(field, x0, y0, dx, xs[k], ys[k])


@dataclass(frozen=True)
class CoastModel:
    """Grid plus signed distance to coast.

    Parameters
    ----------
    grid : Grid
    sdf : ndarray of float32, shape ``(ny, nx)``  [m]
        Positive at sea, negative on land.
    """

    grid: Grid
    sdf: np.ndarray
    relax: np.ndarray | None = None

    @property
    def true_sdf(self) -> np.ndarray:
        """Physical SDF [m] (``sdf`` minus the harbour-corridor relaxation, see
        :func:`port_corridor`); equals ``sdf`` if there is no corridor."""
        return self.sdf if self.relax is None else self.sdf - self.relax

    @property
    def land_mask(self) -> np.ndarray:
        """Bool ``(ny, nx)``, True where ``sdf < 0``."""
        return self.sdf < 0

    def sdf_at(self, x, y) -> np.ndarray:
        """Bilinear SDF [m] at projected points ``(x, y)`` [m]; ``nan`` outside the grid."""
        xa, ya = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        out = np.empty(xa.size)
        g = self.grid
        _bilinear_many(self.sdf, g.x0, g.y0, g.dx, np.ascontiguousarray(xa.ravel()),
                       np.ascontiguousarray(ya.ravel()), out)
        return out.reshape(xa.shape)

    def segment_min(self, xa, ya, xb, yb) -> np.ndarray:
        """EXACT minimum [m] of the bilinear SDF along straight (grid-frame) chords ``a -> b``;
        ``nan`` if an end point is outside the grid (see :func:`segment_min_bilinear`)."""
        xa, ya, xb, yb = np.broadcast_arrays(*(np.asarray(v, float) for v in (xa, ya, xb, yb)))
        out = np.empty(xa.size)
        g = self.grid
        _segmin_many(self.sdf, g.x0, g.y0, g.dx, *(np.ascontiguousarray(v.ravel())
                                                   for v in (xa, ya, xb, yb)), out)
        return out.reshape(xa.shape)

    def sdf_at_lonlat(self, lon, lat) -> np.ndarray:
        """Bilinear SDF [m] at geographic points [deg]."""
        x, y = self.grid.to_xy(lon, lat)
        return self.sdf_at(x, y)

    def is_navigable(self, x, y, d_min: float) -> np.ndarray:
        """True where ``SDF >= d_min`` [m] (DES-860 A.1); False outside the grid."""
        return self.sdf_at(x, y) >= d_min - SDF_TOL_M

    def save_npz(self, path) -> None:
        """Write grid definition and SDF to a compressed ``.npz``."""
        g = self.grid
        np.savez_compressed(
            path, sdf=self.sdf, crs_wkt=np.array(g.crs_wkt),
            geom=np.array([g.x0, g.y0, g.dx, g.nx, g.ny], dtype=np.float64),
        )

    @classmethod
    def load_npz(cls, path) -> CoastModel:
        """Inverse of :meth:`save_npz`."""
        with np.load(path) as z:
            x0, y0, dx, nx, ny = z["geom"]
            grid = Grid(str(z["crs_wkt"]), float(x0), float(y0), float(dx), int(nx), int(ny))
            return cls(grid, z["sdf"].astype(np.float32))


# --------------------------------------------------------------------------------- builder
def build_basin_coast(dx=10_000.0, bbox=DEFAULT_BBOX, source=None, supersample=1,
                      use_cache=True) -> CoastModel:
    """Build (or load from cache/asset) the SDF of a basin.

    Lookup order for the default basin at 10 km: committed asset, then ``data/cache``, then
    build from Natural Earth. Anything else is cached under ``data/cache``.

    Parameters
    ----------
    dx : float
        Cell size [m].
    bbox : tuple of float
        ``(lon_min, lon_max, lat_min, lat_max)`` [deg].
    source : str or Path, optional
        ``ne_*_land.shp``; default 10 m resolution from ``data/external/naturalearth``, else 50 m.
    supersample : int
        See :func:`rasterize_land`.
    use_cache : bool
        Read/write the asset and cache files.
    """
    name = f"coast_sdf_dx{int(dx)}_{'_'.join(f'{b:g}' for b in bbox)}_ss{supersample}.npz"
    if use_cache and source is None:
        for d in (_ASSET_DIR, _CACHE_DIR):
            if (d / name).exists():
                return CoastModel.load_npz(d / name)
    if source is None:
        for res in ("10m", "50m"):
            cand = _NE_DIR / f"ne_{res}_land.shp"
            if cand.exists():
                source = cand
                break
        else:
            raise FileNotFoundError(f"no Natural Earth land in {_NE_DIR}; run "
                                    "scripts/fetch_naturalearth.sh")
    grid = Grid.from_bbox(*bbox, dx)
    lon, lat = grid.lonlat_mesh()
    m = 1.0  # [deg] margin around the grid's true lon/lat footprint
    ext = (max(lon.min() - m, -180.0), min(lon.max() + m, 180.0),
           max(lat.min() - m, -90.0), min(lat.max() + m, 90.0))
    land = rasterize_land(grid, load_land_polygons(source, ext), supersample)
    model = CoastModel(grid, signed_distance(grid, land))
    if use_cache:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        model.save_npz(_CACHE_DIR / name)
    return model


# ------------------------------------------------------------------------------ harbour corridor
def port_corridor(coast: CoastModel, lon: float, lat: float, d_min: float = 20e3,
                  d_port: float = 1e3, ramp_m: float = 40e3) -> CoastModel:
    """Coast model whose clearance requirement ramps from ``d_port`` at a port to ``d_min``.

    The position-dependent requirement ``SDF(x) >= d_req(x)`` with
    ``d_req(x) = d_port + (d_min - d_port) min(r(x) / ramp_m, 1)``, ``r`` the grid-frame distance
    to the port [m], is represented by an SDF *relaxation*: ``sdf' = sdf + relax`` with
    ``relax = d_min - d_req`` so that ``sdf' >= d_min  <=>  sdf >= d_req``. Everything downstream
    (DP arc feasibility, refiner, simulator guard and violation metric) keeps testing
    ``sdf' >= d_min`` on the bilinear interpolant of ``sdf'`` and needs no other change; the
    relaxation vanishes beyond ``ramp_m`` (+ half a cell) so the nominal SDF is untouched there.
    Land stays unreachable because the effective requirement never drops below ``d_port``
    (``> 0``) or the physical SDF at the port.

    Grid resolution. ``relax`` lives on the grid nodes and is interpolated bilinearly like the SDF
    (that is what makes it consistent everywhere). A cone with a 40 km base cannot be resolved on
    a 40 km grid, so the node values are the design ramp at the node and the four corners of the
    cell containing the port get the full relaxation so that the port itself is always feasible.
    The effective ramp is therefore the bilinear interpolant: it ends at about
    ``ramp_m + 1.5 dx`` from the port and is accurate to about one cell (use a finer grid or a
    larger ``ramp_m`` for a sharper corridor).

    Parameters
    ----------
    coast : CoastModel  Nominal coast (without corridor).
    lon, lat : float  [deg]  Port.
    d_min : float [m]  Nominal clearance. d_port : float [m]  Clearance at the port; reduced to the
        physical SDF at the port if that is smaller (non-negative required).
    ramp_m : float [m]  Distance from the port at which the nominal clearance is reached.
    """
    g = coast.grid
    px, py = g.to_xy(lon, lat)
    s_port = float(coast.sdf_at(px, py))
    if not s_port > 0.0:
        raise ValueError(f"port at ({lon}, {lat}) is not at sea on this grid (SDF {s_port:.0f} m)")
    d0 = min(float(d_port), s_port)
    X, Y = g.xy_mesh()
    r = np.hypot(X - px, Y - py)
    relax = (d_min - d0) * np.clip(1.0 - r / ramp_m, 0.0, 1.0)
    fi, fj = (px - g.x0) / g.dx, (py - g.y0) / g.dx
    i0, j0 = min(int(fi), g.nx - 2), min(int(fj), g.ny - 2)
    relax[j0:j0 + 2, i0:i0 + 2] = d_min - d0
    relax = relax.astype(np.float32)
    base = coast.true_sdf
    out = CoastModel(g, (base + relax).astype(np.float32), relax)
    if not float(out.sdf_at(px, py)) >= d_min - SDF_TOL_M:  # pragma: no cover - by construction
        raise ValueError("port not feasible in the relaxed field")
    return out
