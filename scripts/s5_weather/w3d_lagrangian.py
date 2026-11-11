"""A3c: Lagrangian vs Eulerian persistence of productive wind, patch sizes and residence times."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from scipy import ndimage as ndi
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r"); n = uv.shape[0]; ny, nx = g.shape
mon = month_of_hour(arc)
z = np.load(OUT/"a3_adv_dt6.npz"); best, peak, ts, TS, BS = z["best"], z["peak"], z["ts"], int(z["TS"]), int(z["BS"])
DT = 6; nbj, nbi = best.shape[1:3]
# velocity per block [cells / 6h]
okc = (ph[:]!=None)
okp = np.isfinite(ph)
P = np.empty((n, ny, nx), np.float16)
for h0 in range(0, n, 500):
    a = np.asarray(uv[h0:h0+500]); w = np.hypot(a[...,0], a[...,1])/KN
    P[h0:h0+500] = np.interp(w, tws/KN, np.where(okp, ph, 0.0))
Ind = (P.astype(np.float32) > 2000)
# cell -> nearest block
cj, ci = np.mgrid[0:ny, 0:nx]
bj = np.clip(np.round((cj - (BS*TS/2 - 0.5))/TS).astype(int), 0, nbj-1)
bi = np.clip(np.round((ci - (BS*TS/2 - 0.5))/TS).astype(int), 0, nbi-1)
tsl = {int(t): k for k, t in enumerate(ts)}
taus = [6, 12, 24, 48]
ships = {"static": 0.0, "ship_7.8kn": 7.8, "ship_15.6kn": 15.6, "full_system": None}
acc = {tau: {k: [0, 0] for k in ships} for tau in taus}   # [productive at dest, total]
base_acc = {tau: [0, 0] for tau in taus}
seas_acc = {sn: {tau: {k: [0, 0] for k in ships} for tau in taus} for sn in SEASONS}
dxkm = 40.0
for t in range(12, n-50, 6):
    k = tsl.get(t-6)
    if k is None: continue
    vel = best[k]            # (nbj, nbi, 2) cells per 6h  (x=east, y=north)
    vq = peak[k]
    src = Ind[t] & sea
    jj, ii = np.nonzero(src)
    if jj.size == 0: continue
    v = vel[bj[jj, ii], bi[jj, ii]]       # cells/6h
    good = np.isfinite(v[:, 0]) & (vq[bj[jj, ii], bi[jj, ii]] > 0.5)
    jj, ii, v = jj[good], ii[good], v[good]
    sp = np.hypot(v[:, 0], v[:, 1])       # cells per 6h
    sp_kn = sp*dxkm*1e3/(6*3600)/KN
    u = v/np.maximum(sp, 1e-9)[:, None]   # unit
    s_name = [sn for sn, ms in SEASONS.items() if mon[t] in ms][0]
    for tau in taus:
        for name, vs in ships.items():
            if vs is None: disp = v*(tau/6)
            else:
                f = np.minimum(vs, sp_kn)/np.maximum(sp_kn, 1e-9)   # ship follows direction of system, speed capped at ship speed
                disp = v*(tau/6)*f[:, None]
            j2 = np.round(jj + disp[:, 1]).astype(int); i2 = np.round(ii + disp[:, 0]).astype(int)
            inb = (j2 >= 0) & (j2 < ny) & (i2 >= 0) & (i2 < nx)
            j2c = np.clip(j2, 0, ny-1); i2c = np.clip(i2, 0, nx-1)
            val = inb & sea[j2c, i2c]
            hit = Ind[t+tau][j2c, i2c] & val
            acc[tau][name][0] += int(hit.sum()); acc[tau][name][1] += int(val.sum())
            seas_acc[s_name][tau][name][0] += int(hit.sum()); seas_acc[s_name][tau][name][1] += int(val.sum())
        # baseline: unconditional productive fraction at destination (all sea cells)
        base_acc[tau][0] += int((Ind[t+tau] & sea).sum()); base_acc[tau][1] += int(sea.sum())
res = {"cond_prob_productive": {str(tau): {k: acc[tau][k][0]/max(acc[tau][k][1],1) for k in ships} for tau in taus},
       "unconditional": {str(tau): base_acc[tau][0]/base_acc[tau][1] for tau in taus},
       "by_season": {sn: {str(tau): {k: seas_acc[sn][tau][k][0]/max(seas_acc[sn][tau][k][1],1) for k in ships} for tau in taus} for sn in SEASONS}}
# patches: P>2MW connected components on sea (at 3-hourly snapshots), diameter and passage time
D = []; Tpass = []; Tship = []; Tship2 = []; spd = []
for t in range(12, n-10, 12):
    k = tsl.get(t-6)
    if k is None: continue
    lab, nl = ndi.label(Ind[t] & sea)
    if nl == 0: continue
    areas = ndi.sum(np.ones_like(lab), lab, np.arange(1, nl+1))
    cms = ndi.center_of_mass(np.ones_like(lab), lab, np.arange(1, nl+1))
    for a, (cy, cx) in zip(areas, cms):
        if a < 20: continue
        # require patch not touching the box edge/land: skip test (patches clipped by land are truncated)
        d = 2*np.sqrt(a/np.pi)*dxkm
        j, i = int(round(cy)), int(round(cx)); vv = best[k, bj[j, i], bi[j, i]]
        if not np.all(np.isfinite(vv)): continue
        c = np.hypot(*vv)*dxkm/6                  # km/h
        D.append(d); spd.append(c/1.852)
        if c > 0.5:
            Tpass.append(d/c)
            for vs, lst in ((7.8*1.852, Tship), (15.6*1.852, Tship2)):
                lst.append(d/abs(c-vs) if abs(c-vs) > 0.5 else np.inf)
D = np.array(D); Tpass = np.array(Tpass); spd = np.array(spd)
q = lambda x: {str(p): float(np.percentile(x, p)) for p in (10, 25, 50, 75, 90)}
res["patches"] = {"n": int(D.size), "equiv_diameter_km": q(D), "speed_kn": q(spd), "passage_time_static_h": q(Tpass),
                  "passage_time_ship7.8_following_h": q(np.minimum(np.array(Tship), 500)), "passage_time_ship15.6_following_h": q(np.minimum(np.array(Tship2), 500)),
                  "frac_patches_slower_than_7.8kn": float((spd < 7.8).mean()), "frac_slower_than_15.6kn": float((spd < 15.6).mean())}
json.dump(res, open(OUT/"a3c.json", "w"), indent=1)
print(json.dumps(res, indent=1))
