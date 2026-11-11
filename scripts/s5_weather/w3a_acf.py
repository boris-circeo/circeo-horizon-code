"""A3a: temporal ACF at fixed points, spatial ACF (anisotropy)."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r")
z = np.load(OUT/"sea_series.npz"); W = z["W"].astype(np.float32); jj, ii = z["jj"], z["ii"]
n, nc = W.shape; mon = month_of_hour(arc)
ok = np.isfinite(ph)
res = {}
def deseason(X):
    X = X.copy()
    for m in range(1, 13):
        s = mon == m
        X[s] -= X[s].mean(0)
    return X
def acf(X, maxlag=240):
    X = X - X.mean(0)
    f = np.fft.rfft(X, 2*n, axis=0); c = np.fft.irfft(f*np.conj(f), axis=0)[:maxlag+1]
    c /= c[0]; return c
def efold(c):
    k = np.nonzero(c < 1/np.e)[0]
    if k.size == 0: return np.nan
    k = k[0]; return k-1 + (c[k-1]-1/np.e)/(c[k-1]-c[k])
rng = np.random.default_rng(0); sel = rng.choice(nc, 1200, replace=False)
Wa = deseason(W[:, sel])
c_tws = acf(Wa)
# vector ACF: u,v anomalies
a = np.asarray(uv[:])[:, jj[sel], ii[sel]]
U = deseason(a[...,0]); V = deseason(a[...,1])
c_vec = (acf(U)*U.var(0) + acf(V)*V.var(0)).sum(1)/(U.var(0)+V.var(0)).sum()
c_vec_cells = (acf(U)*U.var(0)+acf(V)*V.var(0))/(U.var(0)+V.var(0))
Pp = np.interp(W[:, sel], tws/KN, np.where(ok, ph, 0.0)) > 2000
c_ind = acf(Pp.astype(np.float32))
cm = c_tws.mean(1)
res["temporal"] = {
  "tws_anom": {"efold_h_of_mean_acf": float(efold(cm)), "median_cell_efold": float(np.nanmedian([efold(c_tws[:,k]) for k in range(c_tws.shape[1])])),
               "acf_at_h": {str(h): float(cm[h]) for h in (1,3,6,12,24,48,72,96,120,168,240)},
               "integral_time_h": float(cm[:200].sum() - .5)},
  "wind_vector_anom": {"efold_h_of_mean_acf": float(efold(c_vec)), "acf_at_h": {str(h): float(c_vec[h]) for h in (1,3,6,12,24,48,72,96,120,168,240)}},
  "indicator_Phold>2MW": {"efold_h": float(efold(c_ind.mean(1))), "acf_at_h": {str(h): float(c_ind.mean(1)[h]) for h in (1,3,6,12,24,48,72,120,240)}}}
# seasonal e-fold of vector acf: restrict by subsetting months in the same series
for sn, ms in SEASONS.items():
    sm = np.isin(mon, ms)
    # contiguous blocks: use only series with that season (approx: compute within-season lag pairs)
    X = np.sqrt(U**2+V**2)  # not used
    # pairs (t,t+L) both in season
    out = []
    for L in (6,12,24,48,72):
        m_ = sm[:-L] & sm[L:]
        num = (U[:-L][m_]*U[L:][m_] + V[:-L][m_]*V[L:][m_]).mean(); den = (U[sm]**2+V[sm]**2).mean()
        out.append(num/den)
    res["temporal"].setdefault("vec_acf_by_season", {})[sn] = dict(zip(("6","12","24","48","72"), map(float, out)))
# ---- spatial ACF
step = 6; ts = np.arange(0, n, step)
A = np.asarray(uv[ts])  # (T,ny,nx,2)
M = sea.astype(np.float32)
Ua = A[...,0].copy(); Va = A[...,1].copy()
mt = mon[ts]
for X in (Ua, Va):
    for m in range(1, 13):
        s = mt == m
        mu = (X[s]*M).sum(0)/np.maximum(s.sum(),1)
        X[s] -= mu
Ua *= M; Va *= M
Sa = np.hypot(A[...,0], A[...,1])/KN
Sa = Sa.copy()
for m in range(1, 13):
    s = mt == m; Sa[s] -= Sa[s].mean(0)
Sa *= M
ny, nx = g.shape
R = 24  # cells = 960 km
def corr_map(Xs, norm_from=None):
    C = np.zeros((2*R+1, R+1)); 
    for dj in range(-R, R+1):
        for di in range(0, R+1):
            if di == 0 and dj < 0: continue
            j0a, j1a = max(0, -dj), min(ny, ny-dj); i0a, i1a = 0, nx-di
            num = 0.0; d1 = 0.0; d2 = 0.0
            for X in Xs:
                a_ = X[:, j0a:j1a, i0a:i1a]; b_ = X[:, j0a+dj:j1a+dj, i0a+di:i1a+di]
                num += (a_*b_).sum(); d1 += (a_*a_).sum(); d2 += (b_*b_).sum()
            C[dj+R, di] = num/np.sqrt(d1*d2)
    return C
Cv = corr_map([Ua, Va]); Cu = corr_map([Ua]); Cvv = corr_map([Va]); Cs = corr_map([Sa])
np.savez(OUT/"a3_spatial_acf.npz", Cv=Cv, Cu=Cu, Cvv=Cvv, Cs=Cs, R=R)
dx = g.dx/1e3
def efold_dir(C, theta):  # theta deg from east, counter-clockwise (y north)
    from scipy.ndimage import map_coordinates
    r = np.arange(0, R, 0.1); th = np.radians(theta)
    di = r*np.cos(th); dj = r*np.sin(th)
    sgn = np.where(di < 0, -1, 1)  # use symmetry C(-d)=C(d)
    di2 = di*sgn; dj2 = dj*sgn
    vals = map_coordinates(C, [dj2+R, di2], order=1)
    k = np.nonzero(vals < 1/np.e)[0]
    return float(r[k[0]]*dx) if k.size else np.nan
res["spatial"] = {}
for name, C in (("vector", Cv), ("u", Cu), ("v", Cvv), ("tws_anom", Cs)):
    res["spatial"][name] = {"efold_km_by_azimuth_deg_from_east": {str(t): efold_dir(C, t) for t in range(0, 180, 15)}}
    ef = np.array(list(res["spatial"][name]["efold_km_by_azimuth_deg_from_east"].values()))
    res["spatial"][name]["mean_km"] = float(np.nanmean(ef)); res["spatial"][name]["anisotropy_max_over_min"] = float(np.nanmax(ef)/np.nanmin(ef))
    # distance to zero crossing / to 0.5
    res["spatial"][name]["half_corr_km_EW_NS"] = [efold_dir(C, 0)*0, 0]
json.dump(res, open(OUT/"a3a.json","w"), indent=1)
print(json.dumps(res, indent=1))
