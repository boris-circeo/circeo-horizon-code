"""Value-function work (E0 / V_theta): features, leakage guard, data assembly, model I/O, terminal
field on the grid, shared-DP rollouts. Synthetic data only (no ERA5)."""

import numpy as np
import pytest

from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import DirectPowerModel, EnvelopePowerModel
from horizon.value import (
    FC_NAMES,
    FEATURE_NAMES,
    TerminalFnMPCPolicy,
    ValueModel,
    ValueTerminal,
    feature_matrix,
    fit_value_model,
    forecast_feature_fields,
    leave_month_out_mask,
    month_of,
)
from horizon.value.collect import hindsight_maps, rollout_group, track_samples
from horizon.value.dataset import assemble, build_X, sample_map
from horizon.weather.fields import Ensemble, WindField

EPOCH = np.datetime64("2015-01-01T00:00:00", "s")
DAY = 86400.0


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold(polar):
    return hold_power_curve(polar)


@pytest.fixture(scope="module")
def grid():
    return Grid.from_bbox(-12, 4, 38, 54, 80e3)


@pytest.fixture(scope="module")
def sea(grid):
    return CoastModel(grid, np.full(grid.shape, 1e6, np.float32))


@pytest.fixture(scope="module")
def pm(polar, hold):
    return EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))


class Wx:
    """Uniform stationary wind, perfect forecast; counts forecast calls."""

    def __init__(self, grid, u=9.0, v=3.0, duration_s=20 * DAY):
        self.grid, self.epoch, self.duration_s = grid, EPOCH, duration_s
        self.uv = np.array([u, v], np.float32)
        self.n_fc = 0

    def _f(self, t):
        uv = np.broadcast_to(self.uv, (len(t),) + self.grid.shape + (2,)).copy()
        return WindField(self.grid, EPOCH, np.asarray(t, float), uv)

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        self.n_fc += 1
        t = issue_s + dt_s * np.arange(int(round(horizon_s / dt_s)) + 1)
        return Ensemble(self.grid, EPOCH, issue_s, t, self._f(t).uv[None], np.ones(1))

    def truth(self, dt_s=3600.0, start_s=0.0, end_s=None):
        end_s = self.duration_s if end_s is None else end_s
        return self._f(np.arange(start_s, end_s + 1, dt_s))


# ------------------------------------------------------------------------------ leakage guard
def test_leave_month_out_mask_excludes_target_month_and_buffer():
    tau = np.arange(0, 365) * DAY
    for m in (1, 6, 12):
        keep = leave_month_out_mask(tau, EPOCH, m, buffer_days=5.0)
        mon = month_of(tau, EPOCH)
        assert not keep[mon == m].any()
        first, last = np.flatnonzero(mon == m)[[0, -1]]
        lo, hi = max(first - 5, 0), min(last + 5, 364)
        assert not keep[lo:hi + 1].any()  # buffer on both sides
        assert keep[:max(first - 5, 0)].all() and keep[min(last + 6, 365):].all()


def test_month_of():
    assert list(month_of(np.array([0.0, 31 * DAY, 59 * DAY, 364 * DAY]), EPOCH)) == [1, 2, 3, 12]


# ------------------------------------------------------------------------------------ features
def _hold_curve(hold):
    tws = np.asarray(hold.tws, float)
    return tws, np.asarray(hold.p_hold, float)


def test_forecast_feature_fields_constant_wind(grid, hold):
    tws_ax, p_ax = _hold_curve(hold)
    t = np.arange(0, 10 * DAY + 1, 6 * 3600.0)
    uv = np.zeros((t.size,) + grid.shape + (2,), np.float32)
    uv[..., 0] = 8.0
    f = forecast_feature_fields(t, uv, 5 * DAY, 10 * DAY, tws_ax, p_ax)
    assert f.shape == (len(FC_NAMES),) + grid.shape and f.dtype == np.float32
    p8 = np.interp(8.0, tws_ax, p_ax)
    assert np.allclose(f[0], p8, rtol=1e-5) and np.allclose(f[3], 8.0, rtol=1e-5)
    assert np.allclose(f[4], 0.0, atol=1e-5)  # temporal std


def test_feature_matrix_shape_and_values(grid):
    ny, nx = grid.shape
    clim = np.full(grid.shape, 700.0, np.float32)
    sdf = np.full(grid.shape, 5e4, np.float32)
    fc = np.random.default_rng(0).random((len(FC_NAMES), ny, nx)).astype(np.float32)
    x = np.array([grid.x0 + 3.5 * grid.dx, grid.x0 + 10 * grid.dx])
    y = np.array([grid.y0 + 4 * grid.dx, grid.y0 + 7.2 * grid.dx])
    X = feature_matrix(grid, x, y, 90 * DAY, EPOCH, clim, sdf, fc)
    assert X.shape == (2, len(FEATURE_NAMES)) and np.isfinite(X).all()
    i = FEATURE_NAMES.index
    assert np.allclose(X[:, i("clim_kw")], 700.0) and np.allclose(X[:, i("sdf_km")], 50.0)
    assert np.allclose(X[:, i("sin_doy")] ** 2 + X[:, i("cos_doy")] ** 2, 1.0, atol=1e-6)
    # bilinear: fc_hold at (3.5, 4) = mean of the 2 neighbours along x
    assert X[0, i("fc_hold")] == pytest.approx(0.5 * (fc[0, 4, 3] + fc[0, 4, 4]), rel=1e-5)


