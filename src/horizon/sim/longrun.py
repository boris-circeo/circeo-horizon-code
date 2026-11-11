"""Long persistent missions (up to a year) with monthly checkpoints, streaming truth, metrics.

:func:`run_persistent` advances one mission segment by segment (default: calendar months, or any
fixed number of seconds). At every segment boundary the complete state is written to disk; a run
that is killed and restarted with the same arguments resumes from the last committed segment and
produces a result identical to an uninterrupted run (the policy is re-created by the caller and
only needs the optional ``get_state()`` / ``set_state(dict)`` protocol if it carries hidden state;
the shipped policies are stateless between replans).

Memory: the true wind is read per segment through ``weather.truth(dt_s, start_s, end_s)`` (one
month of hourly 40 km ERA5 is ~40 MB) and dropped afterwards; forecasts are issued from the
archive on demand. Only the executed track (a few MB per year at 900 s) is kept.

Checkpoint format (directory ``out_dir``)::

    meta.json              run signature (start, step, replan, d_min, end, segments, grid, tag)
    seg_0003.npz           arrays of segment 3: x, y [m] (start of every step), power_kw,
                           heading_deg, speed_ms (n steps each), replans (times [s])
    seg_0003.json         commit marker + state at the END of segment 3: step, x, y, active plan
                           (t0_s, dt_s, x, y), next_replan, cumulative energy / guard counters /
                           min margin, guard events, policy state, segment metrics
    summary.json           written at the end: per-segment metrics and totals

``seg_k.npz`` is written first, ``seg_k.json`` last (both through ``os.replace``): a segment
without its json is ignored and recomputed.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from horizon.geo.coast import SDF_TOL_M, CoastModel
from horizon.sim.policies import Plan
from horizon.sim.power import HOLD_SPEED_MS, PowerModel
from horizon.sim.simulator import MissionResult, SimState, advance, energy_on_truth_ex, track_tws

__all__ = ["PersistentResult", "RunInterrupted", "SegmentMetrics", "run_persistent",
           "segment_boundaries"]

_VERSION = 1


class RunInterrupted(RuntimeError):
    """Raised by ``run_persistent(stop_after_segments=n)`` (test hook for an interrupted run)."""


@dataclass(frozen=True)
class SegmentMetrics:
    """Metrics of one segment (month).

    Attributes
    ----------
    label : str  ``YYYY-MM`` (months) or ``seg_k``.
    hours : float  [h]. energy_kwh : float  [kWh]. capacity_factor : float  ``E / (P_rated hours)``.
    hold_share : float  Fraction of steps with ground speed below 0.5 m/s.
    distance_km : float  [km]. guard_interventions : int  Coast guard interventions in the segment.
    replans : int. min_margin_m : float  [m]  Minimum ``SDF - d_min`` over executed chords.
    n_clamped : int  FeasiblePowerModel samples evaluated at a reduced speed.
    wall_s : float  [s]  Wall time of the segment (not part of the checkpoint identity).
    n_tack, n_gybe, n_turn : int  Manoeuvres charged (0 when the manoeuvre model is off).
    storm35_h, storm45_h : float [h] with true TWS above 35 / 45 kn; mean_tws : float [m/s].
    """

    label: str
    hours: float
    energy_kwh: float
    capacity_factor: float
    hold_share: float
    distance_km: float
    guard_interventions: int
    replans: int
    min_margin_m: float
    n_clamped: int
    wall_s: float
    n_tack: int = 0
    n_gybe: int = 0
    n_turn: int = 0
    storm35_h: float = 0.0
    storm45_h: float = 0.0
    mean_tws: float = 0.0


@dataclass(frozen=True)
class PersistentResult:
    """Outcome of :func:`run_persistent`.

    Attributes
    ----------
    result : MissionResult  The whole executed mission (track at ``sim_dt_s``).
    segments : list of SegmentMetrics. resumed_from : int  Number of segments loaded from disk.
    out_dir : Path.
    """

    result: MissionResult
    segments: list
    resumed_from: int
    out_dir: Path

    @property
    def energy_kwh(self) -> float:
        return float(self.result.energy_kwh[-1])


def segment_boundaries(epoch, n_steps: int, sim_dt_s: float, segments="month") -> list[int]:
    """Step indices ``0 = b_0 < b_1 < ... < b_m = n_steps`` delimiting the segments.

    ``segments = "month"``: calendar month starts (UTC) after ``epoch`` (must fall on integer
    steps); a number: fixed segment length in seconds.
    """
    if segments == "month":
        t0 = np.datetime64(epoch, "s")
        t1 = t0 + np.timedelta64(int(round(n_steps * sim_dt_s)), "s")
        m = t0.astype("datetime64[M]") + np.timedelta64(1, "M")
        b = [0]
        while m.astype("datetime64[s]") < t1:
            s = (m.astype("datetime64[s]") - t0) / np.timedelta64(1, "s")
            k = s / sim_dt_s
            if abs(k - round(k)) > 1e-6:
                raise ValueError("month boundary not on a simulation step")
            b.append(int(round(k)))
            m = m + np.timedelta64(1, "M")
    else:
        step = int(round(float(segments) / sim_dt_s))
        b = list(range(0, n_steps, step))
    return [x for x in b if x < n_steps] + [n_steps]


# ------------------------------------------------------------------------------------ IO helpers
def _atomic_json(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(obj, fh, allow_nan=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _atomic_npz(path: Path, **arrays) -> None:
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


def _label(epoch, a: int, b: int, k: int, sim_dt_s: float, segments) -> str:
    if segments == "month":
        t = np.datetime64(epoch, "s") + np.timedelta64(int(round(a * sim_dt_s)), "s")
        return str(t.astype("datetime64[M]"))
    return f"seg_{k:04d}"


def run_persistent(policy, weather, start_lonlat, power_model: PowerModel, coast: CoastModel,
                   out_dir, duration_s: float | None = None, replan_s: float = 6 * 3600.0,
                   sim_dt_s: float = 900.0, u_max: float = 8.0, d_min_m: float = 20e3,
                   segments="month", p_rated_kw: float = 3000.0, tag: str = "", resume: bool = True,
                   stop_after_segments: int | None = None, log=None,
                   manoeuvre=None) -> PersistentResult:
    """Run a (year-long) mission segment by segment with checkpoints; resumable.

    Parameters
    ----------
    policy : Policy  Optionally with ``get_state() -> dict`` / ``set_state(dict)`` (JSON-able).
    weather : source with ``forecast(...)``, ``truth(dt_s, start_s, end_s)``, ``epoch``, and
        optionally ``archive`` (``ERA5Archive``: its ``end`` truncates the mission) and
        ``duration_s``.
    start_lonlat : (lon, lat) [deg]. power_model : PowerModel. coast : CoastModel.
    out_dir : checkpoint directory (created). duration_s : [s] mission length; default / maximum:
        the end of the available data. Forecast horizons are truncated at the mission end
        (:class:`~horizon.sim.simulator.ForecastProvider`), never wrapped around.
    replan_s, sim_dt_s, u_max, d_min_m : as :func:`horizon.sim.simulator.run_mission`.
    segments : ``"month"`` or seconds per segment. p_rated_kw : rated power for the capacity factor.
    tag : str  Free text stored in the run signature (policy name, ...).
    resume : bool  Resume from the last committed segment if ``out_dir`` holds a matching run;
        a non-matching run raises ``ValueError``.
    stop_after_segments : int, optional  Raise :class:`RunInterrupted` after that many NEW
        segments (tests).
    log : callable, optional  ``log(str)`` progress sink.
    manoeuvre : ManoeuvreModel, optional  Manoeuvre losses (:mod:`horizon.sim.manoeuvre`); None or
        disabled reproduces Sprint 4 (same run signature, bit-identical results).

    Returns
    -------
    PersistentResult
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    g = coast.grid
    epoch = np.datetime64(weather.epoch, "s")
    end_s = float("inf") if duration_s is None else float(duration_s)
    if hasattr(weather, "archive"):
        end_s = min(end_s, float((weather.archive.end - epoch) / np.timedelta64(1, "s")))
    if hasattr(weather, "duration_s"):
        end_s = min(end_s, float(weather.duration_s))
    if not np.isfinite(end_s):
        raise ValueError("duration_s is required for a weather source without data end")
    n_total = int(np.floor(end_s / sim_dt_s + 1e-9))
    end_s = n_total * sim_dt_s
    bnd = segment_boundaries(epoch, n_total, sim_dt_s, segments)
    x0, y0 = g.to_xy(*start_lonlat)
    sig = {"version": _VERSION, "tag": tag, "start_lonlat": [float(start_lonlat[0]),
                                                             float(start_lonlat[1])],
           "epoch": str(epoch), "end_s": end_s, "replan_s": replan_s, "sim_dt_s": sim_dt_s,
           "u_max": u_max, "d_min_m": d_min_m, "segments": segments if segments == "month"
           else float(segments), "grid": [g.nx, g.ny, g.dx], "bounds": bnd}
    man_on = manoeuvre is not None and manoeuvre.enabled
    if man_on:
        sig["manoeuvre"] = manoeuvre.signature()
    meta_path = out / "meta.json"
    if meta_path.exists() and resume:
        old = json.loads(meta_path.read_text())
        if old != json.loads(json.dumps(sig)):
            raise ValueError(f"{meta_path}: existing run has a different signature "
                             f"(use another out_dir or resume=False): {old} != {sig}")
    else:
        for f in list(out.glob("seg_*")) + list(out.glob("summary.json")):
            f.unlink()
        _atomic_json(meta_path, sig)

    # ---- load committed segments
    done: list[dict] = []
    for k in range(len(bnd) - 1):
        js, nz = out / f"seg_{k:04d}.json", out / f"seg_{k:04d}.npz"
        if not (js.exists() and nz.exists()):
            break
        done.append(json.loads(js.read_text()))
    state = SimState(0, float(x0), float(y0))
    carried = {"energy_kwh": 0.0, "man_prev": None}
    if done:
        st = done[-1]["state"]
        plan = st["plan"]
        state = SimState(
            int(st["step"]), float(st["x"]), float(st["y"]),
            None if plan is None else Plan(plan["t0_s"], plan["dt_s"], np.array(plan["x"]),
                                           np.array(plan["y"]), plan["value_kwh"]),
            float(st["next_replan"]), list(st["replans"]), int(st["guard_interventions"]),
            [tuple(e) for e in st["guard_events"]], float(st["min_margin_m"]))
        carried["energy_kwh"] = float(st["energy_kwh"])
        mp = st.get("man_prev")
        carried["man_prev"] = None if mp is None else tuple(mp)
        if st.get("policy_state") is not None and hasattr(policy, "set_state"):
            policy.set_state(st["policy_state"])
    resumed = len(done)
    if log and resumed:
        log(f"resuming from segment {resumed} of {len(bnd) - 1} (step {state.step})")

    metrics = [SegmentMetrics(**d["metrics"]) for d in done]
    new = 0
    for k in range(resumed, len(bnd) - 1):
        a, b = bnd[k], bnd[k + 1]
        t_a, t_b = a * sim_dt_s, b * sim_dt_s
        t_wall = time.perf_counter()
        g0, c0 = state.guard_interventions, getattr(power_model, "n_clamped", 0)
        r0 = len(state.replans)
        xs, ys, ve, vn = advance(policy, weather, coast, state, b - a, end_s, replan_s, sim_dt_s,
                                 u_max, d_min_m)
        h0 = np.floor(t_a / 3600.0) * 3600.0
        h1 = min(np.ceil(t_b / 3600.0) * 3600.0 + 3600.0, end_s)
        truth = weather.truth(dt_s=3600.0, start_s=float(h0), end_s=float(max(h1, h0 + 3600.0)))
        p, kind, carried["man_prev"] = energy_on_truth_ex(
            truth, power_model, t_a, sim_dt_s, xs, ys, ve, vn, manoeuvre, carried["man_prev"])
        tws = track_tws(truth, t_a, sim_dt_s, xs, ys)
        del truth
        e_seg = float(p.sum() * sim_dt_s / 3600.0)
        carried["energy_kwh"] += e_seg
        hours = (b - a) * sim_dt_s / 3600.0
        m = SegmentMetrics(
            _label(epoch, a, b, k, sim_dt_s, segments), hours, e_seg, e_seg / (p_rated_kw * hours),
            float(np.mean(np.hypot(ve, vn) < HOLD_SPEED_MS)),
            float(np.hypot(ve, vn).sum() * sim_dt_s / 1e3), state.guard_interventions - g0,
            len(state.replans) - r0, float(state.min_margin_m),
            int(getattr(power_model, "n_clamped", 0) - c0), time.perf_counter() - t_wall,
            int((kind == 1).sum()), int((kind == 2).sum()), int((kind == 3).sum()),
            float((tws > 35 * 0.514444).sum() * sim_dt_s / 3600.0),
            float((tws > 45 * 0.514444).sum() * sim_dt_s / 3600.0), float(tws.mean()))
        extra = {"man_kind": kind} if man_on else {}
        _atomic_npz(out / f"seg_{k:04d}.npz", x=xs[:-1], y=ys[:-1], power_kw=p,
                    heading_deg=np.degrees(np.arctan2(ve, vn)) % 360.0, speed_ms=np.hypot(ve, vn),
                    replans=np.array(state.replans[r0:]), **extra)
        pl = state.plan
        _atomic_json(out / f"seg_{k:04d}.json", {
            "metrics": m.__dict__,
            "state": {
                "step": state.step, "x": state.x, "y": state.y,
                "plan": None if pl is None else {
                    "t0_s": pl.t0_s, "dt_s": pl.dt_s, "x": pl.x.tolist(), "y": pl.y.tolist(),
                    "value_kwh": float(pl.value_kwh)},
                "next_replan": state.next_replan, "replans": state.replans,
                "guard_interventions": state.guard_interventions,
                "guard_events": [list(e) for e in state.guard_events],
                "min_margin_m": state.min_margin_m, "energy_kwh": carried["energy_kwh"],
                "man_prev": carried["man_prev"],
                "policy_state": policy.get_state() if hasattr(policy, "get_state") else None}})
        metrics.append(m)
        if log:
            log(f"{m.label}: E {m.energy_kwh / 1e3:.1f} MWh CF {m.capacity_factor:.3f} hold "
                f"{m.hold_share:.2f} dist {m.distance_km:.0f} km guard {m.guard_interventions} "
                f"[{m.wall_s:.0f} s]")
        new += 1
        if stop_after_segments is not None and new >= stop_after_segments and k < len(bnd) - 2:
            raise RunInterrupted(f"stopped after {new} new segments")

    res = _assemble(out, len(bnd) - 1, sim_dt_s, g, coast, state, d_min_m, man_on)
    _atomic_json(out / "summary.json", {
        "segments": [m.__dict__ for m in metrics], "energy_kwh": float(res.energy_kwh[-1]),
        "guard_interventions": state.guard_interventions, "coast_violations": res.coast_violations,
        "min_margin_m": state.min_margin_m,
        "manoeuvres": {"tack": int(sum(m.n_tack for m in metrics)),
                       "gybe": int(sum(m.n_gybe for m in metrics)),
                       "turn": int(sum(m.n_turn for m in metrics))}})
    return PersistentResult(res, metrics, resumed, out)


