"""Plot the real BETA power polar (our TWA convention), feasibility mask and synthetic comparison.

Output: ``outputs/beta_polar.png`` (gitignored). Data are client-confidential and are read from
the path given as first argument (default ``/home/claude/circeo-horizon-data/power-polar``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from horizon.core.units import KNOT
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.beta import load_beta_polar
from horizon.polar.envelope import build_envelope

DEFAULT = "/home/claude/circeo-horizon-data/power-polar"
src = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
beta = load_beta_polar(src)
syn = synthetic_polar()
out = Path("outputs")
out.mkdir(exist_ok=True)

fig = plt.figure(figsize=(17, 14))
gs = fig.add_gridspec(3, 4)
kns = (10, 20, 30, 50)
for c, kn in enumerate(kns):
    ax = fig.add_subplot(gs[0, c], projection="polar")
    th = np.radians(beta.twa)
    for u in (0.0, 1.0, 2.0, 3.5, 5.0, 7.0):
        j = int(round(u / beta.d_u))
        ax.plot(th, beta.p[kn, :, j], label=f"U={u:g}")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetamax(180)
    ax.set_title(f"BETA TWS {kn} kn: P [kW] vs TWA (0 = head to wind)", fontsize=9)
    if c == 0:
        ax.legend(fontsize=6, loc="lower left")
for c, kn in enumerate((10, 20, 30, 50)):
    ax = fig.add_subplot(gs[1, c])
    p = beta.p[kn]
    im = ax.pcolormesh(beta.u, beta.twa, np.where(beta.feasible[kn], p, np.nan), cmap="RdBu_r",
                       vmin=-3000, vmax=3000, shading="auto")
    ax.set_facecolor("0.8")  # grey = infeasible
    ax.set_xlabel("U [m/s]")
    ax.set_ylabel("TWA [deg]")
    ax.set_title(f"TWS {kn} kn (grey = infeasible)", fontsize=9)
    if c == 3:
        fig.colorbar(im, ax=ax, label="P [kW]")
ax = fig.add_subplot(gs[2, 0])
ax.pcolormesh(beta.tws / KNOT, beta.twa, beta.feasible.mean(axis=2).T, cmap="Greys_r",
              shading="auto")
ax.set_xlabel("TWS [kn]")
ax.set_ylabel("TWA [deg]")
ax.set_title("fraction of feasible U", fontsize=9)
ax = fig.add_subplot(gs[2, 1])
kn = np.arange(51)
for name, t in (("BETA", beta), ("synthetic", syn)):
    pd, _ = t.reduced()
    ax.plot(kn, np.nanmax(pd, axis=1), label=f"{name} max P")
    ax.plot(kn, np.nanmin(np.where(t.feasible, t.p, np.nan).reshape(51, -1), axis=1), "--",
            label=f"{name} min P")
ax.set_xlabel("TWS [kn]")
ax.set_ylabel("P [kW]")
ax.legend(fontsize=7)
ax.set_title("extremes vs TWS", fontsize=9)
ax = fig.add_subplot(gs[2, 2:])
for name, t in (("BETA", beta), ("synthetic", syn)):
    h = hold_power_curve(t, include_stopped=True)
    e = build_envelope(t)
    ip = int(round(-e.vp0 / e.dv))
    ax.plot(kn, e.reward[:, ip, 0], label=f"{name} envelope(v=0)")
    ax.plot(kn, h.p_hold, ":", label=f"{name} hold curve (+stopped)")
ax.set_xlabel("TWS [kn]")
ax.set_ylabel("hold power [kW]")
ax.legend(fontsize=7)
ax.set_title("best station-keeping power", fontsize=9)
fig.tight_layout()
fig.savefig(out / "beta_polar.png", dpi=110)
print("wrote", out / "beta_polar.png")
