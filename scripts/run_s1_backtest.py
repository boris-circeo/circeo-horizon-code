"""Sprint-1 closed-loop backtest: B0, B1 (5 d / 15 d) and hindsight oracle on 5 synthetic winters.

Writes outputs/S1_results.json, docs/sprints/S1_results.md and two figures to outputs/.
Start 47.0N 6.5W (cells within d_min = 20 km of the coast are infeasible in the DP, so the start
must be offshore). Evaluation seeds 101..105, training seeds 1..3 (B0 point only).
"""

import argparse
import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from horizon.core.units import KNOT  # noqa: E402
from horizon.geo.coast import build_basin_coast  # noqa: E402
from horizon.geo.grid import Grid  # noqa: E402
from horizon.polar import hold_power_curve, synthetic_polar  # noqa: E402
from horizon.polar.envelope import build_envelope  # noqa: E402
from horizon.sim import (  # noqa: E402
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    HoldAtPointPolicy,
    OraclePolicy,
    best_climatological_point,
    mission_metrics,
    run_mission,
)
from horizon.sim.metrics import regret  # noqa: E402
from horizon.weather.synthetic import SyntheticWeather  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0
T = 30 * DAY
START = (-6.5, 47.0)  # (lon, lat) [deg], offshore of Lorient
EVAL_SEEDS = (101, 102, 103, 104, 105)
TRAIN_SEEDS = (1, 2, 3)
POLICIES = ("B0", "B0_spec", "B1_5d", "B1_15d", "Oracle")
SPEC_POINT = (-15.0, 50.0)  # (lon, lat) [deg], spec indicative zone for B0


def diagnostics(truth, coast):
    """Basin-mean TWS [m/s] and fraction of (time, sea cell) with TWS in 18-26 kn."""
    tws = np.hypot(truth.uv[..., 0], truth.uv[..., 1])[:, coast.sdf > 0]
    return {"mean_tws_ms": float(tws.mean()),
            "frac_18_26kn": float(np.mean((tws >= 18 * KNOT) & (tws <= 26 * KNOT)))}


