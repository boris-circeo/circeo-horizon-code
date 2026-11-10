"""Versioned JSON export of backtest results for the router inspector (``schema_version`` 1).

The exporter turns closed-loop mission results (:class:`horizon.sim.simulator.MissionResult`)
plus the TRUTH wind into one JSON-serialisable ``dict`` that the static inspector page
(:mod:`horizon.viz.inspector`) embeds and renders. Everything the browser needs is precomputed
here (experienced TWS/TWA, productive-band shares, histograms) or is cheap to derive from the
exported series (regret, gap to the reference, daily losses).

Schema (version 1)
------------------
``dict`` with the keys

``schema_version`` : int
``title``, ``generated`` : str  Free text and ISO-8601 UTC timestamp.
``meta`` : dict
    ``epoch`` (ISO), ``duration_s``, ``sim_dt_s``, ``export_dt_s``, ``p_rated_kw``,
    ``reference`` (policy name used for regret / gap), ``hold_speed_ms``,
    ``productive`` (``{"tws_kn": [18, 26], "twa_deg": [75, 105]}``), ``params`` (free dict).
``policies`` : list of dict
    ``name`` plus optional ``label``, ``description``, ``params`` (display order).
``map`` : dict
    ``grid`` (``nx, ny, dx_km, x0_km, y0_km``; cell centres, grid frame), ``sdf``
    (encoded int16 array ``(ny, nx)`` in units of ``unit_km``; negative = land), ``graticule``
    (list of ``{label, x_km, y_km}``), ``markers`` (list of ``{name, x_km, y_km, lon, lat}``),
    ``start`` (same shape or ``None``).
``seeds`` : list of dict, one per seed
    ``seed``; ``t_s`` (hourly sample times, ``n+1``); ``weather`` (basin diagnostics);
    ``wind`` (decimated truth snapshots, see below); ``storms`` (per snapshot list of
    ``[x_km, y_km]``); ``forecast_error`` (optional); ``runs`` mapping policy name to a run.

Run (all series are sampled every ``export_dt_s``)::

    lon, lat, x_km, y_km          (n+1)   positions at the sample times
    energy_kwh                    (n+1)   cumulative energy
    power_kw, hold_frac, tws_ms, twa_deg   (n)  block means over [t_k, t_k+1]; ``null`` = undefined
    replans                       list of {t_s, planned_value_kwh, plan?, diag?}
    metrics                       energy_kwh, capacity_factor, mean_power_kw, distance_km,
                                  hold_fraction, coast_violations, n_replans
    diag                          productive_share (TWS band and TWA band, hold counts as in the
                                  TWA band), tws_band_share, twa_band_share, hold_share,
                                  mean_speed_ms, mean_tws_ms, tws_hist, twa_hist

``plan`` is ``{t0_s, dt_s, x_km, y_km}`` and only present when it differs from the previous
replan's plan; ``diag`` is the policy's ``last_diagnostics`` (made JSON-safe) after that replan.

``wind`` holds ``nt, ny, nx, x0_km, y0_km, dx_km, dt_s, scale_ms`` and encoded arrays ``u``,
``v`` (int8, ``(nt, ny, nx)``, physical value = ``q * scale_ms``, true east / north "toward"
components) and ``theta`` (float32 ``(ny, nx)``, grid-frame angle [rad] of true east).

Optional additions (still ``schema_version`` 1, all backward compatible):

``polar`` : dict  ``tws_kn, twa_deg, u_ms`` axes, ``p`` (int16 ``(nTWS, nTWA, nU)``, kW =
    ``q * scale_kw``, ``-32768`` = infeasible) and ``meta``.
``meta.weather_kind`` : ``"synthetic"`` | ``"era5"``;  ``map.era5_mask`` : uint8 ``(ny, nx)``.
Per seed ``epoch`` (ISO UTC) and ``label``; per run ``speed_ms`` (block-mean ground speed).

Encoded arrays are ``{"dtype", "shape", "b64"}`` (little-endian raw bytes, base64).
"""

from __future__ import annotations

import base64
import gzip
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from horizon.core.units import KNOT
from horizon.geo.coast import CoastModel
from horizon.sim.metrics import mission_metrics
from horizon.sim.power import HOLD_SPEED_MS
from horizon.sim.simulator import MissionResult, sample_wind
from horizon.weather.fields import WindField

