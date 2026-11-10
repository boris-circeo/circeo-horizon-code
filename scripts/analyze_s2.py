"""Assemble Sprint-2 results: outputs/S2_results.json, docs/sprints/S2_results.md, figures, and the
inspector export (outputs/s2_inspector/*.json.gz) from the per-run pickles of run_s2_backtest.py."""

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import run_s2_backtest as r  # noqa: E402

from horizon.sim.metrics import regret  # noqa: E402
from horizon.viz import SeedRun, export_backtest, save_export  # noqa: E402

ROOT = r.ROOT
SEEDS = (101, 102, 103, 104, 105)
S1P = ("B0", "B0_spec", "B1_5d", "B1_15d", "Oracle")
ALL = ("Oracle", "B0", "B0_spec", "B1_5d", "B1_15d", "B1_5d_REF", "ENS_g0", "ENS_g03",
       "ENS_g03_REF")
KEYS = ("energy_kwh", "capacity_factor", "regret", "hold_fraction", "distance_km")


def load_runs():
    out = {}
    for f in sorted((ROOT / "outputs" / "s2_runs").glob("*.pkl")):
        d = pickle.loads(f.read_bytes())
        out[(d["name"], d["seed"])] = d
    return out


def season_spread(seeds, members=12):
    """Mean over issues (every 2 d, days 0-26) of basin-mean member std of TWS at leads 5-15 d."""
    grid, coast, *_ = r.setup()
    sea = coast.sdf > 0
    res = {}
    for s in seeds:
        wx = r.SyntheticWeather(grid, r.EPOCH, r.T, seed=s)
        vals = []
        for d in range(0, 28, 3):
            ens = wx.forecast(d * 86400.0, 15 * 86400.0, members, dt_s=6 * 3600.0)
            tws = np.hypot(ens.uv[..., 0], ens.uv[..., 1])  # (M,T,Ny,Nx)
            lead = (ens.times_s - ens.issue_s) / 86400.0
            sel = (lead >= 5) & (lead <= 15)
            vals.append(float(tws[:, sel][..., sea].std(axis=0, ddof=1).mean()))
        res[s] = float(np.mean(vals))
    return res


