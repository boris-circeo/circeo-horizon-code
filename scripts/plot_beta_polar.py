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

fig = plt.figure(figsize=(20, 17))
gs = fig.add_gridspec(4, 4)
kns = (10, 14, 18, 22, 26, 30, 40, 50)
# angle = TWA (0 = head to wind at the top), both tacks mirrored, radius = U [m/s]
twa_full = np.concatenate([-beta.twa[::-1], beta.twa[1:]])
th_edges = np.radians(np.concatenate([[twa_full[0] - 1.25], 0.5 * (twa_full[1:] + twa_full[:-1]),
                                      [twa_full[-1] + 1.25]]))
r_edges = np.concatenate([[0.0], 0.5 * (beta.u[1:] + beta.u[:-1]), [beta.u[-1] + 0.125]])
for c, kn in enumerate(kns):
    ax = fig.add_subplot(gs[c // 4, c % 4], projection="polar")
    p = np.where(beta.feasible[kn], beta.p[kn], np.nan)
    full = np.concatenate([p[::-1], p[1:]], axis=0)
    ax.set_facecolor("0.85")  # grey = infeasible / no data
    im = ax.pcolormesh(th_edges, r_edges, np.ma.masked_invalid(full.T), cmap="RdBu_r",
                       vmin=-3000, vmax=3000, shading="flat")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 8.2)
    ax.set_title(f"TWS {kn} kn (wind from top; grey = infeasible)", fontsize=9)
    ax.tick_params(labelsize=7)
    if c == 7:
        fig.colorbar(im, ax=ax, label="P [kW]", shrink=0.8, pad=0.1)
ax = fig.add_subplot(gs[2, 0], projection="polar")
pd_all, _ = beta.reduced()
for kn in (10, 14, 18, 22, 30, 50):
    y = pd_all[kn]
    ax.plot(np.radians(beta.twa), y, label=f"{kn} kn")
    ax.plot(-np.radians(beta.twa), y, color=ax.lines[-1].get_color())
ax.set_theta_zero_location("N")
ax.set_theta_direction(-1)
ax.set_title("P-dagger(TWA) = max_U P [kW], both tacks", fontsize=9)
ax.legend(fontsize=6, loc="lower left")
ax = fig.add_subplot(gs[3, 0])
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