__all__ = ["SCHEMA_VERSION", "SeedRun", "RecordingPolicy", "export_backtest", "merge_exports",
           "encode_array", "decode_array", "save_export", "load_export", "validate_export"]

SCHEMA_VERSION = 1
PRODUCTIVE_TWS_KN = (18.0, 26.0)
PRODUCTIVE_TWA_DEG = (75.0, 105.0)
TWS_HIST_EDGES_KN = np.arange(0.0, 52.0, 2.0)  # 25 bins, last one open-ended
TWA_HIST_EDGES_DEG = np.arange(0.0, 190.0, 10.0)  # 18 bins
_MAX_DIAG_ARRAY = 2000


# --------------------------------------------------------------------------- encoding helpers
def encode_array(a: np.ndarray, dtype: str) -> dict:
    """Encode an array as ``{"dtype", "shape", "b64"}`` (little-endian raw bytes).

    Parameters
    ----------
    a : ndarray  Array (cast to ``dtype``; the caller is responsible for quantisation).
    dtype : str  NumPy dtype name, e.g. ``"int8"``, ``"int16"``, ``"float32"``.
    """
    arr = np.ascontiguousarray(np.asarray(a).astype(np.dtype(dtype).newbyteorder("<")))
    return {"dtype": dtype, "shape": list(arr.shape),
            "b64": base64.b64encode(arr.tobytes()).decode("ascii")}


def decode_array(d: Mapping) -> np.ndarray:
    """Inverse of :func:`encode_array`."""
    raw = base64.b64decode(d["b64"])
    return np.frombuffer(raw, dtype=np.dtype(d["dtype"]).newbyteorder("<")).reshape(d["shape"])


def _listify(a, nd: int) -> list:
    """Round to ``nd`` decimals and convert to a list with non-finite values as ``None``."""
    a = np.asarray(a, float)
    r = np.round(a, nd)
    out = r.tolist()
    if np.all(np.isfinite(a)):
        return out
    return [None if not np.isfinite(v) else o for v, o in zip(a.ravel(), r.ravel().tolist(),
                                                              strict=True)]


