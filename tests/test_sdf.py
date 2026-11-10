"""Tests for horizon.geo.coast (land mask, SDF, CoastModel)."""

import numpy as np
import pytest

from horizon.geo.coast import (
    CoastModel,
    bilinear_sdf,
    build_basin_coast,
    scale_factors,
    signed_distance,
)
from horizon.geo.grid import Grid


@pytest.fixture(scope="module")
def basin():
    try:
        return build_basin_coast()
    except FileNotFoundError:
        pytest.skip("no committed asset and no Natural Earth data")


def _at(model, lat, lon):
    return float(model.sdf_at_lonlat(lon, lat))


def test_known_points(basin):
    assert abs(_at(basin, 47.7, -3.4)) < 20_000  # Lorient approach
    assert _at(basin, 50.0, -25.0) > 500_000  # mid-Atlantic
    assert _at(basin, 48.85, 2.35) < 0  # Paris
    assert _at(basin, 53.2, -8.0) < 0  # Ireland interior
    assert _at(basin, 47.5, -4.5) > 0  # sea off south Brittany


def test_sign_matches_mask_and_cell_values(basin):
    assert np.array_equal(basin.land_mask, basin.sdf < 0)
    assert 0.1 < basin.land_mask.mean() < 0.3
    assert np.abs(basin.sdf).min() >= 0.5 * basin.grid.dx - 1e-3


def test_projection_scale_error_bounded(basin):
    h, k = scale_factors(basin.grid)
    assert max(abs(h - 1).max(), abs(k - 1).max()) < 0.035


def test_circular_island_exact():
    dx = 1_000.0
    grid = Grid.from_bbox(-1, 1, -1, 1, dx, lat0=0.0, lon0=0.0)
    X, Y = grid.xy_mesh()
    cx, cy, r = grid.x[grid.nx // 2], grid.y[grid.ny // 2], 30_000.0
    rho = np.hypot(X - cx, Y - cy)
    sdf = signed_distance(grid, rho <= r)
    assert sdf.dtype == np.float32
    assert np.abs(sdf - (rho - r)).max() <= dx  # within one cell
    assert np.abs(sdf[rho > 3 * r] - (rho - r)[rho > 3 * r]).max() <= dx


def test_degenerate_masks():
    grid = Grid.from_bbox(-1, 1, -1, 1, 10_000.0, lat0=0.0, lon0=0.0)
    assert (signed_distance(grid, np.zeros(grid.shape, bool)) > 0).all()
    assert (signed_distance(grid, np.ones(grid.shape, bool)) < 0).all()


def test_bilinear_matches_array_at_centres(basin):
    g = basin.grid
    rng = np.random.default_rng(0)
    j = rng.integers(0, g.ny, 500)
    i = rng.integers(0, g.nx, 500)
    got = basin.sdf_at(g.x[i], g.y[j])
    assert np.allclose(got, basin.sdf[j, i], atol=1e-2)
    # mid-point of four cells = mean of the four values
    j0, i0 = 100, 200
    xm, ym = g.x[i0] + 0.5 * g.dx, g.y[j0] + 0.5 * g.dx
    expect = basin.sdf[j0 : j0 + 2, i0 : i0 + 2].mean()
    assert np.isclose(basin.sdf_at(xm, ym), expect, atol=1e-2)
    assert np.isnan(basin.sdf_at(g.x[0] - g.dx, g.y[0]))


def test_numba_helper_matches_numpy():
    rng = np.random.default_rng(1)
    f = rng.normal(size=(20, 30)).astype(np.float32)
    x0, y0, dx = 5.0, -7.0, 3.0
    for _ in range(50):
        x = x0 + rng.uniform(0, 29 * dx)
        y = y0 + rng.uniform(0, 19 * dx)
        fi, fj = (x - x0) / dx, (y - y0) / dx
        i, j = min(int(fi), 28), min(int(fj), 18)
        a, b = fi - i, fj - j
        ref = (
            (1 - a) * (1 - b) * f[j, i]
            + a * (1 - b) * f[j, i + 1]
            + (1 - a) * b * f[j + 1, i]
            + a * b * f[j + 1, i + 1]
        )
        assert bilinear_sdf(f, x0, y0, dx, x, y) == pytest.approx(ref, abs=1e-6)
    assert np.isnan(bilinear_sdf(f, x0, y0, dx, x0 - 1, y0))


def test_is_navigable_and_npz_roundtrip(basin, tmp_path):
    x, y = basin.grid.to_xy(np.array([-25.0, 2.35, -3.4]), np.array([50.0, 48.85, 47.7]))
    assert list(basin.is_navigable(x, y, 10_000.0)) == [True, False, False]
    p = tmp_path / "c.npz"
    basin.save_npz(p)
    b2 = CoastModel.load_npz(p)
    assert b2.grid == basin.grid and np.array_equal(b2.sdf, basin.sdf)
