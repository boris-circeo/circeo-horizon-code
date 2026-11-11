"""A4b: perfect-foresight DP 'oracle' on the hold-power field (free movement) vs ship speed; oracle path vs system velocity."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from scipy.ndimage import maximum_filter
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r"); n = uv.shape[0]; ny, nx = g.shape
mon = month_of_hour(arc)
lon, lat = g.lonlat_mesh()
okp = np.isfinite(ph)
STEP = 3
nt = n // STEP
P3 = np.empty((nt, ny, nx), np.float32)
for k in range(0, nt, 100):
    k1 = min(nt, k+100)
    a = np.asarray(uv[k*STEP:k1*STEP]); w = np.hypot(a[...,0], a[...,1])/KN
    p = np.interp(w, tws/KN, np.where(okp, ph, 0.0))/3000
    P3[k:k1] = p.reshape(k1-k, STEP, ny, nx).mean(1)
NEG = np.float32(-1e9)
P3m = np.where(sea[None], P3, NEG)
# S4 start
x0, y0 = g.to_xy(-21.6, 56.49); j0, i0 = g.index_of(x0, y0); j0, i0 = int(j0), int(i0)
print("start cell", j0, i0, sea[j0, i0])
def disc(r):
    R = int(np.ceil(r)); yy, xx = np.mgrid[-R:R+1, -R:R+1]
    return (yy**2 + xx**2) <= r*r + 1e-9
res = {"start": [j0, i0], "fixed_point_CF_at_start": float(P3[:, j0, i0].mean()),
       "fixed_best_cell_CF": float(np.where(sea, P3.mean(0), -1).max()), "year_mean_CF_all_cells": float(P3[:, sea].mean())}
best_cell_idx = np.unravel_index(np.argmax(np.where(sea, P3.mean(0), -1)), (ny, nx))
res["fixed_best_cell"] = [int(best_cell_idx[0]), int(best_cell_idx[1])]
speeds = [0, 2, 4, 6, 8, 12, 16, 24, 32]
res["sweep"] = {}
paths = {}
for v in speeds:
    r = v*STEP*3600/40e3
    fp = disc(r)
    V = np.zeros((nt+1, ny, nx), np.float32)
    for t in range(nt-1, -1, -1):
        nxt = V[t+1]
        mf = maximum_filter(np.where(sea, nxt, NEG), footprint=fp, mode="constant", cval=NEG) if v > 0 else nxt
        V[t] = np.where(sea, P3[t] + mf, NEG)
    cf0 = V[0]/nt
    out = {"radius_cells_per_step": r, "CF_oracle_from_S4_start": float(cf0[j0, i0]), "CF_oracle_best_start": float(np.where(sea, cf0, -1).max()),
           "CF_oracle_mean_over_all_starts": float(cf0[sea].mean())}
    # monthly CF along oracle path from S4 start
    j, i = j0, i0; pj = []; pi_ = []; pw = []
    for t in range(nt):
        pj.append(j); pi_.append(i); pw.append(P3[t, j, i])
        if v > 0:
            # best reachable next
            R = int(np.ceil(r)); jl, jh = max(0, j-R), min(ny, j+R+1); il, ih = max(0, i-R), min(nx, i+R+1)
            sub = V[t+1, jl:jh, il:ih].copy()
            fsub = fp[(jl-(j-R)):(jh-(j-R)), (il-(i-R)):(ih-(i-R))]
            sub = np.where(fsub & sea[jl:jh, il:ih], sub, NEG)
            kk = np.unravel_index(np.argmax(sub), sub.shape); j, i = jl+kk[0], il+kk[1]
    pj = np.array(pj); pi_ = np.array(pi_); pw = np.array(pw)
    mm = mon[np.arange(nt)*STEP]
    out["monthly_CF_path"] = [float(pw[mm == m].mean()) for m in range(1, 13)]
    out["season_CF_path"] = {sn: float(pw[np.isin(mm, ms)].mean()) for sn, ms in SEASONS.items()}
    paths[v] = (pj, pi_)
    res["sweep"][str(v)] = out
    print(v, {k: round(x, 3) for k, x in out.items() if isinstance(x, float)}, flush=True)
# relation of oracle path velocity to system velocity (block advection velocity from dt6 pairs)
z = np.load(OUT/"a3_adv_dt6.npz"); best, peak, ts, TS, BS = z["best"], z["peak"], z["ts"], int(z["TS"]), int(z["BS"])
nbj, nbi = best.shape[1:3]
cj, ci = np.mgrid[0:ny, 0:nx]
bj = np.clip(np.round((cj-(BS*TS/2-0.5))/TS).astype(int), 0, nbj-1); bi = np.clip(np.round((ci-(BS*TS/2-0.5))/TS).astype(int), 0, nbi-1)
tsl = {int(t): k for k, t in enumerate(ts)}
res["path_vs_system"] = {}
for v in (4, 8, 16):
    pj, pi_ = paths[v]
    dj = np.diff(pj).astype(float); di = np.diff(pi_).astype(float)
    ds = np.hypot(dj, di); mv = ds > 0
    cos = []; ratio = []; proj = []; cmag = []; shipspd = []
    for t in range(1, nt-2):
        if not mv[t]: continue
        k = tsl.get(t*STEP)
        if k is None: continue
        c = best[k, bj[pj[t], pi_[t]], bi[pj[t], pi_[t]]]   # cells per 6 h (east, north)
        if not np.all(np.isfinite(c)) or np.hypot(*c) < 0.3: continue
        c3 = c/2                                              # cells per 3 h
        sv = np.array([di[t], dj[t]])
        cos.append(sv@c3/(np.hypot(*sv)*np.hypot(*c3))); proj.append(sv@c3/np.hypot(*c3)*40/3/1.852); cmag.append(np.hypot(*c3)*40/3/1.852); shipspd.append(np.hypot(*sv)*40/3/1.852)
    cos = np.array(cos)
    res["path_vs_system"][str(v)] = {"frac_steps_moving": float(mv.mean()), "n": int(cos.size), "mean_cos_angle": float(cos.mean()),
        "frac_within_45deg_of_system_motion": float((cos > np.cos(np.radians(45))).mean()), "frac_opposite_gt90": float((cos < 0).mean()),
        "mean_ship_speed_when_moving_kn": float(np.mean(shipspd)), "mean_system_speed_kn": float(np.mean(cmag)),
        "mean_ship_velocity_component_along_system_kn": float(np.mean(proj))}
    print(v, res["path_vs_system"][str(v)])
json.dump(res, open(OUT/"a4b.json", "w"), indent=1)
