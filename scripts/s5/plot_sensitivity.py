"""S5 figures (French labels, for the v2 document): tornado of paired effects and forecast-error
curve. Writes docs/s5/fig/s5_tornado.png and docs/s5/fig/s5_error_curve.png (aggregates only).

Usage: ``python3 scripts/s5/plot_sensitivity.py`` (after ``sensitivity_view.py``).
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sensitivity import compute_rows  # noqa: E402

import s5lib as L  # noqa: E402

FIG = L.ROOT / "docs" / "s5" / "fig"


def tornado(view):
    rows = [(g["fr"], r) for g in view["groups"] for r in g["rows"]]
    n = len(rows) + len(view["groups"])
    fig, ax = plt.subplots(figsize=(8.6, 0.24 * n + 1.0))
    y, labels, ys = 0, [], []
    for g in view["groups"]:
        ax.text(-0.01, y, g["fr"], transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=8.5, fontweight="bold")
        y += 1
        for r in g["rows"]:
            sig = r["z"] is not None and abs(r["z"]) >= 2
            col = "#9aa3b2" if not sig else ("#2e9e6a" if r["delta"] >= 0 else "#d0563b")
            ax.barh(y, r["delta"], color=col, height=0.7)
            if r["se"]:
                ax.errorbar(r["delta"], y, xerr=1.96 * r["se"], color="#333", lw=0.8, capsize=2)
            labels.append(r["fr"])
            ys.append(y)
            y += 1
    ax.set_yticks(ys, labels, fontsize=7.5)
    ax.invert_yaxis()
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_xlabel("Effet apparié sur le facteur de charge [points]  (barre : IC 95 %)")
    ax.grid(axis="x", alpha=0.3)
    ax.tick_params(axis="y", pad=2)
    fig.subplots_adjust(left=0.42, right=0.98, top=0.98, bottom=0.6 / (0.24 * n + 1.0) + 0.02)
    fig.savefig(FIG / "s5_tornado.png", dpi=170)
    plt.close(fig)


def error_curve():
    rows = compute_rows()
    pts = {}
    for r in rows:
        env = json.loads(r["env_ovr"])
        if r["router_ovr"] != "{}" or set(env) - {"error_scale"}:
            continue
        if r["router"] in ("B1c_5d_REF", "ENS_REF") and r["seed"] == 1:
            pts.setdefault(r["router"], []).append((env.get("error_scale", 1.0), r["cf"]))
    oracle = next(r["cf"] for r in rows if r["router"] == "Oracle_REF_H" and r["env_ovr"] == "{}"
                  and r["router_ovr"] == "{}")
    b0 = next(r["cf"] for r in rows if r["router"] == "B0" and r["env_ovr"] == "{}")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for name, lab, col in (("B1c_5d_REF", "B1c (prévision de contrôle)", "#1f77b4"),
                           ("ENS_REF", "ENS (ensemble, 2 étapes)", "#d4a017")):
        p = sorted(pts.get(name, []))
        ax.plot([a for a, _ in p], [c for _, c in p], "o-", color=col, label=lab)
    ax.axhline(oracle, color="#7b3fa0", ls="--", lw=1, label=f"Oracle (a posteriori) {oracle:.1f} %")
    ax.axhline(b0, color="#666", ls=":", lw=1, label=f"B0 poste fixe optimal {b0:.1f} %")
    ax.set_xlabel("Échelle de l'erreur de prévision (1 = nominale)")
    ax.set_ylabel("Facteur de charge [%]")
    ax.set_xticks(np.arange(0, 2.01, 0.5))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(FIG / "s5_error_curve.png", dpi=170)
    plt.close(fig)


def main():
    view = json.loads((L.OUT / "sensitivity_view.json").read_text())
    FIG.mkdir(parents=True, exist_ok=True)
    tornado(view)
    error_curve()
    print("wrote", FIG / "s5_tornado.png", FIG / "s5_error_curve.png")


if __name__ == "__main__":
    main()