def _jsonable(obj: Any, depth: int = 0) -> Any:
    """Make a diagnostics object JSON-safe (NumPy -> lists, large arrays -> summary stats)."""
    if depth > 6:
        return None
    if isinstance(obj, Mapping):
        return {str(k): _jsonable(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        if obj.size > _MAX_DIAG_ARRAY:
            f = obj[np.isfinite(obj)] if obj.dtype.kind == "f" else obj
            return {"shape": list(obj.shape), "min": float(f.min()), "max": float(f.max()),
                    "mean": float(f.mean())} if f.size else {"shape": list(obj.shape)}
        return _jsonable(obj.tolist(), depth + 1)
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v, depth + 1) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return round(v, 6) if np.isfinite(v) else None
    if isinstance(obj, (np.integer, np.bool_)):
        return obj.item()
    if isinstance(obj, (int, str, bool)) or obj is None:
        return obj
    return str(obj)


# ------------------------------------------------------------------------------------- recorder
class RecordingPolicy:
    """Wrap a policy to record, at every replan, the plan and ``last_diagnostics``.

    The wrapper is transparent (attributes of the wrapped policy are forwarded) so it can be
    passed to :func:`horizon.sim.simulator.run_mission` unchanged. After the mission,
    :attr:`records` holds one entry per replan.

    Parameters
    ----------
    policy : Policy  Any object with ``plan(t_s, x, y, provider)``.
    record_plans : bool  Store the planned destinations (km) when the plan object changes.
    """

    def __init__(self, policy, record_plans: bool = True):
        self._policy = policy
        self.record_plans = record_plans
        self.records: list[dict] = []
        self._last_plan = None

    def __getattr__(self, name):
        return getattr(self._policy, name)

    def plan(self, t_s, x, y, provider):
        """Delegate to the wrapped policy and record the outcome."""
        plan = self._policy.plan(t_s, x, y, provider)
        rec: dict = {"t_s": float(t_s)}
        v = float(getattr(plan, "value_kwh", float("nan")))
        rec["planned_value_kwh"] = round(v, 1) if np.isfinite(v) else None
        if self.record_plans and plan is not self._last_plan:
            rec["plan"] = {"t0_s": float(plan.t0_s), "dt_s": float(plan.dt_s),
                           "x_km": _listify(np.asarray(plan.x) / 1e3, 1),
                           "y_km": _listify(np.asarray(plan.y) / 1e3, 1)}
        self._last_plan = plan
        diag = getattr(self._policy, "last_diagnostics", None)
        if diag is not None:
            rec["diag"] = _jsonable(diag)
        self.records.append(rec)
        return plan


# ------------------------------------------------------------------------------------- inputs
@dataclass
class SeedRun:
    """All results of one seed (one synthetic winter).

    Attributes
    ----------
    seed : int
    truth : WindField  True wind covering the mission (also used for the map snapshots).
    results : dict[str, MissionResult]  Policy name -> mission result (insertion order kept).
    weather : object, optional  ``SyntheticWeather``-like: ``storm_centres(t)`` adds storm marks
        and ``forecast(...)`` enables the forecast-error-by-lead diagnostic.
    records : dict[str, list[dict]]  Policy name -> :attr:`RecordingPolicy.records` (optional).
    label : str, optional  Free label of the mission (e.g. ``"2015-03 W2"``) shown in the UI.
    """

    seed: int
    truth: WindField
    results: dict[str, MissionResult]
    weather: Any = None
    records: dict[str, list[dict]] = field(default_factory=dict)
    label: str | None = None


# ------------------------------------------------------------------------------- experienced wind
def experienced_wind(truth: WindField, res: MissionResult) -> tuple[np.ndarray, np.ndarray,
                                                                    np.ndarray]:
    """True wind experienced along a mission, per simulation step.

    Returns
    -------
    tws_ms : (n,) [m/s]  True wind speed at the step midpoint.
    twa_deg : (n,) [deg]  True wind angle in ``[0, 180]`` between the commanded true heading and
        the direction the wind blows FROM; ``nan`` while holding (ground speed < 0.5 m/s).
    speed_ms : (n,) [m/s]  Commanded ground speed.
    """
    dt = res.sim_dt_s
    u, v = sample_wind(truth, res.t_s[:-1] + 0.5 * dt, 0.5 * (res.x[:-1] + res.x[1:]),
                       0.5 * (res.y[:-1] + res.y[1:]))
    tws = np.hypot(u, v)
    wind_from = np.degrees(np.arctan2(-u, -v))
    twa = np.abs((res.heading_deg - wind_from + 180.0) % 360.0 - 180.0)
    twa = np.where(res.speed_ms < HOLD_SPEED_MS, np.nan, twa)
    return tws, twa, res.speed_ms


def _blocks(a: np.ndarray, k: int, nan_aware: bool = False) -> np.ndarray:
    """Mean of consecutive blocks of ``k`` samples (last block may be shorter)."""
    idx = np.arange(0, a.size, k)
    if not nan_aware:
        return np.add.reduceat(a, idx) / np.diff(np.append(idx, a.size))
    ok = np.isfinite(a)
    s = np.add.reduceat(np.where(ok, a, 0.0), idx)
    c = np.add.reduceat(ok.astype(float), idx)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(c > 0, s / np.maximum(c, 1), np.nan)


def _export_run(truth: WindField, res: MissionResult, records: list[dict] | None,
                p_rated_kw: float, step: int) -> dict:
    """Series, metrics and diagnostics of one policy run."""
    tws, twa, spd = experienced_wind(truth, res)
    tws_kn = tws / KNOT
    hold = spd < HOLD_SPEED_MS
    m = mission_metrics(res, p_rated_kw)
    in_tws = (tws_kn >= PRODUCTIVE_TWS_KN[0]) & (tws_kn <= PRODUCTIVE_TWS_KN[1])
    # While holding, the ship sails beam-reach tacks (TWA undefined in the series): hold time
    # counts as TWA-in-band, so the productive share only depends on TWS there.
    in_twa = ((twa >= PRODUCTIVE_TWA_DEG[0]) & (twa <= PRODUCTIVE_TWA_DEG[1])) | hold
    sail = ~hold
    tws_hist = np.histogram(np.minimum(tws_kn, TWS_HIST_EDGES_KN[-1] - 1e-6),
                            bins=TWS_HIST_EDGES_KN)[0] / tws.size
    twa_hist = (np.histogram(twa[sail], bins=TWA_HIST_EDGES_DEG)[0] / max(sail.sum(), 1)
                if sail.any() else np.zeros(TWA_HIST_EDGES_DEG.size - 1))
    sl = slice(0, None, step)
    out = {
        "lon": _listify(res.lon[sl], 3), "lat": _listify(res.lat[sl], 3),
        "x_km": _listify(res.x[sl] / 1e3, 1), "y_km": _listify(res.y[sl] / 1e3, 1),
        "energy_kwh": _listify(res.energy_kwh[sl], 1),
        "power_kw": _listify(_blocks(res.power_kw, step), 1),
        "hold_frac": _listify(_blocks(hold.astype(float), step), 2),
        "speed_ms": _listify(_blocks(spd, step), 3),
        "tws_ms": _listify(_blocks(tws, step), 2),
        "twa_deg": _listify(_blocks(twa, step, nan_aware=True), 1),
        "replans": records if records is not None
        else [{"t_s": float(t), "planned_value_kwh": None} for t in res.replan_times_s],
        "metrics": {"energy_kwh": round(m.energy_kwh, 1), "capacity_factor": m.capacity_factor,
                    "mean_power_kw": m.mean_power_kw, "distance_km": m.distance_km,
                    "hold_fraction": m.hold_fraction, "coast_violations": res.coast_violations,
                    "n_replans": res.n_replans},
        "diag": {"productive_share": float(np.mean(in_tws & in_twa)),
                 "tws_band_share": float(np.mean(in_tws)),
                 "twa_band_share": float(np.mean(in_twa)),
                 "hold_share": float(np.mean(hold)),
                 "mean_speed_ms": float(spd.mean()), "mean_tws_ms": float(tws.mean()),
                 "tws_hist": _listify(tws_hist, 5), "twa_hist": _listify(twa_hist, 5)},
    }
    if res.energy_kwh.size - 1 != res.power_kw.size:  # pragma: no cover - defensive
        raise ValueError("inconsistent MissionResult")
    return out


# ---------------------------------------------------------------------------------- wind / map
def _decimate(uv: np.ndarray, f: int) -> np.ndarray:
    """Block-mean ``f x f`` decimation of ``(T, ny, nx, 2)`` (edge-padded)."""
    if f == 1:
        return uv
    _, ny, nx, _ = uv.shape
    py, px = (-ny) % f, (-nx) % f
    a = np.pad(uv, ((0, 0), (0, py), (0, px), (0, 0)), mode="edge")
    t, ny2, nx2, c = a.shape
    return a.reshape(t, ny2 // f, f, nx2 // f, f, c).mean(axis=(2, 4))


def _export_wind(run: SeedRun, grid, wind_dt_s: float, factor: int,
                 duration_s: float) -> tuple[dict, np.ndarray]:
    tr = run.truth
    k = int(round(wind_dt_s / tr.dt_s)) if tr.dt_s > 0 else 1
    if abs(k * tr.dt_s - wind_dt_s) > 1e-6:
        raise ValueError("wind_dt_s must be a multiple of the truth time step")
    ts = np.arange(0.0, duration_s + 0.5 * wind_dt_s, wind_dt_s)
    ik = np.clip(np.rint((ts - tr.times_s[0]) / tr.dt_s).astype(int), 0, tr.times_s.size - 1)
    uv = _decimate(tr.uv[ik].astype(np.float32), factor)
    nt, ny, nx, _ = uv.shape
    scale = float(np.ceil(max(float(np.abs(uv).max()), 1.0) / 127.0 * 100.0) / 100.0)
    q = np.clip(np.rint(uv / scale), -127, 127).astype(np.int8)
    off = 0.5 * (factor - 1) * grid.dx
    dgrid = type(grid)(grid.crs_wkt, grid.x0 + off, grid.y0 + off, grid.dx * factor, nx, ny)
    lon, lat = dgrid.lonlat_mesh()
    e_east, _ = dgrid.local_basis(lon, lat)
    theta = np.arctan2(e_east[..., 1], e_east[..., 0])
    return {"nt": nt, "ny": ny, "nx": nx, "x0_km": dgrid.x0 / 1e3, "y0_km": dgrid.y0 / 1e3,
            "dx_km": dgrid.dx / 1e3, "dt_s": wind_dt_s, "scale_ms": scale,
            "u": encode_array(q[..., 0], "int8"), "v": encode_array(q[..., 1], "int8"),
            "theta": encode_array(theta, "float32")}, ts


def _graticule(grid) -> list[dict]:
    lon, lat = grid.lonlat_mesh()
    out = []
    for lo in np.arange(np.ceil(lon.min() / 10) * 10, lon.max() + 1e-6, 10.0):
        la = np.linspace(lat.min(), lat.max(), 60)
        x, y = grid.to_xy(np.full_like(la, lo), la)
        out.append({"label": f"{abs(lo):g}°{'W' if lo < 0 else 'E'}",
                    "x_km": _listify(np.asarray(x) / 1e3, 1),
                    "y_km": _listify(np.asarray(y) / 1e3, 1)})
    for la0 in np.arange(np.ceil(lat.min() / 5) * 5, lat.max() + 1e-6, 5.0):
        lo = np.linspace(lon.min(), lon.max(), 80)
        x, y = grid.to_xy(lo, np.full_like(lo, la0))
        out.append({"label": f"{la0:g}°N",
                    "x_km": _listify(np.asarray(x) / 1e3, 1),
                    "y_km": _listify(np.asarray(y) / 1e3, 1)})
    return out


def _marker(grid, name: str, lon: float, lat: float) -> dict:
    x, y = grid.to_xy(lon, lat)
    return {"name": name, "lon": float(lon), "lat": float(lat), "x_km": float(x) / 1e3,
            "y_km": float(y) / 1e3}


def _forecast_error(weather, truth: WindField, results: Mapping[str, MissionResult],
                    duration_s: float, horizon_s: float, every_s: float,
                    dt_s: float = 10800.0) -> dict:
    """Control-forecast wind error AT THE SHIP POSITION by lead time, per policy track."""
    leads = np.arange(0.0, horizon_s + 0.5 * dt_s, dt_s)
    acc = {n: {k: np.zeros(leads.size) for k in ("abs", "vec2", "bias", "cnt")} for n in results}
    for issue in np.arange(0.0, duration_s - dt_s, every_s):
        h = min(horizon_s, np.floor((duration_s - issue) / dt_s) * dt_s)
        if h < dt_s:
            continue
        member = weather.forecast(issue, h, 1, dt_s=dt_s).member(0)
        t = member.times_s
        nl = t.size
        for name, res in results.items():
            x, y = np.interp(t, res.t_s, res.x), np.interp(t, res.t_s, res.y)
            uf, vf = sample_wind(member, t, x, y)
            ut, vt = sample_wind(truth, t, x, y)
            a = acc[name]
            a["abs"][:nl] += np.abs(np.hypot(uf, vf) - np.hypot(ut, vt))
            a["vec2"][:nl] += (uf - ut) ** 2 + (vf - vt) ** 2
            a["bias"][:nl] += np.hypot(uf, vf) - np.hypot(ut, vt)
            a["cnt"][:nl] += 1
    by = {}
    for n, a in acc.items():
        c = np.maximum(a["cnt"], 1)
        by[n] = {"mae_tws_ms": _listify(np.where(a["cnt"] > 0, a["abs"] / c, np.nan), 3),
                 "rmse_vec_ms": _listify(np.where(a["cnt"] > 0, np.sqrt(a["vec2"] / c), np.nan), 3),
                 "bias_tws_ms": _listify(np.where(a["cnt"] > 0, a["bias"] / c, np.nan), 3)}
    return {"lead_h": (leads / 3600.0).tolist(), "issue_every_h": every_s / 3600.0, "by_policy": by}


# -------------------------------------------------------------------------------------- export
def export_backtest(runs: Sequence[SeedRun], coast: CoastModel, *, reference: str = "Oracle",
                    title: str = "HORIZON router inspector", p_rated_kw: float = 3000.0,
                    export_dt_s: float = 3600.0, wind_dt_s: float | None = None,
                    wind_factor: int | None = None,
                    policy_info: Mapping[str, Mapping] | None = None,
                    markers: Sequence[Mapping] | None = None,
                    start_lonlat: tuple[float, float] | None = None,
                    params: Mapping | None = None, forecast_error: bool = True,
                    fc_horizon_days: float = 5.0, fc_issue_every_s: float = 86400.0,
                    polar=None, weather_kind: str | None = None,
                    era5_mask: np.ndarray | None = None, wind_budget_mb: float = 6.0,
                    max_plan_records: int = 400) -> dict:
    """Collect backtest outputs into the inspector schema (see module docstring).

    Parameters
    ----------
    runs : sequence of SeedRun  One entry per seed; policy names may differ between seeds but
        paired comparisons only use seeds where both policies exist.
    coast : CoastModel  Land mask / SDF of the map grid (same grid as the truth).
    reference : str  Policy used as the regret / gap reference (the hindsight oracle).
    title : str  Page title.
    p_rated_kw : float  [kW]  Rated power for the capacity factor.
    export_dt_s : float  [s]  Time step of the exported series (multiple of the simulation step).
    wind_dt_s : float, optional  [s]  Time step of the truth wind snapshots (multiple of the truth
        step). ``None`` = automatic: 3 h, coarsened (6 h, 12 h, then 160 km cells) until each seed's
        wind block is below ``wind_budget_mb`` (year-long missions).
    wind_factor : int  Spatial block-decimation factor of the snapshots (2 -> 80 km on 40 km).
    policy_info : mapping, optional  ``name -> {"label", "description", "params"}``.
    markers : sequence of dict, optional  ``{"name", "lon", "lat"}`` shown on the map.
    start_lonlat : tuple, optional  ``(lon, lat)`` [deg] of the mission start.
    params : mapping, optional  Free-form run parameters shown in the header.
    forecast_error : bool  Compute control-forecast error at the ship (needs ``run.weather``).
    fc_horizon_days, fc_issue_every_s : float  Lead range [d] and issue spacing [s] for it.
    polar : PolarTable, optional  Polar used by the policies; embedded (compact) for the Polar tab
        and the Explorer operating-point inset.
    weather_kind : str, optional  ``"synthetic"`` or ``"era5"`` (ERA5 hides storm layers and labels
        missions with their real UTC dates).
    era5_mask : (ny, nx) bool array, optional  True inside the ERA5 box (cells outside are greyed).
    wind_budget_mb : float  Size budget of the wind snapshots of one seed (raw int8, MB).
    max_plan_records : int  Per run, at most this many replans keep their ``plan`` / ``diag``
        (evenly thinned) so that year-long missions stay compact.

    Returns
    -------
    dict
        JSON-serialisable export (``schema_version`` = :data:`SCHEMA_VERSION`).
    """
    if not runs:
        raise ValueError("no runs to export")
    grid = coast.grid
    sim_dt = next(iter(runs[0].results.values())).sim_dt_s
    step = int(round(export_dt_s / sim_dt))
    if step < 1 or abs(step * sim_dt - export_dt_s) > 1e-6:
        raise ValueError("export_dt_s must be a multiple of the simulation step")
    duration = next(iter(runs[0].results.values())).t_s[-1]
    names: list[str] = []
    for r in runs:
        names += [n for n in r.results if n not in names]
    info = policy_info or {}
    wdt, wfac = _auto_wind(runs[0].truth, grid, duration, wind_dt_s, wind_factor, wind_budget_mb)
    seeds_out = []
    for r in runs:
        wind, wts = _export_wind(r, grid, wdt, wfac, duration)
        storms = []
        if hasattr(r.weather, "storm_centres"):
            storms = [_listify(np.asarray(r.weather.storm_centres(float(t))) / 1e3, 1)
                      for t in wts]
        sea = coast.sdf > 0
        tws_all = np.hypot(r.truth.uv[..., 0], r.truth.uv[..., 1])[:, sea]
        n_t = next(iter(r.results.values())).t_s[::step]
        entry = {
            "seed": int(r.seed), "t_s": _listify(n_t, 1),
            "epoch": str(np.datetime_as_string(np.datetime64(r.truth.epoch, "s"), timezone="UTC")),
            "label": r.label,
            "weather": {"mean_tws_ms": float(tws_all.mean()),
                        "frac_18_26kn": float(np.mean((tws_all >= 18 * KNOT)
                                                      & (tws_all <= 26 * KNOT)))},
            "wind": wind, "storms": storms,
            "runs": {n: _export_run(r.truth, res, _thin(r.records.get(n), max_plan_records),
                                    p_rated_kw, step)
                     for n, res in r.results.items()},
        }
        if forecast_error and hasattr(r.weather, "forecast"):
            entry["forecast_error"] = _forecast_error(
                r.weather, r.truth, r.results, duration, fc_horizon_days * 86400.0,
                fc_issue_every_s)
        seeds_out.append(entry)
    mk = [_marker(grid, m["name"], m["lon"], m["lat"]) for m in (markers or [])]
    start = _marker(grid, "start", *start_lonlat) if start_lonlat else None
    epoch = str(np.datetime_as_string(np.datetime64(runs[0].truth.epoch, "s"), timezone="UTC"))
    out = {
        "schema_version": SCHEMA_VERSION, "title": title,
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "meta": {"epoch": epoch, "duration_s": float(duration), "sim_dt_s": float(sim_dt),
                 "export_dt_s": float(export_dt_s), "p_rated_kw": float(p_rated_kw),
                 "reference": reference, "hold_speed_ms": HOLD_SPEED_MS,
                 "productive": {"tws_kn": list(PRODUCTIVE_TWS_KN),
                                "twa_deg": list(PRODUCTIVE_TWA_DEG)},
                 "params": _jsonable(dict(params or {}))},
        "policies": [{"name": n, **_jsonable(dict(info.get(n, {})))} for n in names],
        "map": {"grid": {"nx": grid.nx, "ny": grid.ny, "dx_km": grid.dx / 1e3,
                         "x0_km": grid.x0 / 1e3, "y0_km": grid.y0 / 1e3},
                "sdf": {**encode_array(np.clip(np.rint(coast.sdf / 100.0), -32000, 32000),
                                       "int16"), "unit_km": 0.1},
                "graticule": _graticule(grid), "markers": mk, "start": start},
        "seeds": seeds_out,
    }
    if weather_kind:
        out["meta"]["weather_kind"] = weather_kind
    if era5_mask is not None:
        m = np.asarray(era5_mask, bool).astype(np.uint8)
        out["map"]["era5_mask"] = encode_array(m, "uint8")
    if polar is not None:
        out["polar"] = _export_polar(polar)
    return out


def _auto_wind(truth, grid, duration, dt_s, factor, budget_mb) -> tuple[float, int]:
    """Wind snapshot step and decimation: explicit values win, else fit ``budget_mb``."""
    if dt_s is not None and factor is not None:
        return float(dt_s), int(factor)
    base = max(truth.dt_s, 3600.0)
    for dt_h, f in ((3, 2), (6, 2), (12, 2), (12, 4), (24, 4)):
        dt = float(dt_s) if dt_s is not None else max(dt_h * 3600.0, base)
        fac = int(factor) if factor is not None else f
        nt = int(duration // dt) + 1
        cells = int(np.ceil(grid.ny / fac) * np.ceil(grid.nx / fac))
        if nt * cells * 2 <= budget_mb * 1e6:
            break
    return dt, fac


def _thin(records: list[dict] | None, max_n: int) -> list[dict] | None:
    """Keep ``plan`` / ``diag`` on at most ``max_n`` evenly spaced replans (others lose them)."""
    if records is None or len(records) <= max_n:
        return records
    stride = int(np.ceil(len(records) / max_n))
    return [r if i % stride == 0 else {k: v for k, v in r.items() if k not in ("plan", "diag")}
            for i, r in enumerate(records)]


def _export_polar(polar, tws_step_kn: float = 2.0) -> dict:
    """Compact copy of a :class:`horizon.polar.table.PolarTable` for the Polar tab.

    TWS is decimated to multiples of ``tws_step_kn`` (nearest axis node); power is quantised to
    int16 in units of ``scale_kw`` with ``-32768`` marking infeasible nodes (NaN).
    """
    tws_kn = np.asarray(polar.tws) / KNOT
    want = np.arange(0.0, tws_kn[-1] + 1e-6, tws_step_kn)
    idx = sorted({int(np.argmin(np.abs(tws_kn - w))) for w in want if abs(tws_kn - w).min() < 0.5})
    p = np.asarray(polar.p, float)[idx]
    scale = 0.5
    q = np.where(np.isfinite(p), np.clip(np.rint(p / scale), -32767, 32767), -32768)
    meta = {k: v for k, v in (polar.meta or {}).items()
            if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 160}
    return {"tws_kn": _listify(tws_kn[idx], 2), "twa_deg": _listify(polar.twa, 2),
            "u_ms": _listify(polar.u, 3), "scale_kw": scale, "infeasible": -32768,
            "p": encode_array(q, "int16"), "meta": _jsonable(meta)}


def merge_exports(base: dict, extra: dict, overwrite: bool = True) -> dict:
    """Add the policies of ``extra`` to ``base`` (same seeds, same map); returns ``base``.

    Lets later sprints (S2 policies) be appended to a previously exported S1 file without
    re-running it. Wind, map and metadata of ``base`` are kept; seeds missing from ``base`` are
    ignored.

    Parameters
    ----------
    base, extra : dict  Exports with the same ``schema_version`` and simulation time axis.
    overwrite : bool  Replace a policy of the same name (otherwise keep the one in ``base``).
    """
    if base["schema_version"] != extra["schema_version"]:
        raise ValueError("schema_version mismatch")
    by_seed = {s["seed"]: s for s in base["seeds"]}
    known = {p["name"] for p in base["policies"]}
    for pol in extra["policies"]:
        if pol["name"] not in known:
            base["policies"].append(pol)
            known.add(pol["name"])
        elif overwrite:
            base["policies"] = [pol if p["name"] == pol["name"] else p for p in base["policies"]]
    for s in extra["seeds"]:
        tgt = by_seed.get(s["seed"])
        if tgt is None:
            continue
        if len(s["t_s"]) != len(tgt["t_s"]):
            raise ValueError(f"seed {s['seed']}: time axis mismatch")
        for n, run in s["runs"].items():
            if overwrite or n not in tgt["runs"]:
                tgt["runs"][n] = run
        if "forecast_error" in s and "forecast_error" in tgt:
            tgt["forecast_error"]["by_policy"].update(s["forecast_error"]["by_policy"])
    return base


# ------------------------------------------------------------------------------------------ io
def save_export(data: dict, path: str | Path) -> Path:
    """Write an export as compact JSON (gzip-compressed if the name ends with ``.gz``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    path.write_bytes(gzip.compress(raw, 9) if path.suffix == ".gz" else raw)
    return path


def load_export(path: str | Path) -> dict:
    """Read an export written by :func:`save_export` and validate it."""
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    data = json.loads(raw)
    validate_export(data)
    return data


def validate_export(data: Mapping) -> None:
    """Check structure and array-length consistency; raises ``ValueError`` on problems."""
    def need(cond: bool, msg: str):
        if not cond:
            raise ValueError(f"invalid export: {msg}")

    need(data.get("schema_version") == SCHEMA_VERSION,
         f"schema_version {data.get('schema_version')!r} != {SCHEMA_VERSION}")
    for k in ("title", "meta", "policies", "map", "seeds"):
        need(k in data, f"missing key {k!r}")
    names = [p["name"] for p in data["policies"]]
    need(len(set(names)) == len(names), "duplicate policy names")
    need(data["meta"]["reference"] in names or not names, "reference policy not exported")
    need(len(data["seeds"]) > 0, "no seeds")
    g = data["map"]["grid"]
    need(list(decode_array(data["map"]["sdf"]).shape) == [g["ny"], g["nx"]], "sdf shape")
    if "polar" in data:
        pl = data["polar"]
        need(decode_array(pl["p"]).shape == (len(pl["tws_kn"]), len(pl["twa_deg"]),
                                             len(pl["u_ms"])), "polar shape")
    for s in data["seeds"]:
        n1 = len(s["t_s"])
        w = s["wind"]
        need(decode_array(w["u"]).shape == (w["nt"], w["ny"], w["nx"]), "wind u shape")
        need(decode_array(w["v"]).shape == (w["nt"], w["ny"], w["nx"]), "wind v shape")
        need(not s["storms"] or len(s["storms"]) == w["nt"], "storms / wind snapshots mismatch")
        for n, r in s["runs"].items():
            need(n in names, f"run {n!r} has no policy entry")
            for k in ("lon", "lat", "x_km", "y_km", "energy_kwh"):
                need(len(r[k]) == n1, f"seed {s['seed']} {n}.{k} length")
            for k in ("power_kw", "hold_frac", "tws_ms", "twa_deg"):
                need(len(r[k]) == n1 - 1, f"seed {s['seed']} {n}.{k} length")
            for k in ("energy_kwh", "capacity_factor", "hold_fraction"):
                need(k in r["metrics"], f"{n}.metrics.{k}")