def _assemble(out: Path, n_seg: int, sim_dt_s: float, g, coast: CoastModel, state: SimState,
              d_min_m: float, man_on: bool = False) -> MissionResult:
    parts = [np.load(out / f"seg_{k:04d}.npz") for k in range(n_seg)]
    cat = {key: np.concatenate([z[key] for z in parts]) for key in
           ("x", "y", "power_kw", "heading_deg", "speed_ms") + (("man_kind",) if man_on else ())}
    xs = np.concatenate([cat["x"], [state.x]])
    ys = np.concatenate([cat["y"], [state.y]])
    n = cat["power_kw"].size
    energy = np.concatenate([[0.0], np.cumsum(cat["power_kw"] * sim_dt_s / 3600.0)])
    lon, lat = g.to_lonlat(xs, ys)
    viol = int(np.count_nonzero(~(coast.sdf_at(xs, ys) >= d_min_m - SDF_TOL_M)))
    return MissionResult(
        sim_dt_s * np.arange(n + 1), xs, ys, np.asarray(lon), np.asarray(lat), cat["power_kw"],
        energy, cat["heading_deg"], cat["speed_ms"], np.array(state.replans), viol,
        float(sim_dt_s), state.guard_interventions, tuple(state.guard_events),
        float(state.min_margin_m), cat["man_kind"] if man_on else None)
