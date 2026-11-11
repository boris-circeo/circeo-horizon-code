"""A2: Eulerian run-length statistics at fixed sea cells."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r")
ok = np.isfinite(ph)
jj, ii = np.nonzero(sea); nc = jj.size; n = uv.shape[0]
W = np.empty((n, nc), np.float32)
for h0 in range(0, n, 500):
    a = np.asarray(uv[h0:h0+500])[:, jj, ii]
    W[h0:h0+500] = np.hypot(a[...,0], a[...,1])/KN
P = np.interp(W, tws/KN, np.where(ok, ph, 0.0)).astype(np.float32)
np.savez(OUT/"sea_series.npz", W=W.astype(np.float16), jj=jj, ii=ii)
mon = month_of_hour(arc)
conds = {"TWS18-26": (W>=18)&(W<=26), "Phold>2MW": P>2000, "calm<10": W<10, "TWS<14": W<14}

def runs(b):
    """return start idx, length of True runs (and False runs between, interior only)"""
    d = np.diff(np.concatenate([[0], b.astype(np.int8), [0]]))
    s = np.nonzero(d==1)[0]; e = np.nonzero(d==-1)[0]
    return s, e - s
def fill_gaps(b, gmax):
    s, L = runs(b)
    if s.size < 2: return b
    gaps = s[1:] - (s[:-1]+L[:-1])
    out = b.copy()
    for k in np.nonzero(gaps<=gmax)[0]:
        out[s[k]+L[k]: s[k+1]] = True
    return out
res = {}
Ls = [1,3,6,12,24,48,72,120,168]
for name, B in conds.items():
    for gmax in (0, 3):
        L_all=[]; start_all=[]; gap_all=[]; gap_start=[]; frac=[]
        for c in range(nc):
            b = B[:, c]
            if gmax: b = fill_gaps(b, gmax)
            s, L = runs(b)
            L_all.append(L); start_all.append(s)
            if s.size>1:
                gap_all.append(s[1:]-(s[:-1]+L[:-1])); gap_start.append(s[:-1]+L[:-1])
            frac.append(b.mean())
        L = np.concatenate(L_all); st = np.concatenate(start_all)
        G = np.concatenate(gap_all); gs = np.concatenate(gap_start)
        def stats(L, st):
            o = {"n_episodes_per_cell_year": len(L)/nc, "mean_h": float(L.mean()), "median_h": float(np.median(L)),
                 "p25": float(np.percentile(L,25)), "p75": float(np.percentile(L,75)), "p90": float(np.percentile(L,90)),
                 "time_weighted_median_h": float(np.sort(L)[np.searchsorted(np.cumsum(np.sort(L)), L.sum()/2)]),
                 "frac_time_in_episodes_ge": {str(x): float(L[L>=x].sum()/L.sum()) for x in Ls},
                 "frac_episodes_ge": {str(x): float((L>=x).mean()) for x in Ls}}
            return o
        r = {"cell_frac": float(np.mean(frac)), "episodes": stats(L, st), "gaps": stats(G, gs)}
        # seasonal by episode start
        r["season_episode_median_mean"] = {}
        for sname, ms in SEASONS.items():
            sel = np.isin(mon[st], ms); selg = np.isin(mon[gs], ms)
            r["season_episode_median_mean"][sname] = {
              "ep_median": float(np.median(L[sel])), "ep_mean": float(L[sel].mean()), "ep_tw_ge24": float(L[sel][L[sel]>=24].sum()/L[sel].sum()),
              "gap_median": float(np.median(G[selg])), "gap_mean": float(G[selg].mean()), "gap_p90": float(np.percentile(G[selg],90))}
        res[f"{name}|gapfill{gmax}"] = r
# waiting time from a non-productive hour to the next productive hour (strict P>2MW), per season of the waiting start
B = conds["Phold>2MW"]
wait = []; wst = []
for c in range(0, nc, 3):
    b = B[:, c]
    idx = np.nonzero(b)[0]
    if idx.size == 0: continue
    nxt = np.searchsorted(idx, np.arange(n))
    ok_ = (~b) & (nxt < idx.size)
    w = idx[np.minimum(nxt, idx.size-1)] - np.arange(n)
    wait.append(w[ok_]); wst.append(np.nonzero(ok_)[0])
wait = np.concatenate(wait); wst = np.concatenate(wst)
res["wait_to_next_Phold>2MW_h"] = {"overall": {q: float(np.percentile(wait, q)) for q in (50,75,90,95,99)}, "mean": float(wait.mean())}
for sname, ms in SEASONS.items():
    w = wait[np.isin(mon[wst], ms)]
    res["wait_to_next_Phold>2MW_h"][sname] = {q: float(np.percentile(w, q)) for q in (50,75,90,95,99)}
# fraction of cell-time in a 72 h window with zero productive hours (long droughts), by season
Bf = B.astype(np.float32)
cs = np.cumsum(np.vstack([np.zeros((1,nc),np.float32), Bf]), 0)
for win in (24,72,168):
    s = cs[win:] - cs[:-win]
    res[f"frac_windows_{win}h_with_zero_productive"] = {"year": float((s==0).mean()),
        **{sn: float((s[np.isin(mon[:n-win+1], ms)]==0).mean()) for sn, ms in SEASONS.items()}}
# monthly (sampling) std of cell fraction productive
json.dump(res, open(OUT/"a2.json","w"), indent=1)
for k,v in res.items():
    if "|" in k: print(k, "cellfrac %.3f"%v["cell_frac"], {a:round(b,2) for a,b in v["episodes"].items() if not isinstance(b,dict)}, "gap med/mean/p90", v["gaps"]["median_h"], round(v["gaps"]["mean_h"],1), v["gaps"]["p90"], "tw>=24:", round(v["episodes"]["frac_time_in_episodes_ge"]["24"],2))
print(res["wait_to_next_Phold>2MW_h"]); print({k:v for k,v in res.items() if k.startswith("frac_win")})
print(res["Phold>2MW|gapfill0"]["season_episode_median_mean"])
