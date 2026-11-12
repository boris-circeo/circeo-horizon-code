"""Year-long validation report (campaign_year.yaml): annual CF, paired comparisons over the 35
ten-day segments, storm exposure, compute. Writes docs/s5/year_validation.md and
docs/s5/fig/s5_year_segments.png (aggregates only).

Usage: ``python3 scripts/s5/year_report.py``
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402

LABEL = {"HORIZON_V2": "HORIZON v2", "B1c_5d_REF": "v1 (B1c)", "Oracle_REF_H": "Oracle",
         "B0": "B0 poste fixe"}


def load():
    out = {}
    for c in L.expand(L.load_campaign(str(L.ROOT / "scripts/s5/campaign_year.yaml"))):
        p = L.result_path(c["id"])
        if p.exists():
            r = json.loads(p.read_text())
            out[(c["spec"]["router"]["name"], c["spec"]["seed"])] = r
    return out


def conv(ps):
    return f"{ps['n_not_converged']} / {ps['n_refined']}" if ps else "n/a"


def seg(r):
    return np.array([100 * s["cf"] for s in r["segments"]])


def paired(a, b):
    d = seg(a) - seg(b)
    n = len(d)
    return d.mean(), d.std(ddof=1) / np.sqrt(n), int((d > 0).sum()), n


def main():
    R = load()
    lines = ["# HORIZON v2 — year-long validation (2015-01-01 + 350 d, persistent ship)", "",
             "Campaign `scripts/s5/campaign_year.yaml`; S5 environment (manoeuvre losses, "
             "synthetic forecasts, d_min 20 km); terminal climatology in-sample for every router "
             "(a year-long window cannot leave its own months out; the leak is ±0.1 pt on 30-day "
             "windows, see v2_validation.md).", "",
             "| Router | Seed | CF [%] | Energy [MWh] | h > 35 kn | h > 45 kn | Manoeuvres/day "
             "| Refiner not converged | CPU [min] |", "|---|---|---|---|---|---|---|---|---|"]
    for (name, seed), r in sorted(R.items()):
        ps = r.get("policy_stats") or {}
        lines.append(f"| {LABEL.get(name, name)} | {seed} | {r['cf_pct']:.1f} "
                     f"| {r['energy_mwh']:.0f} | {r['storm35_h']:.0f} | {r['storm45_h']:.1f} "
                     f"| {r['manoeuvres']['per_day']:.2f} "
                     f"| {conv(ps)} "
                     f"| {r['wall_s'] / 60:.0f} |")
    lines += ["", "Paired differences over the 35 ten-day segments [CF points]:", "",
              "| Comparison | Mean | SE | Segments won |", "|---|---|---|---|"]
    pairs = [(("HORIZON_V2", 1), ("B1c_5d_REF", 1), "v2 − v1 (seed 1)"),
             (("HORIZON_V2", 2), ("HORIZON_V2", 1), "v2 seed 2 − seed 1"),
             (("HORIZON_V2", 1), ("B0", 0), "v2 − B0"),
             (("Oracle_REF_H", 0), ("HORIZON_V2", 1), "Oracle − v2"),
             (("Oracle_REF_H", 0), ("B1c_5d_REF", 1), "Oracle − v1")]
    for a, b, lab in pairs:
        if a in R and b in R:
            m, se, w, n = paired(R[a], R[b])
            lines.append(f"| {lab} | {m:+.2f} | {se:.2f} | {w}/{n} |")
    out = L.ROOT / "docs/s5/year_validation.md"
    out.write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    order = [("Oracle_REF_H", 0, "#7b3fa0"), ("HORIZON_V2", 1, "#1f77b4"),
             ("B1c_5d_REF", 1, "#d4a017"), ("B0", 0, "#777")]
    for name, seed, col in order:
        if (name, seed) in R:
            s = seg(R[(name, seed)])
            ax.plot(np.arange(len(s)) * 10 + 5, s, "-", color=col, lw=1.6,
                    label=f"{LABEL[name]} ({R[(name, seed)]['cf_pct']:.1f} %)")
    ax.set_xlabel("Jour de 2015 (segments de 10 jours)")
    ax.set_ylabel("Facteur de charge [%]")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2, loc="lower left")
    fig.tight_layout()
    fig.savefig(L.ROOT / "docs/s5/fig/s5_year_segments.png", dpi=170)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