def main():
    s1 = json.loads((ROOT / "outputs" / "S1_results.json").read_text())
    runs = load_runs()
    out = {"setup": {"members": next(iter(runs.values()))["members"],
                     "k": next(iter(runs.values()))["k"], "seeds": list(SEEDS)},
           "B0_point": s1["B0_point"], "B0_spec_point": s1["B0_spec_point"], "seeds": {}}
    for s in SEEDS:
        row = {p: dict(s1["seeds"][str(s)][p]) for p in S1P}
        jh = row["Oracle"]["energy_kwh"]
        for p in ("B1_5d_REF", "ENS_g0", "ENS_g03", "ENS_g03_REF"):
            d = runs.get((p, s))
            if d is None:
                continue
            m = d["metrics"]
            row[p] = {**m, "regret": regret(jh, m["energy_kwh"]),
                      "coast_violations": d["coast_violations"], "n_replans": d["n_replans"],
                      "wall_s": d["wall_s"]}
        row["diagnostics"] = s1["seeds"][str(s)]["diagnostics"]
        out["seeds"][str(s)] = row
    pols = [p for p in ALL if all(p in out["seeds"][str(s)] for s in SEEDS)]
    pols_part = [p for p in ALL if p not in pols]
    summ = {}
    for p in ALL:
        ss = [s for s in SEEDS if p in out["seeds"][str(s)]]
        for k in KEYS:
            v = np.array([out["seeds"][str(s)][p][k] for s in ss])
            summ.setdefault(p, {})[k] = {"mean": float(v.mean()),
                                         "std": float(v.std(ddof=1)) if v.size > 1 else 0.0,
                                         "n": int(v.size)}
    out["summary"] = summ
    # paired comparisons (energy J, MWh)
    def J(p, s):
        return out["seeds"][str(s)][p]["energy_kwh"] / 1e3

    pairs = [("E1 ensemble value", "ENS_g0", "B1_15d"), ("E1b ENS_g0 vs B1_5d", "ENS_g0", "B1_5d"),
             ("Risk effect (gamma 0.3 vs 0)", "ENS_g03", "ENS_g0"),
             ("Refiner on B1_5d", "B1_5d_REF", "B1_5d"),
             ("Refiner on ENS_g03", "ENS_g03_REF", "ENS_g03"),
             ("ENS_g03 vs B1_15d", "ENS_g03", "B1_15d"),
             ("ENS_g03_REF vs B1_5d_REF", "ENS_g03_REF", "B1_5d_REF")]
    paired = {}
    for lab, a, b in pairs:
        ss = [s for s in SEEDS if a in out["seeds"][str(s)] and b in out["seeds"][str(s)]]
        if not ss:
            continue
        d = np.array([J(a, s) - J(b, s) for s in ss])
        jb = np.array([J(b, s) for s in ss])
        sd = d.std(ddof=1) if d.size > 1 else float("nan")
        t = d.mean() / (sd / np.sqrt(d.size)) if d.size > 1 and sd > 0 else float("nan")
        paired[lab] = {"a": a, "b": b, "seeds": ss, "delta_mwh": d.tolist(),
                       "mean": float(d.mean()), "std": float(sd), "t": float(t),
                       "mean_pct": float(100 * np.mean(d / jb)), "wins": int((d > 0).sum()),
                       "n": int(d.size),
                       "worst_a": float(min(J(a, s) for s in ss)),
                       "worst_b": float(min(J(b, s) for s in ss))}
    out["paired"] = paired
    # best policy vs oracle
    # P10 / worst-seed of J
    out["tail"] = {p: {"worst_mwh": float(min(J(p, s) for s in SEEDS if p in out["seeds"][str(s)])),
                       "p10_mwh": float(np.percentile([J(p, s) for s in SEEDS
                                                        if p in out["seeds"][str(s)]], 10))}
                   for p in ALL}
    # spread stratification of E1
    sp = season_spread(SEEDS)
    out["season_spread_tws_ms"] = sp
    if "E1 ensemble value" in paired:
        d = paired["E1 ensemble value"]
        out["e1_by_spread"] = sorted(
            [{"seed": s, "spread_ms": sp[s], "delta_mwh": x} for s, x in
             zip(d["seeds"], d["delta_mwh"], strict=True)], key=lambda e: e["spread_ms"])
        if len(d["seeds"]) > 2:
            out["e1_spread_corr"] = float(np.corrcoef([sp[s] for s in d["seeds"]],
                                                     d["delta_mwh"])[0, 1])
    # refiner stats + diagnostics
    out["timing"] = {p: float(np.mean([out["seeds"][str(s)][p]["wall_s"] for s in SEEDS
                                       if "wall_s" in out["seeds"][str(s)].get(p, {})] or [0]))
                     for p in ("B1_5d_REF", "ENS_g0", "ENS_g03", "ENS_g03_REF")}
    (ROOT / "outputs" / "S2_results.json").write_text(json.dumps(out, indent=2))
    write_md(out, pols, pols_part)
    figures(runs)
    export_inspector(runs)
    print("done; complete policies:", pols, "partial:", pols_part)


