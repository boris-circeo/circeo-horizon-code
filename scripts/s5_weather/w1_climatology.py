"""A1: TWS distribution, hold power maps, seasonal, productive band."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT / "uv_2015.npy", mmap_mode="r")
mk = np.load(OUT / "masks.npz"); lon, lat = mk["lon"], mk["lat"]
ok = np.isfinite(ph)
n = uv.shape[0]
ny, nx = g.shape
S = np.zeros((ny, nx)); S2 = np.zeros((ny, nx))
seas = season_masks(arc); mon = month_of_hour(arc)
Psum = {s: np.zeros((ny, nx)) for s in SEASONS}; Tsum = {s: np.zeros((ny, nx)) for s in SEASONS}
Pm = np.zeros((12, ny, nx)); Tm = np.zeros((12, ny, nx))
cnt = {s: 0 for s in SEASONS}
hist = np.zeros(80); histS = {s: np.zeros(80) for s in SEASONS}
bands = {"calm<10":lambda w:w<10, "10-14":lambda w:(w>=10)&(w<14), "14-18":lambda w:(w>=14)&(w<18),
         "18-26":lambda w:(w>=18)&(w<=26), ">26":lambda w:w>26, "P>2MW":None}
share = {s:{k:0.0 for k in bands} for s in list(SEASONS)+["year"]}
P2 = np.zeros((ny,nx)); P2s={s:np.zeros((ny,nx)) for s in SEASONS}
ncell = sea.sum()
for h0 in range(0, n, 168):
    h1 = min(n, h0+168)
    a = np.asarray(uv[h0:h1])
    w = np.hypot(a[...,0], a[...,1])/KN
    P = np.interp(w, tws/KN, np.where(ok, ph, 0.0)).astype(np.float64)
    for t in range(h1-h0):
        m = mon[h0+t]; s = [k for k,v in SEASONS.items() if m in v][0]
        Pm[m-1] += P[t]; Tm[m-1] += w[t]
        Psum[s] += P[t]; Tsum[s] += w[t]; cnt[s] += 1
        ws = w[t][sea]; Ps = P[t][sea]
        hh = np.bincount(np.minimum(ws.astype(int), 79), minlength=80)
        hist += hh; histS[s] += hh
        for k, f in bands.items():
            c = (Ps > 2000).sum() if f is None else f(ws).sum()
            share[s][k] += c; share["year"][k] += c
        P2[...] += (P[t] > 2000); P2s[s] += (P[t] > 2000)
nh = np.array([m for m in arc._hours])
cnt_y = n
res = {}
Pyear = Pm.sum(0)/n; Tyear = Tm.sum(0)/n
np.savez(OUT/"a1_maps.npz", Pyear=Pyear, Tyear=Tyear, Pm=Pm/nh[:,None,None], Tm=Tm/nh[:,None,None],
         **{f"P_{s}": Psum[s]/cnt[s] for s in SEASONS}, **{f"T_{s}": Tsum[s]/cnt[s] for s in SEASONS},
         P2=P2/n, **{f"P2_{s}": P2s[s]/cnt[s] for s in SEASONS})
for s in share:
    nn = (cnt_y if s=="year" else cnt[s]) * ncell
    res[s] = {k: 100*v/nn for k,v in share[s].items()}
    P_ = Pyear if s=="year" else Psum[s]/cnt[s]; T_ = Tyear if s=="year" else Tsum[s]/cnt[s]
    res[s].update(meanTWS=float(T_[sea].mean()), meanPhold=float(P_[sea].mean()),
                  CF_hold=float(P_[sea].mean()/3000), p10_Phold_cell=float(np.percentile(P_[sea],10)),
                  p90_Phold_cell=float(np.percentile(P_[sea],90)), max_cell_CF=float(P_[sea].max()/3000),
                  min_cell_CF=float(P_[sea].min()/3000))
H = hist/hist.sum(); cum = np.cumsum(H)
res["tws_quantiles_kn"] = {q: float(np.searchsorted(cum, q/100)) for q in (5,10,25,50,75,90,95)}
# monthly basin CF_hold and spread
res["monthly_CF_hold_basin"] = [float((Pm[i]/nh[i])[sea].mean()/3000) for i in range(12)]
res["monthly_meanTWS_basin"] = [float((Tm[i]/nh[i])[sea].mean()) for i in range(12)]
# latitude bands
latb = [(35,40),(40,45),(45,50),(50,55),(55,60),(60,65)]
res["lat_band"] = {}
for a_,b_ in latb:
    mm = sea & (lat>=a_) & (lat<b_)
    res["lat_band"][f"{a_}-{b_}"] = dict(n=int(mm.sum()), CF=float(Pyear[mm].mean()/3000),
        **{s: float((Psum[s]/cnt[s])[mm].mean()/3000) for s in SEASONS})
# 'productive band' extent: fraction of sea cells with CF_hold>0.5 / 0.6 per season
res["frac_cells_CF_gt"] = {s:{str(th): float(((Psum[s]/cnt[s]/3000)[sea]>th).mean()) for th in (0.4,0.5,0.6,0.7)} for s in SEASONS}
res["frac_cells_CF_gt"]["year"] = {str(th): float((Pyear[sea]/3000>th).mean()) for th in (0.4,0.5,0.6,0.7)}
i = np.unravel_index(np.argmax(np.where(sea,Pyear,-1)), Pyear.shape)
res["best_cell"] = dict(lon=float(lon[i]), lat=float(lat[i]), CF=float(Pyear[i]/3000))
res["hist_tws_kn"] = H.tolist()
res["hold_curve_kn_kw"] = [[float(a/KN), float(b)] for a,b in zip(tws, ph)][::2]
json.dump(res, open(OUT/"a1.json","w"), indent=1)
print(json.dumps({k:v for k,v in res.items() if k not in("hist_tws_kn","hold_curve_kn_kw")}, indent=1))