def main(b0_only: bool = False):
    """Full run, or with ``b0_only`` re-run B0/B0_spec reusing stored results of other policies."""
    t_start = time.perf_counter()
    grid = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = build_basin_coast(40e3)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    pm = EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))
    sx, sy = grid.to_xy(*START)
    jpath = ROOT / "outputs" / "S1_results.json"
    old = json.loads(jpath.read_text()) if b0_only else None

    train = [SyntheticWeather(grid, EPOCH, T, seed=s).truth(dt_s=3 * 3600.0) for s in TRAIN_SEEDS]
    bx, by, b_mean = best_climatological_point(train, pm, coast, (sx, sy))
    del train
    b_lon, b_lat = grid.to_lonlat(bx, by)
    print(f"B0 point: {b_lat:.2f}N {b_lon:.2f}E, training-mean hold power {b_mean:.0f} kW")
    spec_xy = grid.to_xy(*SPEC_POINT)

    out = {"B0_point": {"lon": float(b_lon), "lat": float(b_lat), "train_mean_hold_kw": b_mean},
           "B0_spec_point": {"lon": SPEC_POINT[0], "lat": SPEC_POINT[1]},
           "start": {"lon": START[0], "lat": START[1]}, "seeds": {}}
    tracks = {}
    for seed in EVAL_SEEDS:
        t0 = time.perf_counter()
        wx = SyntheticWeather(grid, EPOCH, T, seed=seed)
        truth = wx.truth(dt_s=3600.0)
        pols = {
            "B0": HoldAtPointPolicy(bx, by),
            "B0_spec": HoldAtPointPolicy(*spec_xy),
            "B1_5d": DeterministicMPCPolicy(polar, hold, coast, horizon_days=5.0),
            "B1_15d": DeterministicMPCPolicy(polar, hold, coast, horizon_days=15.0),
            "Oracle": OraclePolicy(truth, polar, hold, coast, T),
        }
        todo = ["B0", "B0_spec"] if b0_only else ["Oracle", "B0", "B0_spec", "B1_5d", "B1_15d"]
        if b0_only and seed == EVAL_SEEDS[0]:  # other tracks are needed for the figures only
            todo = list(pols)
        res = {n: run_mission(pols[n], wx, truth, START, T, pm, coast) for n in todo}
        row = {}
        if b0_only:
            row = old["seeds"][str(seed)]
            j_hind = row["Oracle"]["energy_kwh"]
        else:
            j_hind = mission_metrics(res["Oracle"]).energy_kwh
        for name in todo:
            m = mission_metrics(res[name])
            new = {**m.__dict__, "regret": regret(j_hind, m.energy_kwh),
                   "coast_violations": res[name].coast_violations,
                   "n_replans": res[name].n_replans}
            if b0_only and name not in ("B0", "B0_spec"):
                assert abs(new["energy_kwh"] / row[name]["energy_kwh"] - 1) < 1e-9  # reproducible
                continue
            row[name] = new
        if "Oracle" in res and not b0_only:
            row["Oracle"]["dp_value_kwh"] = pols["Oracle"].dp_value_kwh
        row["diagnostics"] = diagnostics(truth, coast)
        out["seeds"][str(seed)] = row
        if seed == EVAL_SEEDS[0]:
            tracks = res
        print(f"seed {seed}: " + ", ".join(
            f"{n} {row[n]['energy_kwh'] / 1e3:.1f} MWh (regret {100 * row[n]['regret']:.1f}%)"
            for n in POLICIES) + f"  [{time.perf_counter() - t0:.0f} s]")

    summ = {}
    for name in POLICIES:
        for key in ("energy_kwh", "capacity_factor", "regret", "hold_fraction", "distance_km"):
            v = np.array([out["seeds"][str(s)][name][key] for s in EVAL_SEEDS])
            summ.setdefault(name, {})[key] = {"mean": float(v.mean()), "std": float(v.std(ddof=1))}
    out["summary"] = summ
    (ROOT / "outputs").mkdir(exist_ok=True)
    jpath.write_text(json.dumps(out, indent=2))
    write_markdown(out)
    figures(grid, coast, tracks, (bx, by), spec_xy, (sx, sy))
    print(f"total runtime {time.perf_counter() - t_start:.0f} s")