# ---------------------------------------------------------------------------------- model I/O
def test_model_save_load_roundtrip(tmp_path):
    rng = np.random.default_rng(1)
    X = rng.random((300, len(FEATURE_NAMES))).astype(np.float32)
    y = 1e5 * X[:, 4] + 2e4 * X[:, 6] + rng.normal(0, 1e3, 300)
    m = fit_value_model(X, y, params={"n_estimators": 40}, meta={"holdout": 3})
    m.save(tmp_path / "m.joblib")
    m2 = ValueModel.load(tmp_path / "m.joblib")
    assert np.array_equal(m.predict(X), m2.predict(X))
    assert m2.meta["holdout"] == 3 and m2.meta["n_train"] == 300 and m2.horizon_s == 5 * DAY
    assert np.corrcoef(m.predict(X), y)[0, 1] > 0.95


def test_quantile_model_orders():
    rng = np.random.default_rng(2)
    X = rng.random((400, len(FEATURE_NAMES))).astype(np.float32)
    y = 1e4 * X[:, 0] + rng.normal(0, 2e3, 400)
    lo = fit_value_model(X, y, quantile=0.1, params={"n_estimators": 60}).predict(X)
    hi = fit_value_model(X, y, quantile=0.9, params={"n_estimators": 60}).predict(X)
    assert (hi > lo).mean() > 0.9


# ------------------------------------------------------------------ terminal field on the grid
def _fit_dummy(grid, level):
    rng = np.random.default_rng(3)
    X = rng.random((200, len(FEATURE_NAMES))).astype(np.float32)
    return fit_value_model(X, np.full(200, level) + 1e3 * X[:, 4], params={"n_estimators": 20})


def test_terminal_field_on_grid(grid, hold):
    tws_ax, p_ax = _hold_curve(hold)
    vt = ValueTerminal(_fit_dummy(grid, 1.5e5), grid, np.full(grid.shape, 0.5, np.float32),
                       np.full(grid.shape, 5e4, np.float32), EPOCH, tws_ax, p_ax)
    t = np.arange(0, 10 * DAY + 1, 6 * 3600.0)
    uv = np.full((t.size,) + grid.shape + (2,), 7.0, np.float32)
    f = vt.field(5 * DAY, t, uv)
    assert f.shape == grid.shape and f.dtype == np.float32 and np.isfinite(f).all()
    assert 1.4e5 < f.mean() < 1.7e5
    assert (f >= 0).all()


def test_terminal_call_scales_to_mission_end(grid, hold):
    from horizon.sim.simulator import ForecastProvider
    tws_ax, p_ax = _hold_curve(hold)
    wx = Wx(grid)
    vt = ValueTerminal(_fit_dummy(grid, 1.5e5), grid, np.full(grid.shape, 0.5, np.float32),
                       np.full(grid.shape, 5e4, np.float32), EPOCH, tws_ax, p_ax)
    tau = 5 * DAY
    full = vt(0.0, tau, ForecastProvider(wx, 0.0, 20 * DAY))
    half = vt(0.0, tau, ForecastProvider(wx, 0.0, tau + 2.5 * DAY))
    none = vt(0.0, tau, ForecastProvider(wx, 0.0, tau))
    assert np.allclose(half, 0.5 * full, rtol=1e-4) and not none.any()


# ------------------------------------------------------------- policy / rollouts / hindsight
def test_policy_with_terminal_fn_and_dp_cache(grid, sea, polar, hold, pm):
    from horizon.sim.simulator import ForecastProvider
    wx = Wx(grid)
    calls = []

    def tf(t, tau, prov):
        calls.append((t, tau))
        return np.full(grid.shape, 1e4, np.float32)

    cache = {}
    pol = TerminalFnMPCPolicy(polar, hold, sea, horizon_days=1.0, terminal_fn=tf, dp_cache=cache)
    x, y = grid.to_xy(-4.0, 46.0)
    p1 = pol.plan(0.0, x, y, ForecastProvider(wx, 0.0, 10 * DAY))
    n_fc = wx.n_fc
    p2 = pol.plan(0.0, x + 8e4, y, ForecastProvider(wx, 0.0, 10 * DAY))
    assert wx.n_fc == n_fc and len(calls) == 1 and len(cache) == 1  # DP shared across ships
    assert p1.x.size == p2.x.size == 8
    # a constant terminal value must not change the route vs. zero terminal
    ref = TerminalFnMPCPolicy(polar, hold, sea, horizon_days=1.0)
    p0 = ref.plan(0.0, x, y, ForecastProvider(wx, 0.0, 10 * DAY))
    assert np.allclose(p0.x, p1.x) and np.allclose(p0.y, p1.y)


