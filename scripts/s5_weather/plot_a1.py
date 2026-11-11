import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
mk = np.load(OUT/"masks.npz"); sea=mk["sea"]; land=mk["land"]; lon=mk["lon"]; lat=mk["lat"]
z = np.load(OUT/"a1_maps.npz"); r = json.load(open(OUT/"a1.json"))
def pm(ax, f, vmin, vmax, cmap, title):
    a = np.where(sea, f, np.nan)
    im = ax.pcolormesh(lon, lat, a, vmin=vmin, vmax=vmax, cmap=cmap, shading="auto")
    ax.contour(lon, lat, land.astype(float), [0.5], colors="k", linewidths=.4)
    ax.set_title(title, fontsize=9); ax.set_aspect(1/np.cos(np.radians(50)))
    ax.tick_params(labelsize=7); return im
fig, axs = plt.subplots(1, 3, figsize=(13, 4.6))
pm(axs[0], z["Tyear"], 8, 24, "viridis", "mean TWS [kn], 2015")
im = pm(axs[1], z["Pyear"]/3000, 0.1, 0.6, "viridis", "CF_hold = mean P_hold / 3 MW")
plt.colorbar(im, ax=axs[1], shrink=.8)
im = pm(axs[2], z["P2"]*100, 0, 60, "viridis", "% of hours with P_hold > 2 MW")
plt.colorbar(im, ax=axs[2], shrink=.8)
plt.tight_layout(); plt.savefig(OUT/"a1_annual_maps.png", dpi=110)
fig, axs = plt.subplots(2, 4, figsize=(15, 7.5))
for k, s in enumerate(SEASONS):
    im = pm(axs[0,k], z[f"P_{s}"]/3000, 0.0, 0.75, "viridis", f"{s} CF_hold")
    im2 = pm(axs[1,k], z[f"P2_{s}"]*100, 0, 80, "viridis", f"{s} % hours P_hold>2 MW")
plt.colorbar(im, ax=axs[0], shrink=.8); plt.colorbar(im2, ax=axs[1], shrink=.8)
plt.savefig(OUT/"a1_seasonal_maps.png", dpi=90, bbox_inches="tight")
# hist + hold curve
fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
H = np.array(r["hist_tws_kn"])[:45]*100
ax[0].bar(np.arange(45)+.5, H, color="#4c78a8"); ax[0].set_xlabel("TWS [kn]"); ax[0].set_ylabel("% of cell-hours")
c = np.array(r["hold_curve_kn_kw"]); a2 = ax[0].twinx(); a2.plot(c[:,0], c[:,1]/1000, "k-"); a2.set_ylabel("P_hold [MW] (black)"); a2.set_xlim(0,45)
for s,col in zip(SEASONS, ["#1f77b4","#2ca02c","#d62728","#ff7f0e"]):
    pass
ax[1].plot(range(1,13), r["monthly_CF_hold_basin"], "o-"); ax[1].set_xlabel("month"); ax[1].set_ylabel("basin-mean CF_hold"); ax[1].set_ylim(0,0.7)
plt.tight_layout(); plt.savefig(OUT/"a1_hist_monthly.png", dpi=100)
