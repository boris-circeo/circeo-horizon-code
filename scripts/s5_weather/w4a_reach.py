"""A4a: reachable-better-wind statistics (static reach, free movement) for ship speeds 4 and 8 m/s."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
g, arc, sea, land, env, tws, ph = setup()
z = np.load(OUT/"sea_series.npz"); W = z["W"].astype(np.float32); jj, ii = z["jj"], z["ii"]
n, nc = W.shape; mon = month_of_hour(arc)
P = (np.interp(W, tws/KN, np.where(np.isfinite(ph), ph, 0.0))/3000).astype(np.float32)   # CF_hold
idx = -np.ones(sea.shape, int); idx[jj, ii] = np.arange(nc)
rows, cols, w = [], [], []
nb = [(a, b) for a in range(-2, 3) for b in range(-2, 3) if (a, b) != (0, 0) and np.gcd(abs(a), abs(b)) == 1]
for dj, di in nb:
    j2 = jj+dj; i2 = ii+di; ok = (j2 >= 0) & (j2 < sea.shape[0]) & (i2 >= 0) & (i2 < sea.shape[1])
    k2 = np.where(ok, idx[np.clip(j2, 0, sea.shape[0]-1), np.clip(i2, 0, sea.shape[1]-1)], -1)
    m = k2 >= 0
    rows.append(np.arange(nc)[m]); cols.append(k2[m]); w.append(np.full(m.sum(), 40.0*np.hypot(dj, di)))
Gm = coo_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))), shape=(nc, nc)).tocsr()
D = dijkstra(Gm, directed=False, limit=2200.0).astype(np.float32)   # km
print("dist done", np.isfinite(D).mean())
cs = np.vstack([np.zeros((1, nc), np.float32), np.cumsum(P, 0, dtype=np.float64).astype(np.float32)])  # fine for window means? use float64
cs = np.vstack([np.zeros((1, nc)), np.cumsum(P.astype(np.float64), 0)])
def wmean(t0, T):   # mean over [t0, t0+T) for array of t0 (n_t,)  -> (n_t, nc)
    return (cs[t0+T] - cs[t0])/T
res = {}
for v in (4.0, 8.0):
    for T in (6, 24, 72):
        Rk = v*T*3.6   # km
        reach = D <= Rk
        t0 = np.arange(0, n - 2*T, 12)
        Pnow = P[t0]                                     # (nt, nc)
        Mf = wmean(t0 + T, T)                            # future window mean at each cell
        loc = Mf; 
        snap_best = np.empty_like(Pnow); pers = np.empty_like(Pnow); fore = np.empty_like(Pnow); nowloc = Pnow
        for x in range(nc):
            r = np.nonzero(reach[x])[0]
            Pr = Pnow[:, r]
            snap_best[:, x] = Pr.max(1)
            ar = Pr.argmax(1)
            pers[:, x] = Mf[:, r][np.arange(t0.size), ar]
            fore[:, x] = Mf[:, r].max(1)
        ms = mon[t0]
        def sm(A): return {"year": float(A.mean()), **{sn: float(A[np.isin(ms, mm)].mean()) for sn, mm in SEASONS.items()}}
        r_ = {"reach_km": Rk, "mean_cells_in_reach": float(reach.sum(1).mean()),
              "local_now_CF": sm(nowloc), "snapshot_best_reachable_now_CF": sm(snap_best),
              "local_future_CF": sm(loc), "persistence_relocation_future_CF": sm(pers), "foresight_relocation_future_CF": sm(fore),
              "frac_local_future_below_0.5": float((loc < 0.5).mean()),
              "gain_persistence_when_local_future_lt_0.4": float((pers - loc)[loc < 0.4].mean()), "gain_foresight_when_local_future_lt_0.4": float((fore - loc)[loc < 0.4].mean())}
        res[f"v{v:g}_T{T}"] = r_
        print(f"v{v} T{T}h R={Rk:.0f}km  now {r_['local_now_CF']['year']:.3f} snapbest {r_['snapshot_best_reachable_now_CF']['year']:.3f} | future: local {r_['local_future_CF']['year']:.3f} pers {r_['persistence_relocation_future_CF']['year']:.3f} fore {r_['foresight_relocation_future_CF']['year']:.3f}", flush=True)
json.dump(res, open(OUT/"a4a.json", "w"), indent=1)
