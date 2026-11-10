"""Tests of horizon.weather.era5 (regridding, conventions, month boundaries, fill)."""

from pathlib import Path

import numpy as np
import pytest

from horizon.geo.grid import Grid
from horizon.weather.era5 import ERA5_BOX, ERA5Archive, regrid_indices, regrid_uv

GRIB_DIR = Path("/home/claude/circeo-horizon-data/era5-data")
needs_data = pytest.mark.skipif(not (GRIB_DIR / "wind_2015_01.grib").exists(),
                                reason="client ERA5 files not available")


def test_regrid_exact_on_linear_field():
    """Bilinear interpolation reproduces a field linear in (lon, lat), per component."""
    grid = Grid.from_bbox(-20.0, 0.0, 40.0, 55.0, 40e3)
    lon_s = np.arange(-32.0, 5.0001, 0.25)
    lat_s = np.arange(65.0, 37.9999, -0.25)
    LO, LA = np.meshgrid(lon_s, lat_s)
    u = (0.3 * LO - 0.2 * LA + 5.0)[None]
    v = (-0.1 * LO + 0.4 * LA - 3.0)[None]
    st = regrid_indices(grid, lon_s, lat_s)
    out = regrid_uv(u, v, st)
    lon, lat = grid.lonlat_mesh()
    ok = ~st[4]
    assert ok.mean() > 0.5
    assert out.dtype == np.float32 and out.shape == (1, grid.ny, grid.nx, 2)
    np.testing.assert_allclose(out[0, ..., 0][ok], (0.3 * lon - 0.2 * lat + 5.0)[ok], atol=2e-4)
    np.testing.assert_allclose(out[0, ..., 1][ok], (-0.1 * lon + 0.4 * lat - 3.0)[ok], atol=2e-4)


@pytest.fixture(scope="module")
def archive():
    grid = Grid.from_bbox(*ERA5_BOX, 40e3)
    if not (GRIB_DIR / "wind_2015_01.grib").exists():
        pytest.skip("client ERA5 files not available")
    a = ERA5Archive(GRIB_DIR, grid)
    a.build_cache(months=[1, 2, 12])
    return a


@needs_data
def test_matches_raw_grib_at_a_point(archive):
    """Cache value at a sea cell equals a direct bilinear lookup in the raw GRIB (orientation)."""
    import xarray as xr
    from scipy.interpolate import RegularGridInterpolator

    ds = xr.open_dataset(GRIB_DIR / "wind_2015_02.grib", engine="cfgrib",
                         backend_kwargs={"indexpath": ""})
    k = 24 * 9 + 13
    lat = ds["latitude"].values[::-1]
    lon = ds["longitude"].values
    fu = RegularGridInterpolator((lat, lon), ds["u10"].values[k][::-1], method="linear")
    fv = RegularGridInterpolator((lat, lon), ds["v10"].values[k][::-1], method="linear")
    glon, glat = archive.grid.lonlat_mesh()
    for j, i in [(40, 40), (30, 55), (55, 20)]:
        assert not archive.outside[j, i]
        h = int(archive._offset[1]) + k
        got = archive.hours(h, h + 1)[0, j, i]
        ref = (fu((glat[j, i], glon[j, i])), fv((glat[j, i], glon[j, i])))
        np.testing.assert_allclose(got, ref, atol=2e-3)


@needs_data
def test_westerly_convention(archive):
    """Mean winter flow at 45-55N over the Atlantic is westerly: u > 0 is wind toward the East."""
    lon, lat = archive.grid.lonlat_mesh()
    band = (lat > 45) & (lat < 55) & (lon < -5) & ~archive.outside
    full = archive.hours(0, 744)
    jan = full[:, band]
    assert jan[..., 0].mean() > 3.0
    assert abs(jan[..., 1].mean()) < jan[..., 0].mean()
    # trades are easterly in the south-west of the basin (u < 0), also a convention check
    sw = (lat > 38) & (lat < 42) & (lon < -20) & ~archive.outside
    assert full[:, sw, 0].mean() < jan[..., 0].mean()


@needs_data
def test_month_boundary_continuity(archive):
    """The field is continuous across 31 Jan -> 1 Feb: no jump larger than usual hourly changes."""
    f = archive.truth("2015-01-31T12:00", "2015-02-01T12:00", 3600.0)
    assert f.uv.shape[0] == 25 and f.uv.dtype == np.float32
    step = np.abs(np.diff(f.uv, axis=0)).mean(axis=(1, 2, 3))
    assert step[11] < 2.0 * np.median(step) + 0.2
    # same values as the two monthly caches
    h = int(archive._offset[1])
    np.testing.assert_array_equal(f.uv[12], archive.hours(h, h + 1)[0])
    np.testing.assert_array_equal(f.uv[11], archive.hours(h - 1, h)[0])
    assert f.epoch == np.datetime64("2015-01-31T12:00:00")


@needs_data
def test_time_interpolation_and_dtype(archive):
    f = archive.truth("2015-02-03T00:00", "2015-02-03T06:00", 1800.0)
    assert f.uv.shape[0] == 13
    np.testing.assert_allclose(f.uv[1], 0.5 * (f.uv[0] + f.uv[2]), atol=1e-5)


@needs_data
def test_out_of_span_error_and_wrap(archive):
    with pytest.raises(ValueError):
        archive.truth("2015-12-31T00:00", "2016-01-02T00:00", 3600.0)
    with pytest.warns(UserWarning):
        f = archive.truth("2015-12-31T00:00", "2016-01-02T00:00", 3600.0, fill="wrap")
    assert np.isfinite(f.uv).all()