def write_md(out, pols, part):
    P = [*pols, *part]
    seeds = SEEDS

    def table(title, key, scale, fmt, unit):
        lines = [f"### {title}", "", "| Seed | " + " | ".join(P) + " |", "|---|" + "---|" * len(P)]
        for s in seeds:
            rw = out["seeds"][str(s)]
            lines.append(f"| {s} | " + " | ".join(
                format(rw[p][key] * scale, fmt) if p in rw else "-" for p in P) + " |")
        lines.append("| mean +- std | " + " | ".join(
            f"{out['summary'][p][key]['mean'] * scale:{fmt}} +- "
            f"{out['summary'][p][key]['std'] * scale:{fmt}}"
            + (f" (n={out['summary'][p][key]['n']})" if out['summary'][p][key]['n'] < 5 else "")
            for p in P) + " |")
        return "\n".join(lines) + f"\n\n(unit: {unit})\n"

    md = ["# Sprint 2 - ensemble MPC, CVaR and refiner: regret figure", "",
          "Same setup as S1 (30-day missions from 47.0N 6.5W, synthetic winters seeds 101-105, "
          "40 km grid, 3 h DP, replan 6 h, synthetic polar). New policies: ENS_g0 / ENS_g03 = "
          f"EnsembleMPCPolicy, 15 d, {out['setup']['members']} members, k={out['setup']['k']}, "
          "48 h non-anticipative trunk, gamma 0 / 0.3 (alpha 0.2), zero terminal value; *_REF = "
          "RefinedMPCPolicy (first 48 h refined at 30 min with IPOPT, terminal value = DP / "
          "ensemble v_bar at +48 h). S1 policies are reused from `outputs/S1_results.json` "
          "(re-run bit-identically for the inspector seeds). Generated by "
          "`scripts/run_s2_backtest.py` + `scripts/analyze_s2.py`; raw numbers in "
          "`outputs/S2_results.json`.", "",
          table("Energy J", "energy_kwh", 1e-3, ".1f", "MWh; Oracle = J_hind"),
          table("Capacity factor", "capacity_factor", 1.0, ".3f", "J / (3000 kW T)"),
          table("Regret (J_hind - J) / J_hind", "regret", 100.0, ".1f", "%"),
          table("Hold fraction", "hold_fraction", 100.0, ".0f", "% of time below 0.5 m/s"),
          "### Worst seed / P10 of J [MWh]", "", "| Policy | worst seed | P10 |", "|---|---|---|"]
    md += [f"| {p} | {out['tail'][p]['worst_mwh']:.1f} | {out['tail'][p]['p10_mwh']:.1f} |"
           for p in P]
    md += ["", "### Paired comparisons (J_a - J_b, MWh per 30 d; positive = a better)", "",
           "| Comparison | mean delta | std | mean delta % of J_b | wins (a>b) | paired t "
           "| per-seed |",
           "|---|---|---|---|---|---|---|"]
    for lab, d in out["paired"].items():
        md.append(f"| {lab}: {d['a']} - {d['b']} | {d['mean']:+.1f} | {d['std']:.1f} | "
                  f"{d['mean_pct']:+.1f} | {d['wins']}/{d['n']} | {d['t']:+.2f} | "
                  + ", ".join(f"{x:+.0f}" for x in d["delta_mwh"]) + " |")
    md += ["", "With n = 5 seeds the paired t-test has 4 degrees of freedom (|t| > 2.78 needed at "
           "5 %): significance is limited; treat as indicative.", "",
           "### E1 stratified by seasonal ensemble spread", "",
           "Spread = mean over issues (every 3 d) and sea cells of the member std of TWS at leads "
           "5-15 d [m/s].", "", "| Seed | spread [m/s] | ENS_g0 - B1_15d [MWh] |", "|---|---|---|"]
    md += [f"| {e['seed']} | {e['spread_ms']:.3f} | {e['delta_mwh']:+.1f} |"
           for e in out.get("e1_by_spread", [])]
    if "e1_spread_corr" in out:
        n_e1 = len(out["e1_by_spread"])
        md.append(f"\nCorrelation spread vs delta: {out['e1_spread_corr']:+.2f} (n={n_e1}).")
    md += ["", "Mean wall time per mission [s]: " + ", ".join(
        f"{k} {v:.0f}" for k, v in out["timing"].items()) + ".", ""]
    (ROOT / "docs" / "sprints" / "S2_results.md").write_text("\n".join(md))


