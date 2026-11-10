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
    "bilinear_sdf",
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

    def sdf_at_lonlat(self, lon, lat) -> np.ndarray:
        """Bilinear SDF [m] at geographic points [deg]."""
        x, y = self.grid.to_xy(lon, lat)
        return self.sdf_at(x, y)

    def is_navigable(self, x, y, d_min: float) -> np.ndarray:
        """True where ``SDF >= d_min`` [m] (DES-860 A.1); False outside the grid."""
        return self.sdf_at(x, y) >= d_min

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
