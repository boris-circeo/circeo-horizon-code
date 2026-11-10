"""Tests for horizon.polar.table."""

import warnings

import numpy as np
import pytest

from horizon.polar.table import KNOT, PolarTable, default_axes, trilinear_scalar


def _random_table(seed=0, shape=(6, 7, 5)):
    rng = np.random.default_rng(seed)
    p = rng.uniform(-100, 1000, shape)
    return PolarTable(
        p,
        np.arange(shape[0]) * 2.0,
        np.arange(shape[1]) * 30.0 / 1.0 * 0.5,
        np.arange(shape[2]) * 0.5,
    )


def test_default_axes_spec_grid():
    tws, twa, u = default_axes()
    assert (tws.size, twa.size, u.size) == (51, 73, 41)
    assert tws[-1] == pytest.approx(50 * KNOT)
    assert twa[-1] == 180.0 and u[-1] == 10.0


def test_exact_at_nodes():
    t = _random_table()
    ii, jj, kk = np.meshgrid(*[np.arange(n) for n in t.p.shape], indexing="ij")
    got = t(t.tws[ii], t.twa[jj], t.u[kk])
    np.testing.assert_allclose(got, t.p, rtol=1e-6)


def test_linear_between_nodes_and_clamping():
    t = _random_table()
    # along each axis, midpoint equals the mean of the two neighbouring nodes
    m = t(t.tws[1] + 0.5 * t.d_tws, t.twa[2], t.u[3])
    assert m == pytest.approx(0.5 * (t.p[1, 2, 3] + t.p[2, 2, 3]), rel=1e-6)
    m = t(t.tws[1], t.twa[2] + 0.25 * t.d_twa, t.u[3])
    assert m == pytest.approx(0.75 * t.p[1, 2, 3] + 0.25 * t.p[1, 3, 3], rel=1e-6)
    m = t(t.tws[1], t.twa[2], t.u[3] + 0.5 * t.d_u)
    assert m == pytest.approx(0.5 * (t.p[1, 2, 3] + t.p[1, 2, 4]), rel=1e-6)
    # trilinear cell centre = mean of 8 corners
    c = t(t.tws[1] + 0.5 * t.d_tws, t.twa[2] + 0.5 * t.d_twa, t.u[3] + 0.5 * t.d_u)
    assert c == pytest.approx(t.p[1:3, 2:4, 3:5].mean(), rel=1e-6)
    # clamping
    assert t(-5.0, t.twa[0], t.u[0]) == pytest.approx(t.p[0, 0, 0], rel=1e-6)
    assert t(1e3, 1e3, 1e3) == pytest.approx(t.p[-1, -1, -1], rel=1e-6)


def test_signed_twa_symmetry_and_broadcast():
    t = _random_table()
    assert t(3.0, -40.0, 1.0) == t(3.0, 40.0, 1.0)
    out = t(np.array([[1.0], [2.0]]), np.array([10.0, 20.0, 30.0]), 1.0)
    assert out.shape == (2, 3)
    assert np.isnan(t(np.nan, 10.0, 1.0))


def test_numba_kernel_matches_call():
    t = _random_table(1)
    rng = np.random.default_rng(42)
    x = rng.uniform(-1, t.tws[-1] + 1, 500)
    y = rng.uniform(-200, 200, 500)
    z = rng.uniform(-0.5, t.u[-1] + 0.5, 500)
    vec = t(x, y, z)
    ref = np.array(
        [trilinear_scalar(t.p, *t.axis_params, a, b, c) for a, b, c in zip(x, y, z, strict=True)]
    )
    np.testing.assert_array_equal(vec, ref)
    # independent NumPy reference on in-range points
    from scipy.interpolate import RegularGridInterpolator

    rgi = RegularGridInterpolator((t.tws, t.twa, t.u), t.p.astype(float))
    xi, yi, zi = (
        np.clip(x, 0, t.tws[-1]),
        np.clip(np.abs(y), 0, t.twa[-1]),
        np.clip(z, 0, t.u[-1]),
    )
    np.testing.assert_allclose(vec, rgi(np.stack([xi, yi, zi], -1)), rtol=1e-5, atol=1e-3)


def test_reduced():
    t = _random_table(2)
    pd, ud = t.reduced()
    np.testing.assert_array_equal(pd, t.p.max(axis=2))
    assert pd.dtype == np.float32
    i, j = 3, 4
    assert ud[i, j] == t.u[np.argmax(t.p[i, j])]


def test_npz_roundtrip(tmp_path):
    t = _random_table(3)
    f = tmp_path / "p.npz"
    t.save_npz(f)
    r = PolarTable.load_npz(f)
    np.testing.assert_array_equal(r.p, t.p)
    np.testing.assert_array_equal(r.tws, t.tws)
    assert r.p.dtype == np.float32


def test_validation():
    ax = (np.arange(3.0), np.arange(3.0), np.arange(3.0))
    with pytest.raises(ValueError):
        PolarTable(np.full((3, 3, 3), 4000.0), *ax)
    with pytest.raises(ValueError):
        PolarTable(np.full((3, 3, 3), np.nan), *ax)
    with pytest.warns(UserWarning):
        PolarTable(np.full((3, 3, 3), -900.0), *ax, strict=False)
    with pytest.raises(ValueError):  # non-uniform axis
        PolarTable(np.zeros((3, 3, 3)), np.array([0, 1, 3.0]), ax[1], ax[2])
    with pytest.raises(ValueError):  # TWA beyond 180
        PolarTable(np.zeros((3, 3, 3)), ax[0], np.array([0, 100, 200.0]), ax[2])
    with pytest.raises(ValueError):  # shape mismatch
        PolarTable(np.zeros((3, 3, 2)), *ax)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        PolarTable(np.zeros((3, 3, 3)), *ax)


def _write_csv(path, tws_kn, twa, u, fn):
    rows = ["# test", "tws_kn,twa_deg,u_ms,p_kw"]
    for a in tws_kn:
        for b in twa:
            for c in u:
                rows.append(f"{a},{b},{c},{fn(a, b, c)}")
    path.write_text("\n".join(rows))


def test_csv_roundtrip_uniform(tmp_path):
    f = tmp_path / "p.csv"
    fn = lambda a, b, c: 10 * a + b + 7 * c  # noqa: E731
    _write_csv(f, [0, 5, 10], [0, 45, 90, 135, 180], [0, 2, 4], fn)
    t = PolarTable.from_long_csv(f)
    assert t.p.shape == (3, 5, 3)
    np.testing.assert_allclose(t.tws, np.array([0, 5, 10]) * KNOT)
    assert t(10 * KNOT, 135.0, 2.0) == pytest.approx(fn(10, 135, 2))


def test_csv_regrid_nonuniform(tmp_path):
    f = tmp_path / "p.csv"
    fn = lambda a, b, c: 10 * a + b + 7 * c  # noqa: E731  (linear -> regrid is exact)
    _write_csv(f, [0, 2, 10], [0, 45, 90, 180], [0, 1, 4], fn)
    t = PolarTable.from_long_csv(f)
    assert t.tws.size == 11 and t.twa.size == 73 and t.u.size == 17
    assert t(7 * KNOT, 100.0, 2.5) == pytest.approx(fn(7, 100, 2.5), rel=1e-4)


def test_csv_incomplete_grid_raises(tmp_path):
    f = tmp_path / "p.csv"
    f.write_text("tws_kn,twa_deg,u_ms,p_kw\n0,0,0,0\n1,0,0,0\n0,90,0,0\n")
    with pytest.raises(ValueError):
        PolarTable.from_long_csv(f)
