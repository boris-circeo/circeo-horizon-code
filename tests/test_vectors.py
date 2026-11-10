import numpy as np
import pytest

from horizon.geo.grid import Grid
from horizon.geo.vectors import en_to_grid, grid_to_en

GRID = Grid.from_bbox(-30.0, 0.0, 35.0, 55.0, 50_000.0)
RNG = np.random.default_rng(3)


def test_at_projection_centre_is_identity():
    lon0, lat0 = GRID.to_lonlat(0.0, 0.0)
    # LAEA centre is the box centre: (-15, 45)
    gx, gy = en_to_grid(GRID, 1.0, 0.0, -15.0, 45.0)
    assert (gx, gy) == pytest.approx((1.0, 0.0), abs=1e-4)
    gx, gy = en_to_grid(GRID, 0.0, 1.0, -15.0, 45.0)
    assert (gx, gy) == pytest.approx((0.0, 1.0), abs=1e-4)


def test_roundtrip_random():
    n = 200
    lon = RNG.uniform(-30, 0, n)
    lat = RNG.uniform(35, 55, n)
    ve, vn = RNG.normal(0, 5, (2, n))
    gx, gy = en_to_grid(GRID, ve, vn, lon, lat)
    ve2, vn2 = grid_to_en(GRID, gx, gy, lon, lat)
    assert np.allclose(ve, ve2, atol=1e-8) and np.allclose(vn, vn2, atol=1e-8)


def test_true_north_tilts_off_centre_and_matches_basis():
    # away from the central meridian, true north is rotated in grid frame
    gx, gy = en_to_grid(GRID, 0.0, 1.0, -30.0, 45.0)
    assert abs(gx) > 0.05 and gy > 0
    e, n = GRID.local_basis(-30.0, 45.0)
    assert (gx, gy) == pytest.approx(tuple(n))


def test_scale_factor_not_unity_off_centre():
    gx, gy = en_to_grid(GRID, 1.0, 0.0, -30.0, 55.0)
    assert np.hypot(gx, gy) != pytest.approx(1.0, abs=1e-4)


def test_broadcast_scalar_lonlat_with_array_vectors():
    ve = np.array([1.0, 2.0, 3.0])
    gx, gy = en_to_grid(GRID, ve, 0.0 * ve, -10.0, 40.0)
    assert gx.shape == (3,)
