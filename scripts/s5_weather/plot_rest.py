import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25})
C = ["#1b6ca8", "#d95f02", "#2a9d5c", "#7b4fa3", "#555555"]
g, arc, sea, land, env, tws, ph = setup(); mon = month_of_hour(arc)
z = np.load(OUT/"sea_series.npz"); W = z["W"].astype(np.float32); n, nc = W.shape
P = np.interp(W, tws/KN, np.where(np.isfinite(ph), ph, 0.0))
def runs(b):
    d = np.diff(np.concatenate([[0], b.astype(np.int8), [0]])); s = np.nonzero(d == 1)[0]; e = np.nonzero(d == -1)[0]; return s, e-s
def pool(B, mask_months=None):
    L = []; G = []
    for c in range(0, nc, 2):
        s, l = runs(B[:, c]); L.append(l)
        if s.size > 1: G.append(s[1:]-(s[:-1]+l[:-1]))
    return np.concatenate(L), np.concatenate(G)
fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
for B, lab, col in ((P > 2000, "P_hold > 2 MW", C[0]), ((W >= 18) & (W <= 26), "TWS 18-26 kn", C[1]), (W < 10, "calm < 10 kn", C[4])):
    L, G = pool(B)
    xs = np.arange(1, 241)
    ax[0].plot(xs, [(L <= x).mean() for x in xs], color=col, label=lab)
    ax[1].plot(xs, [L[L <= x].sum()/L.sum() for x in xs], color=col, label=lab)
    ax[2].plot(xs, [(G <= x).mean() for x in xs], color=col, label=lab)
ax[0].set_title("episode length, share of EPISODES <= x"); ax[1].set_title("share of TIME spent in episodes <= x"); ax[2].set_title("gap between episodes (return time), CDF")
for a in ax: a.set_xlabel("hours"); a.set_xscale("log"); a.set_xlim(1, 240)
ax[0].legend(); plt.tight_layout(); plt.savefig(OUT/"a2_runlengths.png", dpi=100)
# --- A3 composite
a3 = json.load(open(OUT/"a3a.json")); sp = np.load(OUT/"a3_spatial_acf.npz"); b3 = json.load(open(OUT/"a3b.json")); c3 = json.load(open(OUT/"a3c.json"))
fig, ax = plt.subplots(2, 3, figsize=(13, 7.2))
lags = [1, 3, 6, 12, 24, 48, 72, 96, 120, 168, 240]
a = ax[0, 0]
a.plot(lags, [a3["temporal"]["tws_anom"]["acf_at_h"][str(h)] for h in lags], "o-", color=C[0], label="TWS anomaly")
a.plot(lags, [a3["temporal"]["wind_vector_anom"]["acf_at_h"][str(h)] for h in lags], "s-", color=C[1], label="wind vector anomaly")
a.plot([1, 3, 6, 12, 24, 48, 72, 120, 240], [a3["temporal"]["indicator_Phold>2MW"]["acf_at_h"][str(h)] for h in (1, 3, 6, 12, 24, 48, 72, 120, 240)], "^-", color=C[2], label="indicator P_hold>2 MW")
a.axhline(1/np.e, color="k", lw=.6, ls="--"); a.set_xscale("log"); a.set_xlabel("lag [h]"); a.set_title("temporal autocorrelation at a fixed point"); a.legend()
a = ax[0, 1]
R = int(sp["R"]); Cv = sp["Cv"].copy()
for dj in range(1, R+1): Cv[R-dj, 0] = Cv[R+dj, 0]
full = np.concatenate([Cv[::-1, ::-1][:, :-1], Cv], axis=1)
ext = [-R*40, R*40, -R*40, R*40]
im = a.imshow(full, origin="lower", extent=ext, cmap="viridis", vmin=0, vmax=1); a.contour(np.linspace(-R*40, R*40, 2*R+1), np.linspace(-R*40, R*40, 2*R+1), full, [1/np.e], colors="w")
a.set_title("spatial correlation of wind-vector anomaly\n(white: 1/e)"); a.set_xlabel("east [km]"); a.set_ylabel("north [km]"); a.grid(False); plt.colorbar(im, ax=a, shrink=.8)
a = ax[0, 2]
zz = np.load(OUT/"a3_adv_dt6.npz"); best, peak, bm, bs = zz["best"], zz["peak"], zz["bmean"], zz["bsea"]
spd = np.hypot(best[..., 0], best[..., 1])*40e3/(6*3600)/KN
ok = np.isfinite(spd) & (peak >= .5) & (bs >= .8)[None]
bins = np.arange(0, 46, 2)
for sel, lab, col in ((ok, "all blocks", C[4]), (ok & (bm >= 16), "blocks with mean TWS >= 16 kn", C[0]), (ok & (bm < 12), "blocks with mean TWS < 12 kn", C[1])):
    h, _ = np.histogram(spd[sel], bins=bins); a.step(bins[:-1], h/h.sum()*100, where="post", color=col, label=lab)