def test_hindsight_and_rollouts(grid, sea, polar, hold, pm):
    wx = Wx(grid, 10.0, 0.0)
    tr = wx.truth(dt_s=10800.0, start_s=0.0, end_s=4 * DAY)
    h = hindsight_maps(tr, 0.0, (1, 2), polar, hold, sea)
    assert h.shape == (2,) + grid.shape and np.nanmin(h) > 0 and (h[1] > h[0]).all()
    cells = np.array([[10, 12], [15, 5], [20, 17]])
    ro = rollout_group(wx, wx.truth(dt_s=3600.0, start_s=0.0, end_s=2 * DAY + 3600.0), pm, sea,
                       polar, hold, 0.0, cells, h_days=2, end_s=wx.duration_s)
    assert ro["E"].shape == (3, 2) and (np.diff(ro["E"], axis=1) > 0).all()
    # causal policy never beats the clairvoyant DP in uniform stationary wind (up to grid error)
    vh = h[1][cells[:, 0], cells[:, 1]]
    assert (ro["E"][:, 1] <= vh * 1.02).all()
    assert wx.n_fc < 3 * 8  # shared DP: forecasts requested once per replan, not per ship


def test_track_samples_windows():
    n = 600
    cum = np.arange(n + 1, dtype=float)
    x = np.arange(n + 1, dtype=float)
    keep, xs, ys, E = track_samples(x, x, cum, np.array([0.0, 900.0 * 100, 900.0 * 590]), (2,),
                                    sim_dt_s=900.0)
    assert list(keep) == [True, True, False]  # window must fit inside the track
    assert E.shape == (2, 1) and np.allclose(E[:, 0], 2 * 96) and list(xs) == [0.0, 100.0]


def test_sample_map_nan_fallback(grid):
    f = np.ones(grid.shape)
    f[3, 3] = np.nan
    v = sample_map(grid, f, np.array([grid.x0 + 3.4 * grid.dx, grid.x0 + 8 * grid.dx]),
                   np.array([grid.y0 + 3.4 * grid.dx, grid.y0 + 8 * grid.dx]))
    assert np.isfinite(v).all()


def test_assemble_shapes_and_leakage(tmp_path, grid):
    rng = np.random.default_rng(0)
    ny, nx = grid.shape
    n_k, n_sh = 8, 5
    for k in range(n_k):
        cells = np.stack([rng.integers(2, ny - 2, n_sh), rng.integers(2, nx - 2, n_sh)], 1)
        np.savez(tmp_path / f"k_{k:03d}.npz", hind=rng.random((3, ny, nx)).astype(np.float32) + 1,
                 fc=(rng.random((6, ny, nx)) if k >= 2 else np.full((6, ny, nx), np.nan)
                     ).astype(np.float32), cells=cells, s_k=k * 30.0 * DAY,
                 x0=grid.x0 + cells[:, 1] * grid.dx, y0=grid.y0 + cells[:, 0] * grid.dx,
                 E=np.cumsum(rng.random((n_sh, 5)) * 1e4, 1))
    run = tmp_path / "run"
    run.mkdir()
    ns = 365 * 96
    for q in range(2):
        np.savez(run / f"seg_{q:04d}.npz", x=np.full(ns // 2, grid.x0 + 5 * grid.dx),
                 y=np.full(ns // 2, grid.y0 + 5 * grid.dx), power_kw=np.full(ns // 2, 1000.0))
        (run / f"seg_{q:04d}.json").write_text("{}")
    ds = assemble(tmp_path, grid, [run], extra_cells_per_k=3)
    n_roll = n_k * n_sh
    assert (ds.src == 0).sum() == n_roll and (ds.src == -1).sum() == 3 * n_k
    assert (ds.src == 1).sum() == n_k
    assert ds.E.shape == (len(ds), 3) and ds.V.shape == (len(ds), 3)
    roll = ds.src == 0
    assert np.isfinite(ds.E[roll][:, :2]).all() and np.isnan(ds.E[roll][:, 2]).all()
    tr = ds.src == 1
    assert np.allclose(ds.E[tr][:, 1], 1000.0 * 5 * 24)  # 5 d at constant 1000 kW
    X = build_X(ds, grid, np.full(grid.shape, 1.0, np.float32), np.full(grid.shape, 5e4))
    assert X.shape == (len(ds), len(FEATURE_NAMES))
    assert np.isnan(X[ds.k < 2]).all() and np.isfinite(X[ds.k >= 2]).all()
    for m in range(1, 9):  # leakage guard at the data-set level
        ok = leave_month_out_mask(ds.tau, ds.epoch, m, 5.0)
        assert not (ds.month[ok] == m).any()
