"""Sprint-3 analysis: tables, paired comparisons, figures and inspector export from outputs/s3_runs.

Usage: ``python3 scripts/analyze_s3.py [--inspector-missions 2015-01-01 ...]``
Writes outputs/S3_results.json, docs/sprints/S3_results.md, outputs/S3_*.png and
outputs/s3_inspector/s3_era5.json.gz.
"""

# ruff: noqa: E501
import argparse
import json
import pickle
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_s3_backtest as R  # noqa: E402

from horizon.core.units import KNOT  # noqa: E402
from horizon.viz import SeedRun, export_backtest, save_export  # noqa: E402
from horizon.weather.forecast_model import ERA5ForecastWeather  # noqa: E402

ROOT = R.ROOT
ORDER = ["Oracle", "Oracle_REF", "B0", "B1_5d", "B1_5d_REF", "B1c_5d_REF", "ENS_g0", "ENS_g0_REF"]
COLORS = {
    "Oracle": "k",
    "Oracle_REF": "tab:purple",
    "B0": "0.5",
    "B1_5d": "tab:blue",
    "B1_5d_REF": "tab:cyan",
    "B1c_5d_REF": "tab:green",
    "ENS_g0": "tab:orange",
    "ENS_g0_REF": "tab:red",
}
COMPARISONS = [
    ("REF effect (B1_5d_REF - B1_5d)", "B1_5d_REF", "B1_5d"),
    ("Clim. terminal effect (B1c_5d_REF - B1_5d_REF)", "B1c_5d_REF", "B1_5d_REF"),
    ("E1 matched: ENS_g0_REF - B1c_5d_REF (both REF + clim terminal)", "ENS_g0_REF", "B1c_5d_REF"),
    ("E1: ENS_g0_REF - B1_5d_REF", "ENS_g0_REF", "B1_5d_REF"),
    ("E1 no REF: ENS_g0 - B1_5d", "ENS_g0", "B1_5d"),
    ("REF effect on ENS (ENS_g0_REF - ENS_g0)", "ENS_g0_REF", "ENS_g0"),
    ("B1 vs B0 (B1_5d - B0)", "B1_5d", "B0"),
    ("Best B1 vs B0 (B1_5d_REF - B0)", "B1_5d_REF", "B0"),
]


def load_runs():
    runs = {}
    for f in sorted(R.RUNS.glob("*.pkl")):
        d = pickle.load(open(f, "rb"))
        runs[(d["name"], d["date"])] = d
    return runs


def paired(J, a, b, dates):
    ds = [d for d in dates if (a, d) in J and (b, d) in J]
    if not ds:
        return None
    diff = np.array([J[(a, d)] - J[(b, d)] for d in ds]) / 1e3  # MWh
    rel = np.array([(J[(a, d)] - J[(b, d)]) / J[(b, d)] for d in ds]) * 100
    sd = float(diff.std(ddof=1)) if len(ds) > 1 else float("nan")
    return {
        "n": len(ds),
        "mean_mwh": float(diff.mean()),
        "std_mwh": sd,
        "t_stat": float(diff.mean() / (sd / np.sqrt(len(ds)))) if sd > 0 else float("nan"),
        "mean_pct_of_b": float(rel.mean()),
        "wins": int((diff > 0).sum()),
        "per_mission_mwh": {d: float(x) for d, x in zip(ds, diff, strict=True)},
    }


