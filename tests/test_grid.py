"""Tests for horizon.geo.grid."""

import numpy as np
import pytest

from horizon.geo.grid import Grid


@pytest.fixture(scope="module")
def basin():
    # North-Atlantic PoC basin (DES-860 §7.5.6: 45W-5E)
    return Grid.from_bbox(-45.0, 5.0, 35.0, 65.0, 10_000.0)


def test_extent_covers_bbox(basin):
    for lon, lat in [(-45, 35), (-45, 65), (5, 35), (5, 65), (-20, 50)]:
        x, y = basin.to_xy(lon, lat)
        assert basin.contains(x, y)


def test_roundtrip(basin):
    lon, lat = basin.to_lonlat(*basin.to_xy(-3.4, 47.7))
    assert lon == pytest.approx(-3.4, abs=1e-9)
    assert lat == pytest.approx(47.7, abs=1e-9)


@pytest.mark.parametrize("lon,lat", [(-40.0, 60.0), (-5.0, 50.0), (0.0, 40.0)])
@pytest.mark.parametrize("psi", [0.0, 45.0, 90.0, 200.0])
def test_heading_conversion_matches_finite_difference(basin, lon, lat, psi):
    """A small displacement along true heading psi must have grid bearing true_to_grid(psi)."""
    from pyproj import Geod

    lon1, lat1, _ = Geod(ellps="WGS84").fwd(lon, lat, psi, 100.0)
    x0, y0 = basin.to_xy(lon, lat)
    x1, y1 = basin.to_xy(lon1, lat1)
    bearing = np.degrees(np.arctan2(x1 - x0, y1 - y0)) % 360.0
    expected = float(basin.true_to_grid_heading(psi, lon, lat))
    diff = (bearing - expected + 180.0) % 360.0 - 180.0
    assert abs(diff) < 0.05
    back = float(basin.grid_to_true_heading(expected, lon, lat))
    assert (back - psi + 180) % 360 - 180 == pytest.approx(0.0, abs=1e-9)


def test_index_of_and_coarsen(basin):
    j, i = basin.index_of(basin.x[7], basin.y[11])
    assert (int(j), int(i)) == (11, 7)
    c = basin.coarsen(4)
    assert c.dx == 40_000.0
    assert c.nx * 4 >= basin.nx and c.ny * 4 >= basin.ny
