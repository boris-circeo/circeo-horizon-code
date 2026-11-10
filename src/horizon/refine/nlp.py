"""Direct multiple-shooting refinement of a DP route with CasADi + IPOPT (DES-860 §4.10, A.4).

Decision variables per stage ``i`` (duration ``dt``): the position ``X_i`` in the projected grid
frame and the **ground velocity** ``V_i = (v_east, v_north)`` [m/s] (true east/north). Dynamics
(continuity constraints)::

    X_{i+1} = X_i + J(X_i) V_i dt

with ``J`` the exact local projection Jacobian (columns = grid images of unit true east / north,
:meth:`horizon.geo.grid.Grid.local_basis`), interpolated by a cubic B-spline of ``(x, y)``: the
same relation the simulator uses cell by cell.

Power is the **mixed-heading envelope** of :mod:`horizon.polar.envelope` (the reward of the DP and
of the simulator), evaluated in the wind frame at the stage mid-point: it is concave in the
ground velocity, so zig-zag and station keeping are represented natively. The tabulated envelope
is smoothed by a tensor-product cubic B-spline over ``(TWS, v_par, v_perp)`` (``v_perp`` mirrored:
port/starboard symmetry); velocities outside the reachable hull (NaN in the table) are filled by
the nearest feasible value minus a concave penalty, and ``|V| <= u_max``. Wind, SDF, terminal
value and Jacobian are cubic B-spline interpolants on a bounding box around the warm start, so
all derivatives (including the exact Hessian) come from CasADi.

Objective (maximised, kWh)::

    sum_i P_i dt - rho_1 sum |V_{i+1} - V_i|^2 - rho_2 sum |V_{i+2} - 2 V_{i+1} + V_i|^2
      + Vbar(X_N)

(A.4 with heading/speed increments replaced by velocity-vector increments). Internally lengths
are in km and the objective in MWh for conditioning.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import casadi as ca
import numpy as np
from scipy.interpolate import make_interp_spline
from scipy.ndimage import distance_transform_edt

from horizon.dp.solver import resample_wind
from horizon.geo.coast import CoastModel
from horizon.polar.envelope import EnvelopeTable
from horizon.weather.fields import WindField

__all__ = ["RefineResult", "refine_plan", "warm_start_from_path"]

_V_TABLE_MAX = 9.0  # [m/s] half-width of the tabulated velocity window
_FILL_A, _FILL_B = 200.0, 1000.0  # [kW/(m/s)^2], [kW/(m/s)]: out-of-hull penalty
_ENV_CACHE: dict = {}
EPS_TWS2 = 0.09  # [(m/s)^2] smoothing of |W| in the wind frame


@dataclass(frozen=True)
class RefineResult:
    """Outcome of :func:`refine_plan`.

    Attributes
    ----------
    t_s : ndarray (N+1,) [s]; x, y : ndarray (N+1,) [m] grid frame (stage nodes).
    ve, vn : ndarray (N,) [m/s]  Ground velocity (true east / north) per stage.
    power_kw : ndarray (N,) [kW]  Envelope power per stage (mid-point).
    energy_kwh, terminal_kwh, penalty_kwh : float  Objective breakdown of the RETURNED plan;
        ``objective_kwh = energy + terminal - penalty``.
    warm_objective_kwh, warm_energy_kwh : float  Same for the warm start (same objective).
    status : str  IPOPT return status (or the failure reason). success : bool  IPOPT converged
        (or accepted) AND the refined plan was feasible.
    used_warm_start : bool  The returned plan is the warm start (fallback or no improvement).
    iterations : int. setup_time_s, solve_time_s : float [s]. max_violation : float
        Largest constraint violation of the returned plan (dynamics [km], speed [m/s],
        SDF [km]).
    """

    t_s: np.ndarray
    x: np.ndarray
    y: np.ndarray
    ve: np.ndarray
    vn: np.ndarray
    power_kw: np.ndarray
    energy_kwh: float
    terminal_kwh: float
    penalty_kwh: float
    warm_objective_kwh: float
    warm_energy_kwh: float
    status: str
    success: bool
    used_warm_start: bool
    iterations: int
    setup_time_s: float
    solve_time_s: float
    max_violation: float

    @property
    def objective_kwh(self) -> float:
        """Energy + terminal value - penalties [kWh]."""
        return self.energy_kwh + self.terminal_kwh - self.penalty_kwh


# ----------------------------------------------------------------------------- B-spline helpers
def _bspline(axes, data, name="f"):
    """Tensor-product cubic B-spline ``ca.Function`` through ``data`` (``dims..., m``).

    Interpolating coefficients are computed per axis with SciPy (not-a-knot), which is far faster
    than ``casadi.interpolant``'s own fit; the result is a CasADi ``Function.bspline`` (exact
    derivatives). Degree is reduced on axes with fewer than 4 nodes.
    """
    c = np.asarray(data, float)
    if c.ndim == len(axes):
        c = c[..., None]
    knots, deg = [], []
    for ax, g in enumerate(axes):
        k = min(3, len(g) - 1)
        s = make_interp_spline(np.asarray(g, float), c, k=k, axis=ax)
        c = np.moveaxis(s.c, 0, ax)
        knots.append(list(s.t))
        deg.append(k)
    m = c.shape[-1]
    flat = np.moveaxis(c, -1, 0).ravel(order="F")
    return ca.Function.bspline(name, knots, flat, deg, m)


def _fill_nan(a, step):
    """Fill NaN of the 2-D array ``a`` with nearest valid value minus a concave penalty."""
    bad = ~np.isfinite(a)
    if not bad.any():
        return a
    d, idx = distance_transform_edt(bad, return_indices=True)
    d = d * step
    near = a[idx[0], idx[1]]
    return np.where(bad, near - _FILL_A * d**2 - _FILL_B * d, a)


def _envelope_fn(env: EnvelopeTable):
    """Cached smooth B-spline of the envelope reward over ``(TWS, v_par, v_perp)`` [kW]."""
    key = id(env)
    if key in _ENV_CACHE and _ENV_CACHE[key][0] is env:
        return _ENV_CACHE[key][1]
    vp, vq = env.v_par_axis(), env.v_perp_axis()
    ip = np.flatnonzero(np.abs(vp) <= _V_TABLE_MAX + 1e-9)
    iq = np.flatnonzero(vq <= _V_TABLE_MAX + 1e-9)
    r = env.reward[:, ip][:, :, iq].astype(float)
    r = np.concatenate([r[:, :, :0:-1], r], axis=2)  # mirror v_perp
    vq_full = np.concatenate([-vq[iq][:0:-1], vq[iq]])
    tws = env.tws0 + env.dtws * np.arange(r.shape[0])
    filled = np.stack([_fill_nan(r[k], env.dv) for k in range(r.shape[0])])
    fn = _bspline([tws, vp[ip], vq_full], filled, "envelope")
    _ENV_CACHE[key] = (env, fn, float(tws[-1]))
    return fn


def _envelope_tws_max(env: EnvelopeTable) -> float:
    return env.tws0 + env.dtws * (env.reward.shape[0] - 1)


# ----------------------------------------------------------------------------- warm start
def warm_start_from_path(path, grid, dp_dt_s, t0_s, x0, y0, n_stages, dt_s):
    """Resample a DP :class:`~horizon.dp.solver.Path` to refiner stage nodes.

    Parameters
    ----------
    path : horizon.dp.Path  Path extracted from node ``k0 = 0`` (time ``t0_s``).
    grid : horizon.geo.grid.Grid
    dp_dt_s : float [s]  DP time step. t0_s : float [s]. x0, y0 : float [m]  Actual start
        (replaces the cell centre). n_stages : int. dt_s : float [s]  Refiner stage duration.

    Returns
    -------
    x, y : ndarray (n_stages+1,)  [m]  Piecewise-linear in time; holds the last point after the
        path end.
    """
    tn = t0_s + dp_dt_s * np.arange(path.i_end.size + 1)
    xn = np.concatenate([[x0], grid.x0 + grid.dx * path.i_end])
    yn = np.concatenate([[y0], grid.y0 + grid.dx * path.j_end])
    t = t0_s + dt_s * np.arange(n_stages + 1)
    return np.interp(t, tn, xn), np.interp(t, tn, yn)


# ----------------------------------------------------------------------------- main
def refine_plan(wind: WindField, x0: float, y0: float, t0_s: float, terminal, envelope:
                EnvelopeTable, coast: CoastModel, warm_start, horizon_s: float = 48 * 3600.0,
                dt_s: float = 1800.0, d_min: float = 20e3, rho=(100.0, 100.0), u_max: float = 8.0,
                margin_m: float = 120e3, max_iter: int = 200, max_cpu_s: float = 20.0,
                ipopt_options: dict | None = None) -> RefineResult:
    """Refine a route by multiple-shooting NLP (module docstring), with warm-start fallback.

    Parameters
    ----------
    wind : WindField
        Short-range forecast on the same grid as ``coast`` [m/s]; interpolated by a cubic
        B-spline in (t, y, x) on a bounding box around the warm start (clamped in time).
    x0, y0 : float [m]  Start position (grid frame). t0_s : float [s since epoch].
    terminal : ndarray (Ny, Nx) [kWh] or callable ``f(x, y) -> ndarray`` [kWh]
        Terminal value ``Vbar`` at ``t0_s + horizon_s`` (non-finite entries are filled).
    envelope : EnvelopeTable  The reward used by the DP and the simulator.
    coast : CoastModel  ``SDF(x_i) >= d_min`` is imposed at stage nodes and mid-points.
    warm_start : tuple ``(x, y)`` of arrays (N+1,) [m]  Node positions, e.g. from
        :func:`warm_start_from_path`. ``x[0], y[0]`` must equal ``(x0, y0)``.
    horizon_s, dt_s : float [s]  Horizon (``N = horizon_s / dt_s`` stages) and stage length.
    d_min : float [m]. rho : (rho_1, rho_2) [kWh/(m/s)^2]  Velocity-increment and curvature
        penalties. u_max : float [m/s]  Ground-speed bound.
    margin_m : float [m]  Bounding-box margin around the warm start (positions are confined to
        it). max_iter, max_cpu_s : IPOPT limits. ipopt_options : dict  Extra ``ipopt.*`` options.

    Returns
    -------
    RefineResult
        Never worse than the warm start in the refiner's own objective: if IPOPT fails, is
        infeasible, leaves the envelope hull, or does not improve, the warm start is returned
        (``used_warm_start=True``).
    """
    t_setup = time.perf_counter()
    n = int(round(horizon_s / dt_s))
    xw, yw = (np.asarray(a, float) for a in warm_start)
    if xw.shape != (n + 1,) or yw.shape != (n + 1,):
        raise ValueError("warm_start must be two arrays of length N+1")
    g = coast.grid
    if wind.grid != g:
        raise ValueError("wind and coast must share the same grid")
    km = 1e3
    # ---- bounding box (cell index ranges)
    i_lo = max(int(np.floor((xw.min() - margin_m - g.x0) / g.dx)), 0)
    i_hi = min(int(np.ceil((xw.max() + margin_m - g.x0) / g.dx)), g.nx - 1)
    j_lo = max(int(np.floor((yw.min() - margin_m - g.y0) / g.dx)), 0)
    j_hi = min(int(np.ceil((yw.max() + margin_m - g.y0) / g.dx)), g.ny - 1)
    i_lo, i_hi = _widen(i_lo, i_hi, g.nx)
    j_lo, j_hi = _widen(j_lo, j_hi, g.ny)
    xa = (g.x0 + g.dx * np.arange(i_lo, i_hi + 1)) / km
    ya = (g.y0 + g.dx * np.arange(j_lo, j_hi + 1)) / km
    sl = (slice(j_lo, j_hi + 1), slice(i_lo, i_hi + 1))
    # ---- wind: (t, y, x, 2)
    tt = wind.times_s
    t_end = t0_s + n * dt_s
    if tt.size >= 4:
        k0 = max(int(np.searchsorted(tt, t0_s, "right")) - 1, 0)
        k1 = min(int(np.searchsorted(tt, t_end, "left")), tt.size - 1)
        while k1 - k0 + 1 < 4:
            k0, k1 = max(k0 - 1, 0), min(k1 + 1, tt.size - 1)
        tw, uvw = tt[k0:k1 + 1], wind.uv[k0:k1 + 1][(slice(None),) + sl]
    else:
        tw = np.linspace(t0_s, t_end, 5)
        uvw = resample_wind(wind, tw)[(slice(None),) + sl]
    wind_fn = _bspline([tw, ya, xa], uvw.astype(float), "wind")
    # ---- SDF, terminal, Jacobian
    sdf = np.clip(np.nan_to_num(coast.sdf[sl].astype(float), nan=-2e5, posinf=5e5), -2e5, 5e5)
    sdf_fn = _bspline([ya, xa], sdf / km, "sdf")
    xm_, ym_ = np.meshgrid(xa * km, ya * km)
    tv = terminal(xm_, ym_) if callable(terminal) else np.asarray(terminal, float)[sl]
    tv = _fill_terminal(np.asarray(tv, float), g.dx)
    term_fn = _bspline([ya, xa], tv, "terminal")
    sj = max(1, int(np.ceil(max(len(xa), len(ya)) / 12)))
    xj, yj = xa[::sj], ya[::sj]
    if xj[-1] != xa[-1]:
        xj = np.append(xj, xa[-1])
    if yj[-1] != ya[-1]:
        yj = np.append(yj, ya[-1])
    gx, gy = np.meshgrid(xj * km, yj * km)
    lon, lat = g.to_lonlat(gx, gy)
    e_, n_ = g.local_basis(lon, lat)
    jac_fn = _bspline([yj, xj], np.concatenate([e_, n_], axis=-1), "jacobian")  # (ex,ey,nx,ny)
    env_fn = _envelope_fn(envelope)
    tws_max = _envelope_tws_max(envelope)
    # ---- symbolic problem
    X = ca.MX.sym("X", 2, n + 1)
    V = ca.MX.sym("V", 2, n)
    rho_p = ca.MX.sym("rho", 2)
    tmid = np.clip(t0_s + dt_s * (np.arange(n) + 0.5), tw[0], tw[-1])
    xm = 0.5 * (X[:, :-1] + X[:, 1:])
    w = wind_fn.map(n)(ca.vertcat(ca.DM(tmid).T, xm[1, :], xm[0, :]))
    u, v = w[0, :], w[1, :]
    tws = ca.sqrt(u**2 + v**2 + EPS_TWS2)
    vpar = -(V[0, :] * u + V[1, :] * v) / tws
    vperp = (V[0, :] * v - V[1, :] * u) / tws
    tws_c = ca.fmin(tws, tws_max)
    pw = env_fn.map(n)(ca.vertcat(tws_c, vpar, vperp))  # kW, (1, n)
    energy = ca.sum2(pw) * dt_s / 3600.0
    term = term_fn(ca.vertcat(X[1, n], X[0, n]))
    dv1 = V[:, 1:] - V[:, :-1]
    dv2 = dv1[:, 1:] - dv1[:, :-1]
    pen1 = ca.sumsqr(dv1)
    pen2 = ca.sumsqr(dv2) if n > 2 else ca.MX(0)
    pen = rho_p[0] * pen1 + rho_p[1] * pen2
    obj_fn = ca.Function("obj", [X, V, rho_p], [energy, term, pen, pw.T])
    jm = jac_fn.map(n)(ca.vertcat(X[1, :-1], X[0, :-1]))  # (4, n): ex, ey, nx, ny
    dxy = ca.vertcat(jm[0, :] * V[0, :] + jm[2, :] * V[1, :],
                     jm[1, :] * V[0, :] + jm[3, :] * V[1, :]) * (dt_s / km)
    g_dyn = ca.vec(X[:, 1:] - X[:, :-1] - dxy)
    xy_all = ca.horzcat(X[:, 1:], xm)
    g_sdf = sdf_fn.map(2 * n)(ca.vertcat(xy_all[1, :], xy_all[0, :])).T - d_min / km
    g_spd = (V[0, :]**2 + V[1, :]**2).T / u_max**2 - 1.0
    gcons = ca.vertcat(g_dyn, g_sdf, g_spd)
    f = -(energy + term - pen) / 1e3
    z = ca.vertcat(ca.vec(X), ca.vec(V))
    prob = {"x": z, "f": f, "g": gcons, "p": rho_p}

    def make_solver(extra):
        return ca.nlpsol("refine", "ipopt", prob, {
            "print_time": False, "ipopt.print_level": 0, "ipopt.sb": "yes",
            "ipopt.linear_solver": "mumps", "ipopt.max_iter": int(max_iter),
            "ipopt.max_cpu_time": float(max_cpu_s), "ipopt.tol": 1e-5,
            "ipopt.acceptable_tol": 1e-3, "ipopt.acceptable_iter": 5,
            "ipopt.mu_strategy": "monotone", "ipopt.mu_init": 1e-3,
            **extra, **(ipopt_options or {})})

    # ---- warm-start variables
    Xw = np.vstack([xw, yw]) / km
    Xw[:, 0] = (x0 / km, y0 / km)
    jw = np.asarray(jac_fn.map(n)(np.vstack([Xw[1, :-1], Xw[0, :-1]])))
    d_km = (Xw[:, 1:] - Xw[:, :-1])
    det = jw[0] * jw[3] - jw[2] * jw[1]
    Vw = np.vstack([(jw[3] * d_km[0] - jw[2] * d_km[1]) / det,
                    (-jw[1] * d_km[0] + jw[0] * d_km[1]) / det]) * km / dt_s
    z0 = np.concatenate([Xw.ravel(order="F"), Vw.ravel(order="F")])
    # ---- bounds
    lbx = np.concatenate([np.tile([xa[0], ya[0]], n + 1), np.full(2 * n, -u_max)])
    ubx = np.concatenate([np.tile([xa[-1], ya[-1]], n + 1), np.full(2 * n, u_max)])
    lbx[:2] = ubx[:2] = (x0 / km, y0 / km)
    lbg = np.concatenate([np.zeros(2 * n), np.zeros(2 * n), np.full(n, -np.inf)])
    ubg = np.concatenate([np.zeros(2 * n), np.full(2 * n, np.inf), np.zeros(n)])
    cons_fn = ca.Function("cons", [X, V], [gcons])

    def violation(Xa, Va):
        c = np.asarray(cons_fn(Xa, Va)).ravel()
        return float(max(np.abs(c[:2 * n]).max(), -c[2 * n:4 * n].min(), c[4 * n:].max() * u_max,
                         0.0))

    def evaluate(Xa, Va):
        e, t_, p_, pw_ = obj_fn(Xa, Va, list(rho))
        return float(e), float(t_), float(p_), np.asarray(pw_).ravel()

    ew, tw_, pwn, _ = evaluate(Xw, Vw)
    warm_obj = ew + tw_ - pwn
    setup = time.perf_counter() - t_setup
    # ---- solve; attempt 2 if no converged improvement: 5x smoothing, adaptive barrier.
    # A non-converged iterate (iteration/time limit) is still accepted if it is feasible, inside
    # the envelope hull and better than the warm start in the refiner's objective.
    t_solve = time.perf_counter()
    iters, converged, best = 0, False, None  # best = (obj, X, V, status)
    status = "exception"
    attempts = [(1.0, {}), (5.0, {"ipopt.mu_strategy": "adaptive", "ipopt.mu_init": 1e-1})]
    for scale, extra in attempts:
        try:
            solver = make_solver(extra)
            sol = solver(x0=z0, p=[scale * rho[0], scale * rho[1]], lbx=lbx, ubx=ubx, lbg=lbg,
                         ubg=ubg)
            st = solver.stats()
            status = str(st["return_status"])
            iters += int(st.get("iter_count", 0))
            zs = np.asarray(sol["x"]).ravel()
            Xs = zs[:2 * (n + 1)].reshape(2, n + 1, order="F")
            Vs = zs[2 * (n + 1):].reshape(2, n, order="F")
        except RuntimeError as exc:  # pragma: no cover - defensive
            status = f"exception: {exc}"
            continue
        if not (np.all(np.isfinite(Xs)) and np.all(np.isfinite(Vs))):
            continue
        es, ts, ps, _ = evaluate(Xs, Vs)
        obj = es + ts - ps
        if (violation(Xs, Vs) <= 1e-3 and obj >= warm_obj - 1e-9
                and _in_hull(envelope, wind_fn, tw, tmid, Xs, Vs, n)
                and (best is None or obj > best[0])):
            best = (obj, Xs, Vs, status)
            converged = bool(st["success"]) or status == "Solved_To_Acceptable_Level"
            if converged:
                break
    solve = time.perf_counter() - t_solve
    use_warm = best is None
    if best is not None:
        _, Xs, Vs, status = best
    else:
        Xs, Vs = Xw, Vw
    es, ts, ps, pw_k = evaluate(Xs, Vs)
    return RefineResult(
        t0_s + dt_s * np.arange(n + 1), Xs[0] * km, Xs[1] * km, Vs[0], Vs[1], pw_k, es, ts, ps,
        warm_obj, ew, status, converged and not use_warm, use_warm, iters, setup, solve,
        violation(Xs, Vs))


def _widen(lo, hi, n, minw=5):
    """Widen the inclusive index range ``[lo, hi]`` to at least ``minw`` nodes within ``[0, n)``."""
    while hi - lo + 1 < min(minw, n):
        lo, hi = max(lo - 1, 0), min(hi + 1, n - 1)
    return lo, hi


def _fill_terminal(tv, dx):
    """Replace non-finite terminal values by the nearest finite one minus a distance penalty."""
    bad = ~np.isfinite(tv)
    if not bad.any():
        return tv
    if bad.all():
        return np.zeros_like(tv)
    span = float(np.ptp(tv[~bad])) + 1.0
    d, idx = distance_transform_edt(bad, return_indices=True)
    return np.where(bad, tv[idx[0], idx[1]] - 0.1 * span * d, tv)


def _in_hull(env, wind_fn, tw, tmid, Xs, Vs, n):
    """True if every stage velocity lies in the reachable hull of the TABULATED envelope."""
    from horizon.polar.envelope import envelope_lookup
    xm = 0.5 * (Xs[:, :-1] + Xs[:, 1:])
    w = np.asarray(wind_fn.map(n)(np.vstack([tmid, xm[1], xm[0]])))
    tws = np.sqrt(w[0] ** 2 + w[1] ** 2 + EPS_TWS2)
    vpar = -(Vs[0] * w[0] + Vs[1] * w[1]) / tws
    vperp = (Vs[0] * w[1] - Vs[1] * w[0]) / tws
    ax = env.axes
    out = [envelope_lookup(env.reward, ax, float(a), float(b), float(c))
           for a, b, c in zip(tws, vpar, vperp, strict=True)]
    return bool(np.all(np.isfinite(out)))