def write_markdown(out):
    def table(title, key, scale, fmt, unit):
        lines = [f"### {title}", "", "| Seed | " + " | ".join(POLICIES) + " |",
                 "|---|" + "---|" * len(POLICIES)]
        for s in EVAL_SEEDS:
            r = out["seeds"][str(s)]
            lines.append(f"| {s} | " + " | ".join(
                format(r[p][key] * scale, fmt) for p in POLICIES) + " |")
        lines.append("| mean +- std | " + " | ".join(
            f"{out['summary'][p][key]['mean'] * scale:{fmt}} +- "
            f"{out['summary'][p][key]['std'] * scale:{fmt}}" for p in POLICIES) + " |")
        return "\n".join(lines) + f"\n\n(unit: {unit})\n"

    b = out["B0_point"]
    diag = ["", "Weather diagnostic per seed (sea cells, whole grid, hourly truth): basin-mean TWS "
            "and fraction of (time, sea cell) with TWS in 18-26 kn:", ""]
    diag += [f"- seed {s}: mean TWS {out['seeds'][str(s)]['diagnostics']['mean_tws_ms']:.1f} m/s "
             f"({out['seeds'][str(s)]['diagnostics']['mean_tws_ms'] / KNOT:.1f} kn), "
             f"{100 * out['seeds'][str(s)]['diagnostics']['frac_18_26kn']:.0f} % in 18-26 kn"
             for s in EVAL_SEEDS]
    md = ["# Sprint 1 - first regret figure", "",
          "Closed-loop causal backtest, 30-day missions from 47.0N 6.5W, synthetic winters "
          "(seeds 101-105), 40 km grid, 3 h DP steps, replan every 6 h, synthetic polar "
          "(hypotheses). Generated by `scripts/run_s1_backtest.py`; raw numbers in "
          "`outputs/S1_results.json`.", "",
          f"B0 hold point (training seeds {TRAIN_SEEDS}): {b['lat']:.2f}N {b['lon']:.2f}E, "
          f"training-mean hold power {b['train_mean_hold_kw']:.0f} kW "
          "(candidates: nominal bbox, SDF >= 50 km, within 800 NM of the start). B0_spec: fixed "
          f"point {out['B0_spec_point']['lat']:.0f}N {-out['B0_spec_point']['lon']:.0f}W.", "",
          table("Energy J", "energy_kwh", 1e-3, ".1f", "MWh; Oracle = J_hind"),
          table("Capacity factor", "capacity_factor", 1.0, ".3f", "J / (3000 kW T)"),
          table("Regret (J_hind - J) / J_hind", "regret", 100.0, ".1f", "%"),
          table("Hold fraction", "hold_fraction", 100.0, ".0f", "% of time below 0.5 m/s"),
          "\n".join(diag), ""]
    (ROOT / "docs" / "sprints" / "S1_results.md").write_text("\n".join(md))


def figures(grid, coast, tracks, b0_xy, spec_xy, start_xy):
    colors = {"B0": "tab:gray", "B0_spec": "tab:orange", "B1_5d": "tab:blue",
              "B1_15d": "tab:green", "Oracle": "tab:red"}
    ext = [(grid.x0 - grid.dx / 2) / 1e3, (grid.x0 + (grid.nx - 0.5) * grid.dx) / 1e3,
           (grid.y0 - grid.dx / 2) / 1e3, (grid.y0 + (grid.ny - 0.5) * grid.dx) / 1e3]
    fig, ax = plt.subplots(figsize=(11, 8))
    im = ax.imshow(np.clip(coast.sdf / 1e3, -300, 1000), origin="lower", extent=ext,
                   cmap="Blues", vmin=-300, vmax=1500)
    ax.contourf(grid.x / 1e3, grid.y / 1e3, coast.land_mask, levels=[0.5, 1.5], colors="0.55")
    ax.contour(grid.x / 1e3, grid.y / 1e3, coast.sdf / 1e3, levels=[20, 50], colors="k",
               linewidths=0.4)
    for name, r in tracks.items():
        ax.plot(r.x / 1e3, r.y / 1e3, color=colors[name], lw=1.1, label=name, alpha=0.9)
    ax.plot(*np.array(start_xy) / 1e3, "k*", ms=12, label="start")
    ax.plot(*np.array(b0_xy) / 1e3, "s", color="tab:gray", mec="k", label="B0 point")
    ax.plot(*np.array(spec_xy) / 1e3, "s", color="tab:orange", mec="k", label="B0_spec point")
    ax.set(xlabel="x [km]", ylabel="y [km]", title="Trajectories, seed 101 (background: SDF [km])")
    ax.legend(loc="lower left")
    fig.colorbar(im, ax=ax, shrink=0.7, label="SDF [km]")
    fig.savefig(ROOT / "outputs" / "S1_trajectories.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for name, r in tracks.items():
        ax.plot(r.t_s / DAY, r.energy_kwh / 1e3, color=colors[name], label=name)
    ax.set(xlabel="time [days]", ylabel="cumulative energy [MWh]",
           title="Cumulative energy, seed 101")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig(ROOT / "outputs" / "S1_cumulative_energy.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--b0-only", action="store_true",
                    help="re-run B0 and B0_spec only, reuse stored results of the other policies")
    main(ap.parse_args().b0_only)
