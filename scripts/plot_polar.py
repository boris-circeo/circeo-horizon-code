"""Plot the synthetic power polar and hold curve to ``outputs/polar_synthetic.png``.

matplotlib is an optional dependency: ``pip install matplotlib``.
Usage: ``python scripts/plot_polar.py [output.png]``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.table import KNOT

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None


def main(out: Path) -> None:
    if plt is None:
        sys.exit("matplotlib is not installed (optional dependency): pip install matplotlib")
    polar = synthetic_polar()
    p_dag, u_dag = polar.reduced()
    hold = hold_power_curve(polar)
    kn = polar.tws / KNOT

    fig = plt.figure(figsize=(14, 4.5), constrained_layout=True)
    ax = fig.add_subplot(1, 3, 1, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetamax(180)
    for k in (10, 15, 18, 20, 22, 26):
        ax.plot(np.radians(polar.twa), np.clip(p_dag[k], 0, None), label=f"{k} kn")
    ax.set_title("P_dagger(TWA) [kW], max over U")
    ax.legend(loc="lower left", fontsize=7)

    ax = fig.add_subplot(1, 3, 2)
    im = ax.pcolormesh(
        polar.u, polar.twa, polar.p[20].astype(float), shading="auto", cmap="viridis"
    )
    ax.set(xlabel="U [m/s]", ylabel="TWA [deg]", title="P at TWS = 20 kn [kW]")
    fig.colorbar(im, ax=ax)

    ax = fig.add_subplot(1, 3, 3)
    for a in (30, 60, 90, 135):
        ax.plot(kn, p_dag[:, int(a / polar.d_twa)], label=f"TWA {a} deg")
    ax.plot(kn, hold.p_hold, "k--", label="hold curve")
    ax.plot(kn, hold.p_beam, "k:", label="beam optimum")
    ax.set(xlabel="TWS [kn]", ylabel="P [kW]", title="Cuts at fixed TWA (synthetic: HYPOTHESES)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(out.resolve())


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/polar_synthetic.png"))