a.axvline(7.8, color="k", ls="--", lw=.8); a.text(8.3, a.get_ylim()[1]*.92, "ship 4 m/s", fontsize=7); a.axvline(15.6, color="k", ls=":", lw=.8); a.text(16, a.get_ylim()[1]*.82, "ship 8 m/s", fontsize=7)
a.set_xlabel("pattern translation speed [kn]"); a.set_ylabel("% of blocks"); a.set_title("speed of wind-speed anomaly patterns (800 km blocks, 6 h lag)"); a.legend(fontsize=7)
a = ax[1, 0]
taus = [6, 12, 24, 48]
for k, lab, col in (("static", "stay at the cell (Eulerian)", C[0]), ("ship_7.8kn", "follow the system at <= 7.8 kn", C[2]), ("ship_15.6kn", "follow at <= 15.6 kn", C[3]), ("full_system", "move with the system velocity", C[1])):
    a.plot(taus, [c3["cond_prob_productive"][str(t)][k] for t in taus], "o-", color=col, label=lab)
a.plot(taus, [c3["unconditional"][str(t)] for t in taus], "k--", label="unconditional frequency"); a.set_ylim(0, 1)
a.set_xlabel("lead tau [h]"); a.set_title("P(productive at t+tau | productive at t)"); a.legend(fontsize=7)
a = ax[1, 1]
for s, col in zip(SEASONS, C):
    a.plot(taus, [c3["by_season"][s][str(t)]["full_system"] - c3["by_season"][s][str(t)]["static"] for t in taus], "o-", color=col, label=s)
a.axhline(0, color="k", lw=.6); a.set_xlabel("lead tau [h]"); a.set_title("gain of riding the system vs staying (probability points)"); a.legend()
a = ax[1, 2]
dts = (3, 6)
vals = {sn: b3["dt6_q0.5"][sn+"_prod16"]["median_kn"] for sn in SEASONS}
a.bar(list(vals), list(vals.values()), color=C[0]); a.axhline(7.8, color="k", ls="--", lw=.8); a.axhline(15.6, color="k", ls=":", lw=.8)
a.set_ylabel("median speed [kn]"); a.set_title("median pattern speed in productive blocks, by season\n(dashed: ship 4 m/s, dotted: 8 m/s)")
plt.tight_layout(); plt.savefig(OUT/"a3_spacetime.png", dpi=95)
# --- A4
b = json.load(open(OUT/"a4b.json")); c = json.load(open(OUT/"a4c.json")); a4a = json.load(open(OUT/"a4a.json"))
fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
v = [0, 4, 6, 8, 12, 16, 24, 32]
ax[0].plot(v, [b["sweep"][str(x)]["CF_oracle_from_S4_start"] for x in v], "o-", color=C[0]); ax[0].axhline(0.572, color="k", ls=":", lw=.8)
ax[0].axvline(4, color=C[4], ls="--", lw=.7); ax[0].axvline(8, color=C[4], ls="--", lw=.7); ax[0].set_xlabel("ship speed [m/s]"); ax[0].set_ylabel("annual CF_hold-oracle"); ax[0].set_title("perfect-foresight DP (hold power, free movement)\nvs ship speed; dotted: fixed point")
for vv, col in zip((4, 8, 16), C):
    ax[1].plot([80, 160, 320, 640, 1280], [c[f"R{R}_v{vv}"] for R in (80, 160, 320, 640, 1280)], "o-", color=col, label=f"{vv} m/s")
ax[1].set_xscale("log"); ax[1].set_xlabel("max distance from start [km]"); ax[1].set_title("oracle CF when confined to a disc"); ax[1].legend()
Ts = [6, 24, 72]
for vv, ls in ((4.0, "-"), (8.0, "--")):
    for key, lab, col in (("local_future_CF", "stay", C[4]), ("persistence_relocation_future_CF", "relocate to best-now (persistence)", C[1]), ("foresight_relocation_future_CF", "relocate with foresight", C[0])):
        ax[2].plot(Ts, [a4a[f"v{vv:g}_T{T}"][key]["year"] for T in Ts], ls, marker="o", color=col, label=(lab if vv == 4.0 else None))
ax[2].set_xlabel("T [h] (reach = v T; solid 4 m/s, dashed 8 m/s)"); ax[2].set_xscale("log"); ax[2].set_xticks(Ts); ax[2].set_xticklabels(Ts); ax[2].set_title("mean CF_hold over [t+T, t+2T]"); ax[2].legend(fontsize=7)
plt.tight_layout(); plt.savefig(OUT/"a4_mobility.png", dpi=100)
# --- A5
import os
f = OUT/"a5.json"
if f.exists():
    r = json.load(open(f)); L = np.array(r["leads_h"])/24
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    ax[0].plot(L, r["BSS_forecast_vs_clim"], color=C[0], label="forecast v2 vs annual clim")
    if "BSS_forecast_vs_seasonal_clim" in r: ax[0].plot(L, r["BSS_forecast_vs_seasonal_clim"], "--", color=C[0], label="forecast v2 vs seasonal clim")
    ax[0].plot(L, r["BSS_calibrated_persistence_vs_clim"], color=C[1], label="calibrated persistence"); ax[0].axhline(0, color="k", lw=.6)
    ax[0].set_xlabel("lead [days]"); ax[0].set_title("Brier skill score, event P_hold > 2 MW at a cell"); ax[0].legend(fontsize=7)
    ax[1].plot(L, r["ACC_ens_mean"], color=C[0], label="ensemble mean"); ax[1].plot(L, r["ACC_control"], color=C[2], label="control"); ax[1].plot(L, r["ACC_persistence"], color=C[1], label="persistence")
    ax[1].axhline(0.6, color="k", ls="--", lw=.6); ax[1].set_xlabel("lead [days]"); ax[1].set_title("anomaly correlation of TWS"); ax[1].legend(fontsize=7)
    plt.tight_layout(); plt.savefig(OUT/"a5_predictability.png", dpi=100)