def figures(runs):
    grid, coast, *_ = r.setup()
    colors = {"B0": "tab:gray", "B0_spec": "tab:orange", "B1_5d": "tab:blue",
              "B1_15d": "tab:green", "Oracle": "tab:red", "B1_5d_REF": "tab:cyan",
              "ENS_g0": "tab:purple", "ENS_g03": "tab:brown", "ENS_g03_REF": "tab:pink"}
    ext = [(grid.x0 - grid.dx / 2) / 1e3, (grid.x0 + (grid.nx - 0.5) * grid.dx) / 1e3,
           (grid.y0 - grid.dx / 2) / 1e3, (grid.y0 + (grid.ny - 0.5) * grid.dx) / 1e3]
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.imshow(np.clip(coast.sdf / 1e3, -300, 1000), origin="lower", extent=ext, cmap="Blues",
              vmin=-300, vmax=1500)
    ax.contourf(grid.x / 1e3, grid.y / 1e3, coast.land_mask, levels=[0.5, 1.5], colors="0.55")
    for p in ("B0", "B1_5d", "B1_15d", "B1_5d_REF", "ENS_g0", "ENS_g03", "ENS_g03_REF", "Oracle"):
        d = runs.get((p, 101))
        if d is not None:
            ax.plot(d["res"].x / 1e3, d["res"].y / 1e3, color=colors[p], lw=1.0, label=p, alpha=.9)
    sx, sy = grid.to_xy(*r.START)
    ax.plot(sx / 1e3, sy / 1e3, "k*", ms=12, label="start")
    ax.set(xlabel="x [km]", ylabel="y [km]", title="Trajectories, seed 101 (S1 + S2 policies)")
    ax.legend(loc="lower left", ncol=2)
    fig.savefig(ROOT / "outputs" / "S2_trajectories.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    s2 = json.loads((ROOT / "outputs" / "S2_results.json").read_text())
    P = [p for p in ALL if p != "Oracle"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    m = [100 * s2["summary"][p]["regret"]["mean"] for p in P]
    sd = [100 * s2["summary"][p]["regret"]["std"] for p in P]
    ax.bar(P, m, yerr=sd, color=[colors[p] for p in P], capsize=3)
    for s in SEEDS:
        ax.plot(range(len(P)), [100 * s2["seeds"][str(s)][p]["regret"] if p in
                                s2["seeds"][str(s)] else np.nan for p in P], "k.", ms=4, alpha=.5)
    ax.set(ylabel="regret [%]", title="Regret vs hindsight oracle (mean +- std; dots = seeds)")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.savefig(ROOT / "outputs" / "S2_regret_bars.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


def export_inspector(runs):
    grid, coast, polar, hold, pm = r.setup()
    info = {
        "B0": {"label": "B0 hold at best fixed point"},
        "B0_spec": {"label": "B0 hold at spec point 50N 15W"},
        "B1_5d": {"label": "B1 deterministic MPC, 5 d", "params": {"horizon_days": 5}},
        "B1_15d": {"label": "B1 deterministic MPC, 15 d", "params": {"horizon_days": 15}},
        "Oracle": {"label": "Hindsight oracle (DP on truth)"},
        "ENS_g0": {"label": "Ensemble MPC, expectation only (gamma 0)",
                   "params": {"horizon_days": 15, "gamma": 0.0, "alpha": 0.2}},
        "ENS_g03": {"label": "Ensemble MPC + CVaR (gamma 0.3)",
                    "params": {"horizon_days": 15, "gamma": 0.3, "alpha": 0.2}},
        "B1_5d_REF": {"label": "B1 5 d + continuous refiner 48 h"},
        "ENS_g03_REF": {"label": "Ensemble CVaR + continuous refiner 48 h"},
    }
    b = json.loads((ROOT / "outputs" / "S1_results.json").read_text())
    markers = [{"name": "B0 point", **{k: b["B0_point"][k] for k in ("lon", "lat")}},
               {"name": "B0_spec point", "lon": r.SPEC_POINT[0], "lat": r.SPEC_POINT[1]}]
    seeds = sorted({s for (_, s) in runs if ("Oracle", s) in runs})
    sruns = []
    for s in seeds:
        wx = r.SyntheticWeather(grid, r.EPOCH, r.T, seed=s)
        truth = wx.truth(dt_s=3600.0)
        names = [p for p in ALL if (p, s) in runs]
        sruns.append(SeedRun(s, truth, {p: runs[(p, s)]["res"] for p in names}, wx,
                             {p: runs[(p, s)]["records"] for p in names}))
    d0 = next(iter(runs.values()))
    data = export_backtest(
        sruns, coast, reference="Oracle", title="HORIZON S2 router inspector", wind_dt_s=3 * 3600.0,
        policy_info=info, markers=markers, start_lonlat=r.START,
        params={"grid_km": 40, "replan_h": 6, "plan_dt_h": 3, "start": "47.0N 6.5W",
                "weather": "synthetic", "members": d0["members"], "k": d0["k"],
                "n_seeds": len(seeds)})
    out = ROOT / "outputs" / "s2_inspector"
    out.mkdir(exist_ok=True)
    save_export(data, out / "s2_export.json.gz")


if __name__ == "__main__":
    main()