def era5_diag(ctx, date):
    epoch = np.datetime64(f"{date}T00:00:00", "s")
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, R.T, seed=0)
    tr = wx.truth(dt_s=3 * 3600.0)
    sea = (ctx.coast0.sdf > 0) & ~ctx.outside
    w = np.hypot(tr.uv[..., 0], tr.uv[..., 1])[:, sea]
    return {
        "mean_tws_ms": float(w.mean()),
        "mean_tws_kn": float(w.mean() / KNOT),
        "frac_18_26kn": float(((w >= 18 * KNOT) & (w <= 26 * KNOT)).mean()),
        "frac_gt35kn": float((w > 35 * KNOT).mean()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--inspector-missions",
        nargs="+",
        default=["2015-01-01", "2015-02-01", "2015-11-15", "2015-12-01"],
    )
    ap.add_argument("--track-mission", default="2015-01-01")
    ap.add_argument("--no-inspector", action="store_true")
    a = ap.parse_args()
    ctx = R.Ctx()
    runs = load_runs()
    dates = [d for d in R.MISSIONS if ("Oracle", d) in runs and ("Oracle_REF", d) in runs]
    pols = [p for p in ORDER if any((p, d) in runs for d in dates)]
    J = {k: v["metrics"]["energy_kwh"] for k, v in runs.items()}
    JH = {d: max(J[("Oracle", d)], J.get(("Oracle_REF", d), -np.inf)) for d in dates}
    out = {"missions": dates, "policies": pols, "per_mission": {}, "diagnostics": {}}
    for d in dates:
        row = {}
        for p in pols:
            r = runs.get((p, d))
            if r is None:
                continue
            m = r["metrics"]
            row[p] = {
                **m,
                "regret": 1 - m["energy_kwh"] / JH[d],
                "coast_violations": r["coast_violations"],
                "n_replans": r["n_replans"],
                "outside_steps": r["extra"]["outside_steps"],
                "min_sdf_km": r["extra"]["min_sdf_km"],
                "wrapped_requests": r["extra"]["wrapped_requests"],
                "clamped_power_steps": r["extra"].get("clamped_power_steps"),
                "wall_s": r["wall_s"],
            }
            if p == "B0":
                row[p]["b0_lonlat"] = r["extra"]["b0_lonlat"]
        out["per_mission"][d] = row
        out["diagnostics"][d] = era5_diag(ctx, d)
    summ = {}
    for p in pols:
        ds = [d for d in dates if p in out["per_mission"][d]]
        v = {
            k: np.array([out["per_mission"][d][p][k] for d in ds])
            for k in ("energy_kwh", "capacity_factor", "regret", "hold_fraction", "distance_km")
        }
        summ[p] = {"n": len(ds), "missions": ds}
        for k, x in v.items():
            summ[p][k] = {
                "mean": float(x.mean()),
                "std": float(x.std(ddof=1)) if len(ds) > 1 else float("nan"),
            }
    out["summary"] = summ
    # summary restricted to the missions common to all policies (fair mean when ENS reduced)
    common = [d for d in dates if all(p in out["per_mission"][d] for p in pols)]
    out["common_missions"] = common
    out["summary_common"] = (
        {
            p: {
                k: {
                    "mean": float(np.mean([out["per_mission"][d][p][k] for d in common])),
                    "std": float(np.std([out["per_mission"][d][p][k] for d in common], ddof=1)),
                }
                for k in ("energy_kwh", "capacity_factor", "regret")
            }
            for p in pols
        }
        if common
        else {}
    )
    out["paired"] = {name: paired(J, x, y, dates) for name, x, y in COMPARISONS}
    out["paired_winter6"] = {
        name: paired(J, x, y, [d for d in dates if d in R.WINTER6]) for name, x, y in COMPARISONS
    }
    out["checks"] = {
        "total_coast_violations": int(sum(r["coast_violations"] for r in runs.values())),
        "total_outside_steps": int(sum(r["extra"]["outside_steps"] for r in runs.values())),
        "min_sdf_km": float(min(r["extra"]["min_sdf_km"] for r in runs.values())),
        "total_wrapped_requests": int(sum(r["extra"]["wrapped_requests"] for r in runs.values())),
        "j_hind_mwh": {d: JH[d] / 1e3 for d in dates},
        "j_hind_is": {
            d: "Oracle_REF" if J.get(("Oracle_REF", d), -1) >= J[("Oracle", d)] else "Oracle"
            for d in dates
        },
        "max_causal_minus_j_hind_mwh": {
            d: max(
                (J[(p, d)] - JH[d]) / 1e3
                for p in pols
                if p not in ("Oracle", "Oracle_REF") and (p, d) in J
            )
            for d in dates
        },
        "oracle_ref_minus_oracle_mwh": {
            d: (J.get(("Oracle_REF", d), np.nan) - J[("Oracle", d)]) / 1e3 for d in dates
        },
        "wall_s_by_policy": {
            p: float(np.mean([r["wall_s"] for (n, _), r in runs.items() if n == p])) for p in pols
        },
        "members": sorted({r["members"] for (n, _), r in runs.items() if n.startswith("ENS")}),
    }
    pre = {}
    for f in sorted((R.RUNS / "pre_coastfix").glob("*.pkl")):
        d_ = pickle.load(open(f, "rb"))
        pre[(d_["name"], d_["date"])] = d_
    out["coastfix"] = {}
    for p_ in sorted({k[0] for k in pre}):
        ks = [k for k in pre if k[0] == p_ and k in runs]
        dl = np.array([(J[k] - pre[k]["metrics"]["energy_kwh"]) / 1e3 for k in ks])
        out["coastfix"][p_] = {
            "n": len(ks),
            "mean_delta_mwh": float(dl.mean()),
            "std_delta_mwh": float(dl.std(ddof=1)),
            "pre_violation_steps": int(sum(pre[k]["coast_violations"] for k in ks)),
            "pre_min_sdf_km": float(min(pre[k]["extra"]["min_sdf_km"] for k in ks)),
            "per_mission_mwh": {k[1]: float(x) for k, x in zip(ks, dl, strict=True)},
        }
    out["checks"]["violation_steps_by_policy"] = {
        p_: int(sum(r["coast_violations"] for (n_, _), r in runs.items() if n_ == p_)) for p_ in pols
    }
    out["checks"]["min_sdf_km_by_policy"] = {
        p_: float(min(r["extra"]["min_sdf_km"] for (n_, _), r in runs.items() if n_ == p_))
        for p_ in pols
    }
    (ROOT / "outputs" / "S3_results.json").write_text(json.dumps(out, indent=1))
    write_md(out)
    figures(ctx, runs, out, a.track_mission)
    if not a.no_inspector:
        inspector(ctx, runs, [d for d in a.inspector_missions if d in dates])
    print("done")


def _fmt(x, f=".1f"):
    return format(x, f)


NOTES = """### Method notes and anomalies

* **Runtime / reductions.** Two workers on 2 cores, ~2.2 h wall. Per-replan timing (single core, 40 km
  grid): B1_5d 0.5 s, B1+REF 1.8 s, ENS (10 members, k 5, 10 d) 4.3 s, ENS+REF 5.5 s. Full 10 x 7 would have
  exceeded the ~3.5 h budget, so the two ENS policies were run on the 6 winter missions only (Jan 1,
  Jan 15, Feb 1, Feb 15, Nov 15, Dec 1); members stayed at 10 (second reduction not needed).
  Means "common 6 missions" compare all policies on the same missions.
* **Domain.** ERA5-box-outside cells merged into the SDF as land (d_min 20 km applies from the box edge);
  zero time spent in outside cells (checked on every track).
* **Wrap.** Dec 1 + 30 d ends 31 Dec 00 UTC, inside the data; horizons are truncated at mission end, so
  no request went beyond the data (`wrapped_requests` = 0 everywhere).
* **B0.** Best cell of the mean hold power (envelope reward at v = 0, 3-hourly samples) over the 2015 months
  NOT touched by the mission (start and end month excluded), SDF >= 50 km, inside the ERA5 box, <= 800 NM
  from the start. Mild leakage remains: climatology comes from the same year (neighbouring months are
  autocorrelated) and the truth of the other months is partly "future" for Jan-Mar missions.
* **Terminal value (B1c, ENS).** V_T = P_clim(x) * min(5 d, mission time left after the window), P_clim
  from the same excluded-month climatology; B1_5d / B1_5d_REF have zero terminal value.
* **Forecasts** are the hypothesised ERA5 error model (exchangeable ensemble), not real NWP.
* **Power model.** The BETA envelope has holes (e.g. fast upwind): the refiner occasionally commands a
  velocity with undefined power (NaN). `FeasiblePowerModel` evaluates such samples at a slightly reduced
  ground speed (4 samples in one run, B1c Jan 1; kinematics unchanged).
* **Hindsight reference.** The 3 h DP Oracle was beaten by REF policies; regrets are therefore computed
  against J_hind = max(Oracle, Oracle_REF) per mission (Oracle_REF = DP on truth to mission end + 48 h
  refinement on truth at every 6 h replan). See `checks.max_causal_minus_j_hind_mwh` (<= 0 means no causal
  policy beats J_hind).
* **Coast-margin fix (post-S3).** The refiner now enforces SDF >= d_min + 2 km at nodes, quarter points and
  mid-points and the DP arc check samples every <= dx/8. B1_5d_REF, B1c_5d_REF and ENS_g0_REF were re-run after the fix (old results kept in
  `outputs/s3_runs/pre_coastfix`, see table above); B0, B1_5d and the DP Oracle are unaffected by the refiner
  but were run with the old DP arc sampling; regression tests in
  `tests/test_refine.py`.
* **Coast.** No track enters land or the outside region. Strict-SDF violations (< 20 km) come from DP
  macro arcs cutting corners (min 19.75 km, Oracle too) and from the refiner (down to 17.0 km:
  B1_5d_REF Nov 1; 17.95 km ENS_g0_REF Jan 1; 18.5 km B1_5d_REF Mar 1).
* **B1c Oct 1** (-112 MWh vs B1_5d_REF): the climatological terminal value pulled the ship north
  (Norwegian Sea) into a calm spell; the terminal effect is positive on average but noisy.
"""


def write_md(o):
    pols, dates = o["policies"], o["missions"]
    L = [
        "# Sprint 3 results: real ERA5 truth (2015), BETA polar, ERA5-error-model forecasts",
        "",
        "Generated by `scripts/analyze_s3.py` from `outputs/s3_runs` (`outputs/S3_results.json`).",
        "Setup: 40 km grid, d_min 20 km, ERA5-box-outside cells = land, BETA polar",
        "(holes repaired, VPP-bug mask),",
        "start 47.0N 6.5W, 30 d missions, replan 6 h, DP 3 h (max_span 2). Forecasts: exchangeable",
        "ERA5-error",
        "ensemble (`ERA5ForecastWeather`, hypothesised error law, NOT real forecasts).",
        "",
    ]
    for title, key, sc, f in (
        ("Net energy J [MWh]", "energy_kwh", 1e-3, ".1f"),
        ("Capacity factor [-]", "capacity_factor", 1, ".3f"),
        ("Regret vs J_hind = max(Oracle, Oracle_REF) [%]", "regret", 100, ".1f"),
    ):
        L += [
            f"### {title}",
            "",
            "| Mission | " + " | ".join(pols) + " |",
            "|---|" + "---|" * len(pols),
        ]
        for d in dates:
            r = o["per_mission"][d]
            L.append(
                f"| {d} | "
                + " | ".join(format(r[p][key] * sc, f) if p in r else "-" for p in pols)
                + " |"
            )
        L.append(
            "| **mean +- std** | "
            + " | ".join(
                f"{o['summary'][p][key]['mean'] * sc:{f}} +- {o['summary'][p][key]['std'] * sc:{f}}"
                for p in pols
            )
            + " |"
        )
        if o["common_missions"] and len(o["common_missions"]) != len(dates):
            L.append(
                f"| mean +- std (common {len(o['common_missions'])} missions) | "
                + " | ".join(
                    f"{o['summary_common'][p][key]['mean'] * sc:{f}} +- "
                    f"{o['summary_common'][p][key]['std'] * sc:{f}}"
                    for p in pols
                )
                + " |"
            )
        L.append("")
    L += [
        "### Paired comparisons (J difference [MWh], positive = first policy better)",
        "",
        "| Comparison | n | mean diff | std | t | mean % of reference | wins |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, v in o["paired"].items():
        if v:
            L.append(
                f"| {name} | {v['n']} | {v['mean_mwh']:+.1f} | {v['std_mwh']:.1f} | "
                f"{v['t_stat']:+.1f} | {v['mean_pct_of_b']:+.2f} % | {v['wins']}/{v['n']} |"
            )
    L += [
        "",
        "Winter-6 subset (Jan 1, Jan 15, Feb 1, Feb 15, Nov 15, Dec 1):",
        "",
        "| Comparison | n | mean diff | std | t | mean % | wins |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, v in o["paired_winter6"].items():
        if v:
            L.append(
                f"| {name} | {v['n']} | {v['mean_mwh']:+.1f} | {v['std_mwh']:.1f} | "
                f"{v['t_stat']:+.1f} | {v['mean_pct_of_b']:+.2f} % | {v['wins']}/{v['n']} |"
            )
    L += [
        "",
        "### ERA5 diagnostics per mission (sea cells inside the ERA5 box, 3-hourly)",
        "",
        "| Mission | mean TWS [m/s] | mean TWS [kn] | share 18-26 kn | share >35 kn |",
        "|---|---|---|---|---|",
    ]
    for d in dates:
        g = o["diagnostics"][d]
        L.append(
            f"| {d} | {g['mean_tws_ms']:.2f} | {g['mean_tws_kn']:.1f} | "
            f"{100 * g['frac_18_26kn']:.1f} % | {100 * g['frac_gt35kn']:.2f} % |"
        )
    L += ["", "### Checks", "", f"```\n{json.dumps(o['checks'], indent=1)}\n```", ""]
    L += [
        "### Hold fraction / distance (mean over missions)",
        "",
        "| Policy | hold fraction | distance [km] |",
        "|---|---|---|",
    ]
    for p in pols:
        s = o["summary"][p]
        L.append(f"| {p} | {s['hold_fraction']['mean']:.2f} | {s['distance_km']['mean']:.0f} |")
    L.append("")
    L += ["### Pre/post coast-fix (REF policies re-run with SDF >= d_min + 2 km, quarter-point sampling)", "",
          "| Policy | n | mean delta J [MWh] (post - pre) | std | pre violation steps | pre min SDF [km] |",
          "|---|---|---|---|---|---|"]
    for p_, v in o["coastfix"].items():
        L.append(f"| {p_} | {v['n']} | {v['mean_delta_mwh']:+.1f} | {v['std_delta_mwh']:.1f} | "
                 f"{v['pre_violation_steps']} | {v['pre_min_sdf_km']:.2f} |")
    L.append("")
    L.append(NOTES)
    (ROOT / "docs" / "sprints" / "S3_results.md").write_text("\n".join(L))


def figures(ctx, runs, o, track_date):
    g = ctx.grid
    ext = [
        g.x0 / 1e3,
        (g.x0 + g.dx * (g.nx - 1)) / 1e3,
        g.y0 / 1e3,
        (g.y0 + g.dx * (g.ny - 1)) / 1e3,
    ]
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.imshow(
        np.where(ctx.coast0.sdf < 0, 0.75, 1.0),
        origin="lower",
        extent=ext,
        cmap="gray",
        vmin=0,
        vmax=1,
    )
    ax.imshow(
        np.where(ctx.outside, 0.5, np.nan),
        origin="lower",
        extent=ext,
        cmap="Reds",
        vmin=0,
        vmax=1,
        alpha=0.35,
    )
    ax.contour(
        np.linspace(ext[0], ext[1], g.nx),
        np.linspace(ext[2], ext[3], g.ny),
        ctx.coast.sdf,
        levels=[20e3],
        colors="0.3",
        linewidths=0.6,
    )
    for p in o["policies"]:
        r = runs.get((p, track_date))
        if r is None:
            continue
        ax.plot(
            r["res"].x / 1e3,
            r["res"].y / 1e3,
            color=COLORS[p],
            lw=1.4 if p not in ("Oracle", "Oracle_REF") else 2.2,
            label=f"{p} ({r['metrics']['energy_kwh'] / 1e3:.0f} MWh)",
            alpha=0.9,
        )
    sx, sy = g.to_xy(*R.START)
    ax.plot(sx / 1e3, sy / 1e3, "k*", ms=12)
    ax.set_title(f"S3 tracks, mission {track_date} (red = outside ERA5 box, treated as land)")
    ax.set_xlabel("x [km]"), ax.set_ylabel("y [km]")
    # zoom on the region visited
    xs = np.concatenate(
        [runs[(p, track_date)]["res"].x for p in o["policies"] if (p, track_date) in runs]
    )
    ys = np.concatenate(
        [runs[(p, track_date)]["res"].y for p in o["policies"] if (p, track_date) in runs]
    )
    ax.set_xlim(xs.min() / 1e3 - 300, xs.max() / 1e3 + 300)
    ax.set_ylim(ys.min() / 1e3 - 300, ys.max() / 1e3 + 300)
    ax.legend(loc="best", fontsize=8)
    ax.set_aspect("equal")
    fig.savefig(ROOT / "outputs" / "S3_trajectories.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    # zoom: 5-day window of the same mission (staircase check)
    fig, ax = plt.subplots(figsize=(9, 9))
    t0, t1 = 8 * 86400.0, 13 * 86400.0
    allx, ally = [], []
    for p in ("Oracle", "Oracle_REF", "B1_5d_REF", "ENS_g0_REF"):
        r = runs.get((p, track_date))
        if r is None:
            continue
        res = r["res"]
        m = (res.t_s >= t0) & (res.t_s <= t1)
        ax.plot(res.x[m] / 1e3, res.y[m] / 1e3, color=COLORS[p], lw=1.5, label=p)
        mk = m & (np.abs(res.t_s % 86400.0) < 1)
        ax.plot(res.x[mk] / 1e3, res.y[mk] / 1e3, ".", color=COLORS[p], ms=7)
        allx.append(res.x[m]), ally.append(res.y[m])
    ax.set_xlim(np.concatenate(allx).min() / 1e3 - 30, np.concatenate(allx).max() / 1e3 + 30)
    ax.set_ylim(np.concatenate(ally).min() / 1e3 - 30, np.concatenate(ally).max() / 1e3 + 30)
    ax.set_aspect("equal")
    ax.set_title(f"S3 tracks, days 8-13 of {track_date} (dots = daily marks)")
    ax.legend(fontsize=8)
    ax.set_xlabel("x [km]"), ax.set_ylabel("y [km]")
    fig.savefig(ROOT / "outputs" / "S3_trajectories_zoom.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    # regret bars
    dates = o["missions"]
    pp = [p for p in o["policies"] if p not in ("Oracle", "Oracle_REF")]
    fig, ax = plt.subplots(figsize=(13, 5))
    wdt = 0.8 / len(pp)
    for k, p in enumerate(pp):
        v = [
            100 * o["per_mission"][d][p]["regret"] if p in o["per_mission"][d] else np.nan
            for d in dates
        ]
        ax.bar(np.arange(len(dates)) + k * wdt, v, wdt, color=COLORS[p], label=p)
    ax.set_xticks(np.arange(len(dates)) + 0.4 - wdt / 2, [d[5:] for d in dates])
    ax.set_ylabel("regret vs Oracle [%]")
    ax.set_title("S3 regret by mission")
    ax.legend(ncol=3, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.savefig(ROOT / "outputs" / "S3_regret_bars.png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    # mean regret bars
    fig, ax = plt.subplots(figsize=(7, 4))
    m = [100 * o["summary"][p]["regret"]["mean"] for p in pp]
    s = [100 * o["summary"][p]["regret"]["std"] for p in pp]
    ax.bar(pp, m, yerr=s, color=[COLORS[p] for p in pp], capsize=3)
    ax.set_ylabel("mean regret [%] +- std")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.savefig(ROOT / "outputs" / "S3_regret_mean.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def inspector(ctx, runs, dates):
    seed_runs = []
    for d in dates:
        epoch = np.datetime64(f"{d}T00:00:00", "s")
        wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, R.T, seed=R.mission_id(d))
        truth = wx.truth(dt_s=3600.0)
        res = {p: runs[(p, d)]["res"] for p in ORDER if (p, d) in runs}
        rec = {p: runs[(p, d)]["records"] for p in res}
        seed_runs.append(SeedRun(R.mission_id(d), truth, res, wx, rec, label=d[:7] + " " + d[5:]))
    info = {
        "Oracle": {"label": "Oracle (hindsight DP)"},
        "Oracle_REF": {"label": "Oracle + refiner (hindsight)"},
        "B0": {"label": "B0 best fixed point"},
        "B1_5d": {"label": "B1 5 d DP"},
        "B1_5d_REF": {"label": "B1 5 d + refiner"},
        "B1c_5d_REF": {"label": "B1 5 d + refiner + clim terminal"},
        "ENS_g0": {"label": "ENS 10 d (g=0)"},
        "ENS_g0_REF": {"label": "ENS 10 d + refiner"},
    }
    data = export_backtest(
        seed_runs,
        ctx.coast,
        title="HORIZON S3 - ERA5 2015 inspector",
        start_lonlat=R.START,
        policy_info=info,
        reference="Oracle_REF",
        params={
            "grid_km": 40,
            "replan_h": 6,
            "polar": "BETA",
            "members": 10,
            "forecasts": "ERA5 error model (hypothesised)",
        },
        polar=ctx.polar,
        weather_kind="era5",
        era5_mask=~ctx.outside,
        forecast_error=True,
    )
    path = ROOT / "outputs" / "s3_inspector" / "s3_era5.json.gz"
    save_export(data, path)
    print("inspector export", path, f"{path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
