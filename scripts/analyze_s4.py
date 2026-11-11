# ruff: noqa: E501
"""Sprint-4 analysis: Experiment A (median fleet ship, 2015) and B (Lorient departures).

Reads outputs/s4_runs/{A_*,B_*} (checkpoint directories, see horizon.sim.longrun) and writes
outputs/S4_results.json, docs/sprints/S4_results.md and outputs/S4_*.png. Client data stays local.
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import run_s3_backtest as R  # noqa: E402

from horizon.core.units import KNOT  # noqa: E402
from horizon.sim.simulator import sample_wind  # noqa: E402
from horizon.weather.forecast_model import ERA5ForecastWeather  # noqa: E402

RUNS = ROOT / "outputs/s4_runs"
MONTHS = [f"2015-{m:02d}" for m in range(1, 13)]
MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
P_RATED = 3000.0
DT = 900.0
# name -> (directory, label)
A = {
    "Oracle_REF_H": ("A_OracleH", "Oracle_REF_H"),
    "B0": ("A_B0", "B0"),
    "B1_5d_REF s1": ("A_B1_REF_s1", "B1_5d_REF"),
    "B1c_5d_REF s1": ("A_B1c_REF_s1", "B1c_5d_REF s1"),
    "B1c_5d_REF s2": ("A_B1c_REF_s2", "B1c_5d_REF s2"),
    "ENS_REF s1": ("A_ENS_REF_s1", "ENS_REF s1"),
    "ENS_REF s2": ("A_ENS_REF_s2", "ENS_REF s2"),
}
COL = {"Oracle_REF_H": "#222222", "B0": "#999999", "B1_5d_REF s1": "#1b9e77",
       "B1c_5d_REF s1": "#d95f02", "B1c_5d_REF s2": "#e6ab02", "ENS_REF s1": "#7570b3",
       "ENS_REF s2": "#a6a0d6"}


def load_run(d: Path):
    """dict with per-month metrics and the concatenated per-step arrays; None if absent."""
    if not (d / "meta.json").exists():
        return None
    meta = json.loads((d / "meta.json").read_text())
    nb = len(meta["bounds"]) - 1
    segs = []
    for k in range(nb):
        if not (d / f"seg_{k:04d}.json").exists():
            break
        segs.append(json.loads((d / f"seg_{k:04d}.json").read_text()))
    if not segs:
        return None
    zs = [np.load(d / f"seg_{k:04d}.npz") for k in range(len(segs))]
    return {"meta": meta, "metrics": [s["metrics"] for s in segs], "n_seg": len(segs),
            "complete": len(segs) == nb, "bounds": meta["bounds"],
            "x": [z["x"] for z in zs], "y": [z["y"] for z in zs],
            "p": [z["power_kw"] for z in zs],
            "state": segs[-1]["state"],
            "info": json.loads((d / "run_info.json").read_text())
            if (d / "run_info.json").exists() else None}


def paired(a, b, scale=1.0):
    """Monthly paired difference a - b (arrays [MWh], NaN-aware)."""
    ok = np.isfinite(a) & np.isfinite(b)
    d = (a - b)[ok]
    if d.size == 0:
        return None
    sd = float(d.std(ddof=1)) if d.size > 1 else float("nan")
    return {"n": int(d.size), "mean_mwh_per_month": float(d.mean()),
            "sum_mwh": float(d.sum()), "std": sd,
            "t": float(d.mean() / (sd / np.sqrt(d.size))) if sd > 0 else float("nan"),
            "mean_pct_of_b": float(np.mean(d / b[ok]) * 100), "wins": int((d > 0).sum()),
            "per_month_mwh": [float(x) if np.isfinite(x) else None for x in (a - b)]}


def main():
    warnings.filterwarnings("ignore", category=UserWarning)
    ctx = R.Ctx()
    base_coast = ctx.coast  # unmodified (no corridor)
    runs = {k: load_run(RUNS / v[0]) for k, v in A.items()}
    runs = {k: v for k, v in runs.items() if v is not None}
    E = {k: np.full(12, np.nan) for k in runs}
    CF = {k: np.full(12, np.nan) for k in runs}
    HOLD = {k: np.full(12, np.nan) for k in runs}
    GUARD = {}
    for k, r in runs.items():
        for i, m in enumerate(r["metrics"]):
            E[k][i] = m["energy_kwh"] / 1e3
            CF[k][i] = m["capacity_factor"]
            HOLD[k][i] = m["hold_share"]
        GUARD[k] = int(r["state"]["guard_interventions"])
    for k, r in runs.items():
        if r["n_seg"] < 12:
            print("partial:", k, r["n_seg"], "months")
    ref = "Oracle_REF_H"
    done = {k: int(np.isfinite(E[k]).sum()) for k in E}

    def annual(k):
        ok = np.isfinite(E[k])
        h = np.array([runs[k]["metrics"][i]["hours"] for i in range(ok.sum())])
        return float(E[k][ok].sum()), float(E[k][ok].sum() * 1e3 / (P_RATED * h.sum()))

    ann = {k: annual(k) for k in runs}
    regret_m = {k: (E[ref] - E[k]) / E[ref] * 100 for k in runs} if ref in runs else {}
    regret_a = {}
    for k in runs:
        ok = np.isfinite(E[k]) & np.isfinite(E[ref])
        regret_a[k] = float((E[ref][ok].sum() - E[k][ok].sum()) / E[ref][ok].sum() * 100)

    # ------------------------------------------------------------- ERA5 + experienced diagnostics
    sea = (ctx.coast0.sdf > 0) & ~ctx.outside
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, np.datetime64("2015-01-01T00:00:00", "s"),
                             365 * 86400.0, seed=0)
    basin = {"mean_tws_kn": [], "share_18_26": []}
    exp_tws = {k: np.full(12, np.nan) for k in runs}
    exp_share = {k: np.full(12, np.nan) for k in runs}
    bnd = next(iter(runs.values()))["bounds"]
    for mi in range(12):
        a, b = bnd[mi] * DT, bnd[mi + 1] * DT
        tr = wx.truth(dt_s=3600.0, start_s=float(a), end_s=float(b + 3600.0))
        w = np.hypot(tr.uv[::3, ..., 0], tr.uv[::3, ..., 1])[:, sea]
        basin["mean_tws_kn"].append(float(w.mean() / KNOT))
        basin["share_18_26"].append(float(((w >= 18 * KNOT) & (w <= 26 * KNOT)).mean()))
        for k, r in runs.items():
            if mi >= r["n_seg"]:
                continue
            x, y = r["x"][mi], r["y"][mi]
            t = a + DT * np.arange(x.size) + 0.5 * DT
            xm = np.append(x, x[-1])
            ym = np.append(y, y[-1])
            u, v = sample_wind(tr, t, 0.5 * (xm[:-1] + xm[1:]), 0.5 * (ym[:-1] + ym[1:]))
            s = np.hypot(u, v) / KNOT
            exp_tws[k][mi] = float(s.mean())
            exp_share[k][mi] = float(((s >= 18) & (s <= 26)).mean())
        del tr
    print("diagnostics done", flush=True)

    # ------------------------------------------------------------------------- comparisons
    def key(name):
        return E.get(name, np.full(12, np.nan))

    comps = {}
    pairs = [
        ("ENS_REF s1 - B1c_5d_REF s1", "ENS_REF s1", "B1c_5d_REF s1"),
        ("ENS_REF s2 - B1c_5d_REF s2", "ENS_REF s2", "B1c_5d_REF s2"),
        ("Clim. terminal effect (B1c s1 - B1 s1)", "B1c_5d_REF s1", "B1_5d_REF s1"),
        ("Routing vs B0 (B1c s1 - B0)", "B1c_5d_REF s1", "B0"),
        ("Routing vs B0 (B1 s1 - B0)", "B1_5d_REF s1", "B0"),
        ("Routing vs B0 (ENS s1 - B0)", "ENS_REF s1", "B0"),
        ("Seed effect (B1c s2 - B1c s1)", "B1c_5d_REF s2", "B1c_5d_REF s1"),
        ("Seed effect (ENS s2 - ENS s1)", "ENS_REF s2", "ENS_REF s1"),
        ("Hindsight - B1c s1", "Oracle_REF_H", "B1c_5d_REF s1"),
    ]
    for lab, x, y in pairs:
        if x in runs and y in runs:
            p = paired(key(x), key(y))
            if p:
                comps[lab] = p

    seed_spread = {}
    for pol in ("B1c_5d_REF", "ENS_REF"):
        k1, k2 = f"{pol} s1", f"{pol} s2"
        if k1 in runs and k2 in runs:
            ok = np.isfinite(E[k1]) & np.isfinite(E[k2])
            d = (E[k2] - E[k1])[ok]
            seed_spread[pol] = {"n_months": int(ok.sum()),
                                "annual_mwh": [float(E[k1][ok].sum()), float(E[k2][ok].sum())],
                                "annual_diff_mwh": float(d.sum()),
                                "annual_diff_pct": float(d.sum() / E[k1][ok].sum() * 100),
                                "monthly_std_mwh": float(d.std(ddof=1)) if d.size > 1 else None,
                                "monthly_abs_max_mwh": float(np.abs(d).max())}

    # ------------------------------------------------------------------------- safety
    safety = {}
    for k, r in runs.items():
        info = r["info"] or {}
        safety[k] = {"guard_interventions": GUARD[k],
                     "coast_violations": info.get("coast_violations"),
                     "min_margin_km": info.get("min_margin_km", r["state"]["min_margin_m"] / 1e3),
                     "n_dp_fallback": info.get("n_dp_fallback"),
                     "wall_h": (sum(m["wall_s"] for m in r["metrics"]) / 3600.0),
                     "n_clamped": int(sum(m["n_clamped"] for m in r["metrics"]))}

    # ------------------------------------------------------------------ Experiment B (Lorient)
    B = {"months": [], "ok": False}
    sdf0 = base_coast.sdf_at
    for mi, mo in enumerate(MONTHS):
        rb = load_run(RUNS / f"B_B1c_{mo[5:]}")
        ro = load_run(RUNS / f"B_OH_{mo[5:]}")
        if rb is None or ro is None or not rb["complete"] or not ro["complete"]:
            continue
        n14 = 14 * 96
        row = {"month": mo}
        for tag, rr, ka in (("B1c", rb, "B1c_5d_REF s1"), ("OH", ro, "Oracle_REF_H")):
            p = rr["p"][0][:n14]
            row[f"{tag}_cf"] = float(p.mean() / P_RATED)
            row[f"{tag}_mwh"] = float(p.sum() * DT / 3600 / 1e3)
            if ka in runs and mi < runs[ka]["n_seg"]:
                pa = runs[ka]["p"][mi][:n14]
                row[f"{tag}_A_cf"] = float(pa.mean() / P_RATED)
            d_km = sdf0(rr["x"][0][:n14], rr["y"][0][:n14]) / 1e3
            for thr in (50, 100):
                i = np.nonzero(d_km >= thr)[0]
                row[f"{tag}_t_sdf{thr}km_h"] = float(i[0] * DT / 3600) if i.size else None
            ref_p = row.get(f"{tag}_A_cf", np.nan) * P_RATED
            run6 = np.convolve(p, np.ones(24) / 24, mode="valid")  # 6 h running mean
            j = np.nonzero(run6 >= 0.9 * ref_p)[0] if np.isfinite(ref_p) else []
            row[f"{tag}_t_productive_h"] = float((j[0] + 24) * DT / 3600) if len(j) else None
            row[f"{tag}_cf_day1_3"] = float(p[:288].mean() / P_RATED)
        B["months"].append(row)
    B["ok"] = bool(B["months"])

    out = {
        "months": MONTHS, "done_months": done,
        "energy_mwh": {k: [None if not np.isfinite(v) else float(v) for v in E[k]] for k in runs},
        "cf": {k: [None if not np.isfinite(v) else float(v) for v in CF[k]] for k in runs},
        "hold_share": {k: [None if not np.isfinite(v) else float(v) for v in HOLD[k]]
                       for k in runs},
        "annual": {k: {"energy_mwh": ann[k][0], "cf": ann[k][1], "regret_pct": regret_a.get(k)}
                   for k in runs},
        "regret_monthly_pct": {k: [None if not np.isfinite(v) else float(v) for v in regret_m[k]]
                               for k in regret_m},
        "comparisons": comps, "seed_spread": seed_spread, "safety": safety,
        "basin_tws_kn": basin["mean_tws_kn"], "basin_share_18_26": basin["share_18_26"],
        "ship_tws_kn": {k: [None if not np.isfinite(v) else float(v) for v in exp_tws[k]]
                        for k in runs},
        "ship_share_18_26": {k: [None if not np.isfinite(v) else float(v) for v in exp_share[k]]
                             for k in runs},
        "lorient": B,
        "start_lonlat": runs[next(iter(runs))]["meta"]["start_lonlat"],
    }
    (ROOT / "outputs/S4_results.json").write_text(json.dumps(out, indent=1))
    figures(out, runs, CF, E, regret_m, exp_tws, basin)
    write_md(out)
    print("written")


# ===================================================================================== figures
def figures(o, runs, CF, E, regret_m, exp_tws, basin):
    x = np.arange(12)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    # 1 monthly CF
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 1.3]})
    for k in runs:
        a1.plot(x, CF[k], "-o", ms=3, color=COL[k], label=k, lw=1.6 if "s2" not in k else 1.0,
                ls="-" if "s2" not in k else "--")
    a1.set_ylabel("capacity factor")
    a1.set_title("Median fleet ship, 2015: monthly capacity factor")
    a1.legend(ncol=2, frameon=False, fontsize=8)
    a1.grid(alpha=0.25)
    a2.bar(x - 0.2, basin["mean_tws_kn"], 0.4, color="#5b8fb9", label="basin mean TWS [kn]")
    a2b = a2.twinx()
    a2b.bar(x + 0.2, np.array(basin["share_18_26"]) * 100, 0.4, color="#c9a227",
            label="share 18-26 kn [%]")
    a2.set_ylabel("mean TWS [kn]")
    a2b.set_ylabel("share 18-26 kn [%]")
    a2.set_xticks(x, MN)
    h1, l1 = a2.get_legend_handles_labels()
    h2, l2 = a2b.get_legend_handles_labels()
    a2.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper right", ncol=2)
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/S4_monthly_cf.png", dpi=140)
    plt.close(fig)
    # 2 regret
    fig, ax = plt.subplots(figsize=(9, 4))
    ks = [k for k in runs if k != "Oracle_REF_H" and k != "B0"]
    w = 0.8 / max(len(ks), 1)
    for i, k in enumerate(ks):
        ax.bar(x - 0.4 + w * (i + 0.5), regret_m[k], w, color=COL[k], label=k)
    ax.set_xticks(x, MN)
    ax.set_ylabel("regret vs Oracle_REF_H [%]")
    ax.set_title("Monthly regret vs hindsight (approximate bound)")
    ax.legend(frameon=False, fontsize=8, ncol=3)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/S4_regret_monthly.png", dpi=140)
    plt.close(fig)
    # 3 annual + seeds
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    ks = list(runs)
    a1.bar(range(len(ks)), [o["annual"][k]["cf"] for k in ks], color=[COL[k] for k in ks])
    a1.set_xticks(range(len(ks)), ks, rotation=35, ha="right")
    a1.set_ylabel("annual capacity factor")
    a1.set_ylim(0.5, 1.0)
    a1.set_title("Annual CF")
    kr = [k for k in ks if o["annual"][k]["regret_pct"] is not None and k != "Oracle_REF_H"]
    a2.bar(range(len(kr)), [o["annual"][k]["regret_pct"] for k in kr], color=[COL[k] for k in kr])
    a2.set_xticks(range(len(kr)), kr, rotation=35, ha="right")
    a2.set_ylabel("annual regret [%]")
    a2.set_title("Annual regret vs Oracle_REF_H")
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/S4_annual.png", dpi=140)
    plt.close(fig)
    # 4 paired
    fig, ax = plt.subplots(figsize=(9, 4))
    items = [("ENS_REF s1 - B1c_5d_REF s1", "ENS - B1c"),
             ("Clim. terminal effect (B1c s1 - B1 s1)", "B1c - B1"),
             ("Seed effect (B1c s2 - B1c s1)", "B1c seed2 - seed1")]
    items = [(a, b) for a, b in items if a in o["comparisons"]]
    w = 0.8 / max(len(items), 1)
    for i, (k, lab) in enumerate(items):
        d = np.array([np.nan if v is None else v for v in o["comparisons"][k]["per_month_mwh"]])
        ax.bar(x - 0.4 + w * (i + 0.5), d, w, label=lab)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x, MN)
    ax.set_ylabel("monthly energy difference [MWh]")
    ax.set_title("Paired monthly differences")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/S4_paired.png", dpi=140)
    plt.close(fig)
    # 5 Lorient
    bm = o["lorient"]["months"]
    if bm:
        xb = np.arange(len(bm))
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
        lab = [r["month"][5:] for r in bm]
        a1.plot(xb, [r["OH_cf"] for r in bm], "-o", color=COL["Oracle_REF_H"],
                label="Oracle_REF_H from Lorient")
        a1.plot(xb, [r["B1c_cf"] for r in bm], "-o", color=COL["B1c_5d_REF s1"],
                label="B1c_5d_REF from Lorient")
        a1.plot(xb, [r.get("B1c_A_cf", np.nan) for r in bm], "--", color=COL["B1c_5d_REF s1"],
                label="B1c, same window, ship at sea (A)")
        a1.plot(xb, [r.get("OH_A_cf", np.nan) for r in bm], "--", color=COL["Oracle_REF_H"],
                label="Oracle_H, same window (A)")
        a1.set_xticks(xb, lab)
        a1.set_xlabel("departure month (1st)")
        a1.set_ylabel("14-day capacity factor")
        a1.legend(frameon=False, fontsize=7)
        a1.grid(alpha=0.25)
        a2.bar(xb - 0.2, [r["B1c_t_sdf50km_h"] or np.nan for r in bm], 0.4,
               color=COL["B1c_5d_REF s1"], label="B1c: SDF >= 50 km")
        a2.bar(xb + 0.2, [r["OH_t_sdf50km_h"] or np.nan for r in bm], 0.4,
               color=COL["Oracle_REF_H"], label="Oracle_H: SDF >= 50 km")
        a2.set_xticks(xb, lab)
        a2.set_ylabel("hours to reach 50 km offshore")
        a2.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        fig.savefig(ROOT / "outputs/S4_lorient.png", dpi=140)
        plt.close(fig)
    # 6 ship-experienced TWS
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(x, basin["mean_tws_kn"], "k-o", ms=3, label="basin mean (sea cells)")
    for k in ("B0", "B1c_5d_REF s1", "ENS_REF s1"):
        if k in exp_tws:
            ax.plot(x, exp_tws[k], "-o", ms=3, color=COL[k], label=f"experienced, {k}")
    ax.set_xticks(x, MN)
    ax.set_ylabel("mean TWS [kn]")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/S4_tws.png", dpi=140)
    plt.close(fig)


# ======================================================================================== text
def f(v, fmt=".3f"):
    return "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else format(v, fmt)


def write_md(o):
    ks = list(o["energy_mwh"])
    L = ["# Sprint 4 results: persistent year-long runs (2015) and Lorient departures", "",
         "Generated by `scripts/analyze_s4.py` from `outputs/s4_runs` (`outputs/S4_results.json`, "
         "figures `outputs/S4_*.png`). Forecast model v2 (issue consistency + latency + "
         "seasonality, see `S4_forecast_notes.md`); ERA5 2015 truth, BETA polar, 40 km grid, "
         "d_min 20 km, replan 6 h, DP 3 h. Forecast errors are a hypothesised perturbation model, "
         "not NWP.", "",
         "## Experiment A: median fleet ship (persistent, 2015)", "",
         f"Start {o['start_lonlat'][0]:.2f} E, {o['start_lonlat'][1]:.2f} N (annual best offshore "
         "point), 2015-01-01 to 2015-12-31, no transits to port. `Oracle_REF_H` is hindsight with a "
         "15 d truth look-ahead + refiner + climatological terminal value: an APPROXIMATE bound.", "",
         "### Monthly capacity factor", "",
         "| Policy | " + " | ".join(MN) + " | Year |", "|---|" + "---|" * 13]
    for k in ks:
        L.append(f"| {k} | " + " | ".join(f(v, ".3f") for v in o["cf"][k]) + f" | "
                 f"{o['annual'][k]['cf']:.3f} |")
    L += ["", "| Basin | " + " | ".join(MN) + " | |", "|---|" + "---|" * 13,
          "| mean TWS [kn] | " + " | ".join(f(v, ".1f") for v in o["basin_tws_kn"]) + " | |",
          "| share 18-26 kn [%] | " + " | ".join(f(v * 100, ".1f") for v in o["basin_share_18_26"])
          + " | |"]
    for k in ks:
        L.append(f"| experienced TWS {k} [kn] | " + " | ".join(
            f(v, ".1f") for v in o["ship_tws_kn"][k]) + " | |")
    for k in ks:
        L.append(f"| experienced share 18-26 kn {k} [%] | " + " | ".join(
            f(None if v is None else v * 100, ".1f") for v in o["ship_share_18_26"][k]) + " | |")
    L += ["", "Basin = sea cells inside the ERA5 box, 3-hourly; experienced = true wind at the ship "
          "every 15 min.", "", "![monthly CF](../../outputs/S4_monthly_cf.png)", "",
          "### Monthly energy [MWh]", "",
          "| Policy | " + " | ".join(MN) + " | Year |", "|---|" + "---|" * 13]
    for k in ks:
        L.append(f"| {k} | " + " | ".join(f(v, ".0f") for v in o["energy_mwh"][k])
                 + f" | {o['annual'][k]['energy_mwh']:.0f} |")
    L += ["", "### Annual capacity factor and regret", "",
          "| Policy | Energy [MWh] | CF | Regret vs Oracle_REF_H [%] | wall [h] | guard | coast "
          "viol. | min margin [km] | DP fallbacks |", "|---|---|---|---|---|---|---|---|---|"]
    for k in ks:
        s = o["safety"][k]
        L.append(f"| {k} | {o['annual'][k]['energy_mwh']:.0f} | {o['annual'][k]['cf']:.3f} | "
                 f"{f(o['annual'][k]['regret_pct'], '.2f')} | {s['wall_h']:.2f} | "
                 f"{s['guard_interventions']} | {s['coast_violations']} | "
                 f"{f(s['min_margin_km'], '.2f')} | {s['n_dp_fallback']} |")
    L += ["", "![annual](../../outputs/S4_annual.png)", "", "### Monthly regret vs Oracle_REF_H [%]",
          "", "| Policy | " + " | ".join(MN) + " |", "|---|" + "---|" * 12]
    for k in o["regret_monthly_pct"]:
        L.append(f"| {k} | " + " | ".join(f(v, ".1f") for v in o["regret_monthly_pct"][k]) + " |")
    L += ["", "![regret](../../outputs/S4_regret_monthly.png)", "",
          "### Paired comparisons (monthly energy difference, positive = first better)", "",
          "| Comparison | n | mean [MWh/month] | sum [MWh] | std | t | mean % | wins |",
          "|---|---|---|---|---|---|---|---|"]
    for lab, c in o["comparisons"].items():
        L.append(f"| {lab} | {c['n']} | {c['mean_mwh_per_month']:+.1f} | {c['sum_mwh']:+.0f} | "
                 f"{f(c['std'], '.1f')} | {f(c['t'], '+.1f')} | {c['mean_pct_of_b']:+.2f} | "
                 f"{c['wins']}/{c['n']} |")
    L += ["", "![paired](../../outputs/S4_paired.png)", "",
          "### Forecast-error sensitivity (seed 1 vs 2)", ""]
    if o["seed_spread"]:
        for pol, s in o["seed_spread"].items():
            L.append(f"* {pol}: annual {s['annual_mwh'][0]:.0f} vs {s['annual_mwh'][1]:.0f} MWh "
                     f"(difference {s['annual_diff_mwh']:+.0f} MWh, {s['annual_diff_pct']:+.2f} %); "
                     f"monthly std of the difference {f(s['monthly_std_mwh'], '.1f')} MWh, max "
                     f"{s['monthly_abs_max_mwh']:.0f} MWh ({s['n_months']} months).")
    else:
        L.append("(no second seed)")
    L += ["", "![tws](../../outputs/S4_tws.png)", "", "## Experiment B: departures from Lorient", ""]
    bm = o["lorient"]["months"]
    if bm:
        L += ["14-day missions starting on the 1st of each month from Lorient (47.7 N, 3.4 W) through the "
              "port corridor (40 km ramp). `(A)` = same 14-day window in Experiment A (ship already "
              "at sea). t(50 km), t(100 km): first time the ship is that far from the coast "
              "(true coastline SDF); t(prod): first time the 6 h mean power reaches 90 % of the "
              "same-window mean power of A.", "",
              "| Month | B1c CF | B1c CF (A) | B1c t50 [h] | B1c t100 [h] | B1c t(prod) [h] | "
              "Oracle_H CF | Oracle_H CF (A) | Oracle_H t50 [h] | Oracle_H t(prod) [h] |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in bm:
            L.append(f"| {r['month']} | {r['B1c_cf']:.3f} | {f(r.get('B1c_A_cf'))} | "
                     f"{f(r['B1c_t_sdf50km_h'], '.1f')} | {f(r['B1c_t_sdf100km_h'], '.1f')} | "
                     f"{f(r['B1c_t_productive_h'], '.1f')} | {r['OH_cf']:.3f} | "
                     f"{f(r.get('OH_A_cf'))} | {f(r['OH_t_sdf50km_h'], '.1f')} | "
                     f"{f(r['OH_t_productive_h'], '.1f')} |")
        cb = np.mean([r["B1c_cf"] for r in bm])
        ca = np.nanmean([r.get("B1c_A_cf", np.nan) for r in bm])
        L += ["", f"Mean 14-day CF from Lorient: B1c {cb:.3f} vs {ca:.3f} at sea (A), i.e. "
              f"{(ca - cb) * P_RATED * 336 / 1e3:.1f} MWh lost per departure; "
              "![lorient](../../outputs/S4_lorient.png)"]
    else:
        L.append("(not available)")
    (ROOT / "docs/sprints/S4_results.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
