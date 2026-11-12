"""Sprint-5 sensitivity campaign: case specification, normalisation, building and execution.

A CASE = (router config, environment config, window start, duration, forecast seed). Specs are
normalised (default-valued overrides dropped, fields irrelevant to the router type dropped) so that
identical cases requested by several experiments share one result file. Client ERA5 data is
confidential: results hold aggregated metrics only; checkpoints hold executed tracks (git-ignored
under ``outputs/``).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import resource
import sys
import time
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
OUT = Path(os.environ.get("S5_OUT", ROOT / "outputs" / "s5"))  # S5_OUT: tests only
RUNS, LOGS, LOCKS, CKPT, ERRS, CACHE = (OUT / d for d in
                                        ("runs", "logs", "locks", "ckpt", "errors", "cache"))
LORIENT = (-3.4, 47.7)
MID_ATLANTIC = (-20.0, 46.0)

ROUTER_DEFAULTS = {
    "B1c_5d_REF": dict(horizon_days=5.0, replan_h=6.0, refiner_h=48.0, terminal="clim",
                       terminal_days=5.0, max_span=2, router_polar="nominal", storm_kn=0.0),
    # B1c on the ENSEMBLE MEAN of `members` (blend_h > 0: control up to that lead, mean beyond)
    "B1m_5d_REF": dict(horizon_days=5.0, replan_h=6.0, refiner_h=48.0, terminal="clim",
                       terminal_days=5.0, max_span=2, router_polar="nominal", storm_kn=0.0,
                       members=10, blend_h=0.0),
    # greedy baselines (no DP): best reachable cell by forecast hold power / by wind speed
    "GREEDY_HOLD24": dict(replan_h=6.0, reach_h=24.0, window_h=24.0, speed=6.0),
    "GREEDY_MAXWIND": dict(replan_h=6.0, reach_h=24.0, window_h=24.0, speed=6.0, tws_cap=14.0),
    "ENS_REF": dict(members=20, k=6, gamma=0.0, alpha=0.2, horizon_days=10.0, replan_h=6.0,
                    refiner_h=48.0, terminal="clim", terminal_days=5.0, max_span=2,
                    router_polar="nominal", storm_kn=0.0),
    "Oracle_REF_H": dict(horizon_days=15.0, replan_h=6.0, refiner_h=48.0, terminal="clim",
                         terminal_days=5.0, max_span=2, router_polar="nominal", storm_kn=0.0),
    "B0": dict(),
}
ENV_DEFAULTS = dict(
    error_scale=1.0, latency_h=6.0, consistency=True, spread_factor=1.0, season_amp=0.15,
    manoeuvre=True, tau_scale=1.0, man_rho=0.3, man_fixed_kwh=0.0,
    truth_polar_scale=1.0, truth_polar_twa_shift=0.0, d_min_km=20.0, grid_km=40.0,
    start="offshore", disp_scale=1.0, amp_scale=1.0, noise_scale=1.0, structure="default",
    analog_scale=1.0)
FORECAST_KEYS = ("error_scale", "latency_h", "consistency", "spread_factor", "season_amp",
                 "disp_scale", "amp_scale", "noise_scale", "structure", "analog_scale")
# knobs of the environment that do not influence a router that sees no forecast
SEED_FREE = ("Oracle_REF_H", "B0")
WINDOWS = {
    "bench6": ["2015-01-01", "2015-03-01", "2015-05-01", "2015-07-01", "2015-09-01",
               "2015-11-01"],
    "ens4": ["2015-01-01", "2015-05-01", "2015-07-01", "2015-11-01"],
}


# ------------------------------------------------------------------------------------ specs
def normalise(spec: dict) -> dict:
    """Canonical spec: ``{router: {name, **overrides}, env: {...}, start, days, seed}`` with only
    non-default overrides; forecast-irrelevant fields dropped for hindsight / fixed routers."""
    name = spec["router"]["name"]
    if name not in ROUTER_DEFAULTS:
        raise ValueError(f"unknown router {name}")
    rd = ROUTER_DEFAULTS[name]
    ro = {k: v for k, v in spec["router"].items() if k != "name"}
    bad = set(ro) - set(rd)
    if bad:
        raise ValueError(f"router {name}: unknown overrides {sorted(bad)}")
    if name == "B0":
        ro = {}
    ro = {k: _num(v) for k, v in ro.items() if _num(v) != rd[k]}
    eo = {k: _num(v) for k, v in spec.get("env", {}).items()}
    bad = set(eo) - set(ENV_DEFAULTS)
    if bad:
        raise ValueError(f"unknown environment overrides {sorted(bad)}")
    eo = {k: v for k, v in eo.items() if v != ENV_DEFAULTS[k]}
    if name in SEED_FREE:
        for k in FORECAST_KEYS:
            eo.pop(k, None)
    seed = 0 if name in SEED_FREE else int(spec.get("seed", 1))
    return {"router": {"name": name, **dict(sorted(ro.items()))}, "env": dict(sorted(eo.items())),
            "start": str(spec["start"]), "days": float(spec.get("days", 30.0)), "seed": seed}


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def full_router(spec: dict) -> dict:
    n = spec["router"]["name"]
    return {**ROUTER_DEFAULTS[n], **{k: v for k, v in spec["router"].items() if k != "name"}}


def full_env(spec: dict) -> dict:
    return {**ENV_DEFAULTS, **spec["env"]}


def case_id(spec: dict) -> str:
    s = normalise(spec)
    ovr = "+".join([f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}"
                    for k, v in s["router"].items() if k != "name"]
                   + [f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}"
                      for k, v in s["env"].items()]) or "base"
    ovr = re.sub(r"[^A-Za-z0-9_.=+-]", "", ovr)[:70]
    h = hashlib.sha1(json.dumps(s, sort_keys=True).encode()).hexdigest()[:6]
    return f"{s['router']['name']}__{ovr}__{s['start']}_{s['days']:g}d__s{s['seed']}__{h}"


# ------------------------------------------------------------------------------------ campaign
def load_campaign(path) -> dict:
    import yaml
    return yaml.safe_load(open(path))


def _variants(exp: dict) -> list[dict]:
    """Variants of an experiment: ``[{name, router: {...}, env: {...}}]``."""
    out = []
    if "variants" in exp:
        for v in exp["variants"]:
            out.append({"name": v.get("name", "v"), "router": v.get("router", {}),
                        "env": v.get("env", {})})
    for key, vals in (exp.get("vary") or {}).items():
        kind, par = key.split(".", 1)
        for val in vals:
            out.append({"name": f"{par}={val:g}" if isinstance(val, float) else f"{par}={val}",
                        "router": {par: val} if kind == "router" else {},
                        "env": {par: val} if kind == "env" else {}})
    if not out:
        out.append({"name": "base", "router": {}, "env": {}})
    return out


def expand(camp: dict) -> list[dict]:
    """Expand a campaign into case records ordered by priority.

    Each record: ``{id, spec, tier, order, experiments: [exp ids]}`` (shared cases are merged:
    best tier, first order)."""
    wins = {**WINDOWS, **camp.get("windows", {})}
    dur = float(camp.get("duration_days", 30.0))
    tier_rank = {t: i for i, t in enumerate(camp.get("tiers", ["A", "B", "C", "D", "E"]))}
    cases: dict[str, dict] = {}
    order = 0
    for exp in camp["experiments"]:
        if exp.get("disabled"):
            continue
        for var in _variants(exp):
            routers = [(exp["router"], var["router"], exp.get("seeds", [1]))]
            if exp.get("oracle"):
                routers.append(("Oracle_REF_H", {}, [0]))
            if exp.get("b0"):
                routers.append(("B0", {}, [0]))
            for rname, rov, seeds in routers:
                for seed in seeds:
                    for w in wins[exp.get("windows", "bench6")]:
                        env = {**(camp.get("env_defaults") or {}), **var["env"]}
                        spec = normalise({"router": {"name": rname, **(rov if rname == exp["router"]
                                                                       else {})},
                                          "env": env, "start": w, "days": dur, "seed": seed})
                        cid = case_id(spec)
                        rec = cases.get(cid)
                        tr = tier_rank[exp.get("tier", "A")]
                        if rec is None:
                            cases[cid] = {"id": cid, "spec": spec, "tier": exp.get("tier", "A"),
                                          "_rank": tr, "order": order,
                                          "experiments": [exp["id"]]}
                            order += 1
                        else:
                            if exp["id"] not in rec["experiments"]:
                                rec["experiments"].append(exp["id"])
                            if tr < rec["_rank"]:
                                rec["_rank"], rec["tier"] = tr, exp.get("tier", "A")
    out = sorted(cases.values(), key=lambda r: (r["_rank"], r["order"]))
    for r in out:
        del r["_rank"]
    return out


def result_path(cid: str) -> Path:
    return RUNS / f"{cid}.json"


def is_done(cid: str) -> bool:
    return result_path(cid).exists()


# ------------------------------------------------------------------------------------ locks
def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # zombie
        return Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def claim(cid: str, pid: int | None = None) -> bool:
    """Take the per-case lock (O_EXCL). Stale locks (dead pid) are broken. True if acquired."""
    LOCKS.mkdir(parents=True, exist_ok=True)
    p = LOCKS / f"{cid}.lock"
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                d = json.loads(p.read_text())
                if pid_alive(int(d["pid"])):
                    return False
            except (OSError, ValueError, KeyError):
                time.sleep(0.2)
                if p.exists() and time.time() - p.stat().st_mtime < 5:
                    return False
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w") as fh:
            json.dump({"pid": pid or os.getpid(), "t": time.time()}, fh)
        return True
    return False


def set_lock_pid(cid: str, pid: int) -> None:
    (LOCKS / f"{cid}.lock").write_text(json.dumps({"pid": pid, "t": time.time()}))


def release(cid: str) -> None:
    try:
        (LOCKS / f"{cid}.lock").unlink()
    except FileNotFoundError:
        pass


def live_locks() -> dict[str, dict]:
    out = {}
    if LOCKS.exists():
        for p in LOCKS.glob("*.lock"):
            try:
                d = json.loads(p.read_text())
                if pid_alive(int(d["pid"])):
                    out[p.stem] = d
                else:  # stale lock of a dead worker (e.g. its master was killed): clean it
                    p.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError):
                pass
    return out


def atomic_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1, allow_nan=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def record_error(cid: str, msg: str) -> None:
    p = ERRS / f"{cid}.json"
    d = json.loads(p.read_text()) if p.exists() else {"attempts": 0, "log": []}
    d["attempts"] += 1
    d["log"] = (d["log"] + [{"t": time.strftime("%F %T"), "msg": msg[-1500:]}])[-5:]
    atomic_json(p, d)


def error_attempts(cid: str) -> int:
    p = ERRS / f"{cid}.json"
    try:
        return int(json.loads(p.read_text())["attempts"])
    except (OSError, ValueError, KeyError):
        return 0


# ------------------------------------------------------------------------------------ context
_CTX: dict = {}


def get_ctx(grid_km: float):
    """Shared per-process context (grid, ERA5 archive, coast, BETA polar) for a grid spacing."""
    if grid_km in _CTX:
        return _CTX[grid_km]
    import warnings

    import run_s3_backtest as R

    warnings.filterwarnings("ignore", category=UserWarning)
    if float(grid_km) == 40.0:
        ctx = R.Ctx()
    else:
        ctx = _build_ctx_other_dx(R, float(grid_km))
    _CTX[grid_km] = ctx
    return ctx


def _build_ctx_other_dx(R, dx_km: float):
    import fcntl

    from horizon.geo.coast import CoastModel, build_basin_coast, signed_distance
    from horizon.geo.grid import Grid
    from horizon.polar import hold_power_curve
    from horizon.polar.beta import load_beta_polar
    from horizon.polar.envelope import build_envelope
    from horizon.sim import DirectPowerModel, EnvelopePowerModel, FeasiblePowerModel
    from horizon.weather.era5 import ERA5_BOX, ERA5Archive

    class CtxDx(R.Ctx):
        def __init__(self):  # same construction as R.Ctx at another spacing
            self.grid = Grid.from_bbox(*ERA5_BOX, dx_km * 1e3)
            self.archive = ERA5Archive(R.ERA5_CACHE, self.grid, year=R.YEAR)
            LOCKS.mkdir(parents=True, exist_ok=True)
            with open(LOCKS / f"era5_cache_{dx_km:g}.flock", "w") as fh:  # one builder at a time
                fcntl.flock(fh, fcntl.LOCK_EX)
                self.archive.build_cache()
            self.outside = self.archive.outside
            c0 = build_basin_coast(dx_km * 1e3, bbox=ERA5_BOX)
            land = (c0.sdf < 0) | self.outside
            self.coast0 = c0
            self.coast = CoastModel(self.grid, signed_distance(self.grid, land))
            self.polar = load_beta_polar(R.POLAR_DIR)
            self.hold = hold_power_curve(self.polar)
            self.env = build_envelope(self.polar)
            self.pm = FeasiblePowerModel(
                EnvelopePowerModel(self.env, fallback=DirectPowerModel(self.polar, self.hold)))
            self._month_maps = {}

        def month_map(self, m):  # climatology cache files are per grid spacing
            if m not in self._month_maps:
                f = CACHE / f"hold_sum_dx{dx_km:g}_{R.YEAR}_{m:02d}.npz"
                if f.exists():
                    z = np.load(f)
                    self._month_maps[m] = (z["s"], int(z["n"]))
                else:
                    from horizon.polar.climatology import climatological_hold_power
                    from horizon.weather.fields import WindField
                    h0, h1 = int(self.archive._offset[m - 1]), int(self.archive._offset[m])
                    uv = self.archive.hours(h0, h1)[::3]
                    wf = WindField(self.grid, self.archive.start, np.arange(uv.shape[0]) * 10800.0,
                                   uv)
                    p = climatological_hold_power(wf, self.env).astype(np.float64)
                    CACHE.mkdir(parents=True, exist_ok=True)
                    np.savez(f, s=p * uv.shape[0], n=uv.shape[0])
                    self._month_maps[m] = (p * uv.shape[0], uv.shape[0])
            return self._month_maps[m]

    return CtxDx()


def start_point(ctx, env: dict):
    """(lon, lat) of the start and the coast model to use (port corridor for Lorient)."""
    from horizon.geo.coast import port_corridor
    from horizon.sim import best_climatological_point

    coast = ctx.coast
    s = env["start"]
    if s == "lorient":
        return LORIENT, port_corridor(coast, *LORIENT, ramp_m=40e3)
    if s == "mid_atlantic":
        return MID_ATLANTIC, coast
    if s != "offshore":
        return tuple(float(v) for v in str(s).split(",")), coast
    key = CACHE / f"offshore_start_dx{env['grid_km']:g}.json"
    if key.exists():
        return tuple(json.loads(key.read_text())), coast
    clim = ctx.clim_hold_kw(set())
    sxy = ctx.grid.to_xy(*__import__("run_s3_backtest").START)
    x, y, _ = best_climatological_point([], ctx.pm, ctx.coast, sxy, mean_kw=clim,
                                        extra_mask=~ctx.outside)
    ll = tuple(float(v) for v in ctx.grid.to_lonlat(x, y))
    atomic_json(key, list(ll))
    return ll, coast


# ------------------------------------------------------------------------------------ build
def build_environment(ctx, env: dict, seed: int, start_iso: str, days: float):
    """(weather, truth power model, manoeuvre model) of an environment config."""
    from horizon.sim import ManoeuvreModel
    from horizon.sim.truth_models import make_power_model
    from horizon.weather.forecast_model import ERA5ForecastWeather, ForecastErrorParams

    d = ENV_DEFAULTS
    if all(env[k] == d[k] for k in FORECAST_KEYS):
        params = ForecastErrorParams()
    else:
        params = ForecastErrorParams.with_knobs(
            error_scale=env["error_scale"], latency_h=env["latency_h"],
            consistency=env["consistency"], spread_factor=env["spread_factor"],
            season_amp=env["season_amp"])
        from dataclasses import replace
        params = replace(params, disp_scale=env["disp_scale"], amp_scale=env["amp_scale"],
                         noise_scale=env["noise_scale"], structure=env["structure"],
                         analog_scale=env["analog_scale"])
    epoch = np.datetime64(f"{start_iso}T00:00:00", "s")
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, days * 86400.0, params=params,
                             seed=seed, fast_filter=os.environ.get("HORIZON_FAST_FILTER") == "1")
    if env["truth_polar_scale"] == 1.0 and env["truth_polar_twa_shift"] == 0.0:
        pm = ctx.pm
    else:
        pm = make_power_model(ctx.polar, env["truth_polar_scale"], env["truth_polar_twa_shift"])
    man = ManoeuvreModel(enabled=bool(env["manoeuvre"]), tau_scale=env["tau_scale"],
                         rho=env["man_rho"], fixed_kwh=env["man_fixed_kwh"])
    return wx, pm, man


def build_router(ctx, spec: dict, wx, coast, start_xy):
    from horizon.config import make_policy
    from horizon.polar import hold_power_curve
    from horizon.sim import HoldAtPointPolicy
    from horizon.sim.truth_models import perturb_polar

    name = spec["router"]["name"]
    if name == "B0":
        return HoldAtPointPolicy(*start_xy)
    r, e = full_router(spec), full_env(spec)
    if name.startswith("GREEDY"):
        from horizon.sim.policies_simple import GreedyPolicy
        return GreedyPolicy(ctx.hold, coast, mode="hold24" if name.endswith("HOLD24") else
                            "maxwind", reach_h=r["reach_h"], window_h=r["window_h"],
                            d_min_m=e["d_min_km"] * 1e3, speed=r["speed"],
                            **({"tws_cap": r["tws_cap"]} if "tws_cap" in r else {}))
    pol = ctx.polar
    if r["router_polar"] == "truth":
        pol = perturb_polar(pol, e["truth_polar_scale"], e["truth_polar_twa_shift"])
    hold = hold_power_curve(pol) if pol is not ctx.polar else ctx.hold
    if r["storm_kn"] > 0:  # survival constraint as a steep penalty in the router's model
        from horizon.sim.policies_simple import storm_penalty_polar
        pol, hold = storm_penalty_polar(pol, hold, r["storm_kn"])
    return make_policy(router_config(name, r, e), pol, hold, coast,
                       ctx.clim_hold_kw(set()) if r["terminal"] == "clim" else None, weather=wx)


def router_config(name: str, r: dict, e: dict):
    """:class:`horizon.config.HorizonConfig` of a campaign router (full router / env dicts)."""
    from horizon.config import HorizonConfig
    kw = dict(horizon_days=r["horizon_days"], replan_h=r["replan_h"], refiner_h=r["refiner_h"],
              terminal=r["terminal"], terminal_days=r["terminal_days"],
              max_span=int(r["max_span"]), d_min_km=e["d_min_km"],
              router_polar=r["router_polar"], storm_kn=r["storm_kn"])
    if name == "Oracle_REF_H":
        return HorizonConfig(kind="ORACLE_H", **kw)
    if name == "ENS_REF":
        return HorizonConfig(kind="ENS", members=int(r["members"]), k=int(r["k"]),
                             gamma=r["gamma"], alpha=r["alpha"], **kw)
    if name == "B1m_5d_REF":
        return HorizonConfig(mean_members=int(r["members"]), blend_h=r["blend_h"], **kw)
    return HorizonConfig(**kw)


# ------------------------------------------------------------------------------------ run
def run_case(spec: dict, log=print, segment_s: float = 10 * 86400.0) -> dict:
    """Run one case (resumable through ``outputs/s5/ckpt/<id>``); returns the result dict."""
    from horizon.sim.longrun import run_persistent

    spec = normalise(spec)
    cid = case_id(spec)
    e, r = full_env(spec), full_router(spec)
    t_setup = time.perf_counter()
    ctx = get_ctx(e["grid_km"])
    dmin = e["d_min_km"] * 1e3
    start, coast = start_point(ctx, e)
    wx, pm, man = build_environment(ctx, e, spec["seed"], spec["start"], spec["days"])
    pol = build_router(ctx, spec, wx, coast, ctx.grid.to_xy(*start))
    pm.n_clamped = 0
    setup_s = time.perf_counter() - t_setup
    cpu0 = time.process_time()
    replan_s = r.get("replan_h", 6.0) * 3600.0
    out_dir = CKPT / cid
    res = run_persistent(pol, wx, start, pm, coast, out_dir, duration_s=spec["days"] * 86400.0,
                         replan_s=replan_s, d_min_m=dmin, segments=segment_s, tag=cid,
                         manoeuvre=man, log=lambda s: log(s))
    mr = res.result
    hours = sum(m.hours for m in res.segments)
    tot = {k: int(sum(getattr(m, f"n_{k}") for m in res.segments))
           for k in ("tack", "gybe", "turn")}
    out = {
        "id": cid, "status": "ok", "spec": spec, "start_lonlat": list(start),
        "cf_pct": 100.0 * res.energy_kwh / (3000.0 * hours), "energy_mwh": res.energy_kwh / 1e3,
        "hours": hours,
        "hold_share": float(sum(m.hold_share * m.hours for m in res.segments) / hours),
        "distance_km": float(sum(m.distance_km for m in res.segments)),
        "manoeuvres": {**tot, "total": sum(tot.values()),
                       "per_day": sum(tot.values()) / (hours / 24.0)},
        "storm35_h": float(sum(m.storm35_h for m in res.segments)),
        "storm45_h": float(sum(m.storm45_h for m in res.segments)),
        "mean_tws_ms": float(sum(m.mean_tws * m.hours for m in res.segments) / hours),
        "min_coast_margin_km": float(mr.min_margin_m) / 1e3,
        "guard_interventions": int(mr.guard_interventions),
        "coast_violations": int(mr.coast_violations), "n_replans": int(mr.n_replans),
        "n_dp_fallback": getattr(pol, "n_dp_fallback", None),
        "n_clamped": int(sum(m.n_clamped for m in res.segments)),  # also pre-resume segments
        "policy_stats": {k: int(getattr(pol, k)) for k in
                         ("n_refined", "n_warm_start", "n_not_converged", "n_hold_fallback")
                         if hasattr(pol, k)} or None,
        "resumed_from": res.resumed_from,
        "wall_s": setup_s + float(sum(m.wall_s for m in res.segments)),
        "cpu_s": time.process_time() - cpu0 + setup_s,
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        "segments": [{"label": m.label, "cf": m.capacity_factor} for m in res.segments],
        "finished": time.strftime("%F %T"),
        "versions": versions(),
    }
    atomic_json(result_path(cid), out)
    track_case(spec, out, log=log)
    return out


def versions() -> dict:
    """Code + data version tags of this process (see :mod:`horizon.tracking`)."""
    import run_s3_backtest as R

    from horizon.tracking import code_version, data_version
    return {**code_version(ROOT), **data_version(R.ERA5_CACHE, R.POLAR_DIR, R.YEAR)}


def track_case(spec: dict, out: dict, experiment: str = "S5-sensitivity", log=print,
               extra_tags: dict | None = None) -> str | None:
    """Record a finished case in MLflow (best effort: a tracking failure never fails a run)."""
    from horizon import tracking
    if not tracking.enabled():
        return None
    try:
        spec = normalise(spec)
        name = spec["router"]["name"]
        params = {**tracking.flatten("router", {"name": name, **full_router(spec)}),
                  **tracking.flatten("env", full_env(spec)),
                  "window.start": spec["start"], "window.days": str(spec["days"]),
                  "seed": str(spec["seed"])}
        tags = {**(out.get("versions") or versions()), "case_id": out["id"], "router": name,
                "window": spec["start"], "router_ovr": json.dumps(
                    {k: v for k, v in spec["router"].items() if k != "name"}, sort_keys=True),
                "env_ovr": json.dumps(spec["env"], sort_keys=True), **(extra_tags or {})}
        return tracking.log_result(experiment, out, params, tags, run_name=out["id"])
    except Exception as exc:  # noqa: BLE001 - tracking must never break a simulation
        log(f"tracking skipped: {exc!r}")
        return None


def main_run(spec: dict) -> int:
    """CLI body: skip if done, claim, run, record errors. Exit code 0 ok / 75 busy / 1 error."""
    spec = normalise(spec)
    cid = case_id(spec)
    if is_done(cid):
        print(f"{cid}: done (skipped)")
        return 0
    if os.environ.get("S5_CLAIMED") != "1" and not claim(cid):  # the queue master pre-claims
        print(f"{cid}: locked by a live worker")
        return 75
    try:
        t0 = time.perf_counter()
        out = run_case(spec, log=lambda s: print(time.strftime("%H:%M:%S"), s, flush=True))
        print(f"{cid}: CF {out['cf_pct']:.2f} % in {time.perf_counter() - t0:.0f} s", flush=True)
        return 0
    except BaseException:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr, flush=True)
        record_error(cid, tb)
        return 1
    finally:
        release(cid)


def copy_spec(spec):
    return copy.deepcopy(spec)
