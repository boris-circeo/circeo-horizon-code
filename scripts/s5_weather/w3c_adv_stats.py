import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
g, arc, sea, land, env, tws, ph = setup()
mon = month_of_hour(arc)
res = {}
for DT in (3,6):
    z = np.load(OUT/f"a3_adv_dt{DT}.npz"); best, peak, c0, bm, bs, ts = (z[k] for k in ("best","peak","c0","bmean","bsea","ts"))
    vx = best[...,0]*40/3.6/DT/1.0; vy = best[...,1]*40/3.6/DT   # m/s  (km/h /3.6)
    vx = best[...,0]*40e3/(DT*3600); vy = best[...,1]*40e3/(DT*3600)
    sp = np.hypot(vx, vy)/KN; dr = (np.degrees(np.arctan2(vy, vx))) % 360
    valid_b = (bs >= 0.8)[None]
    ms = mon[ts + DT//2]
    for qmin in (0.5, 0.7):
        base = valid_b & np.isfinite(sp) & (peak >= qmin)
        out = {"n_all_pairs_blocks": int(valid_b.sum()*ts.size/ts.size), "frac_valid_kept": float(base.sum()/ (valid_b & np.ones_like(peak,bool)).sum())}
        def st(sel, label):
            s = sp[sel]
            if s.size < 50: return None
            return {"n": int(s.size), "median_kn": float(np.median(s)), "mean_kn": float(s.mean()), "p10": float(np.percentile(s,10)), "p25": float(np.percentile(s,25)),
                    "p75": float(np.percentile(s,75)), "p90": float(np.percentile(s,90)),
                    "frac_lt_4kn": float((s<4).mean()), "frac_lt_7.8kn": float((s<7.8).mean()), "frac_lt_15.6kn": float((s<15.6).mean()), "frac_gt_20kn": float((s>20).mean()), "frac_gt_30kn": float((s>30).mean()),
                    "mean_east_kn": float((vx[sel]/KN).mean()), "mean_north_kn": float((vy[sel]/KN).mean()),
                    "frac_eastward": float((np.cos(np.radians(dr[sel]))>0).mean())}
        out["all"] = st(base, "all")
        out["productive_blocks_meanTWS>=16"] = st(base & (bm >= 16), "p")
        out["strong_blocks_meanTWS>=20"] = st(base & (bm >= 20), "p")
        out["weak_blocks_meanTWS<12"] = st(base & (bm < 12), "p")
        for sn, mm in SEASONS.items():
            sel = base & np.isin(ms, mm)[:, None, None]
            out[sn] = st(sel, sn); out[sn+"_prod16"] = st(sel & (bm >= 16), sn)
        # latitude bands of block centers
        res[f"dt{DT}_q{qmin}"] = out
    # also how much of anomaly correlation is stationary: zero-lag corr vs peak
    sel = valid_b & np.isfinite(peak)
    res[f"dt{DT}_corr"] = {"mean_zero_shift_corr": float(c0[np.broadcast_to(sel,c0.shape)].mean()), "mean_peak_corr": float(peak[np.broadcast_to(sel,peak.shape)].mean()),
        "frac_blocks_peak_ge_0.5": float((peak[np.broadcast_to(sel,peak.shape)]>=0.5).mean()),
        "frac_interior": float(np.isfinite(sp[np.broadcast_to(sel,sp.shape)]).mean())}
json.dump(res, open(OUT/"a3b.json","w"), indent=1)
print(json.dumps(res, indent=1))
