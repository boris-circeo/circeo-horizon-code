"""A6: intra-year variability as a proxy for sampling noise (single year)."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
g, arc, sea, land, env, tws, ph = setup()
z = np.load(OUT/"sea_series.npz"); W = z["W"].astype(np.float32); jj, ii = z["jj"], z["ii"]
n, nc = W.shape; mon = month_of_hour(arc)
P = (np.interp(W, tws/KN, np.where(np.isfinite(ph), ph, 0.0))/3000).astype(np.float32)
res = {}
# monthly CF per cell, residual after fitting annual+semiannual harmonics
nh = np.array(arc._hours); moff = np.concatenate([[0], np.cumsum(nh)])
Mcf = np.stack([P[moff[m]:moff[m+1]].mean(0) for m in range(12)])     # (12, nc)
tm = (moff[:-1] + moff[1:])/2/8760*2*np.pi
X = np.column_stack([np.ones(12), np.cos(tm), np.sin(tm), np.cos(2*tm), np.sin(2*tm)])
beta, *_ = np.linalg.lstsq(X, Mcf, rcond=None); resid = Mcf - X@beta
# 5 params for 12 points: unbiased variance with dof 7
res["monthly_CF_resid_std_after_2harmonics_cellmedian"] = float(np.median(np.sqrt((resid**2).sum(0)/7)))
res["monthly_CF_std_raw_cellmedian"] = float(np.median(Mcf.std(0, ddof=1)))
res["monthly_CF_range_cellmedian"] = float(np.median(Mcf.max(0)-Mcf.min(0)))
basin = Mcf.mean(1)
res["basin_monthly_CF"] = [float(x) for x in basin]
res["basin_monthly_CF_min_max"] = [float(basin.min()), float(basin.max())]
# S4 start
x0, y0 = g.to_xy(-21.6, 56.49); j0, i0 = (int(a) for a in g.index_of(x0, y0)); c0 = int(np.nonzero((jj == j0) & (ii == i0))[0][0])
res["S4_start_monthly_CF"] = [float(x) for x in Mcf[:, c0]]; res["S4_start_annual_CF"] = float(P[:, c0].mean())
res["S4_start_resid_std"] = float(np.sqrt((resid[:, c0]**2).sum()/7))
# stratified (by month) moving-block bootstrap of annual CF, 7-day blocks
rng = np.random.default_rng(1)
def boot(series, B=400, bl=168):
    out = []
    for b in range(B):
        tot = 0.0
        for m in range(12):
            s = series[moff[m]:moff[m+1]]; L = s.size; k = int(np.ceil(L/bl))
            st = rng.integers(0, L-bl, k); tot += np.concatenate([s[a:a+bl] for a in st])[:L].mean()*L
        out.append(tot/n)
    return np.array(out)
bs0 = boot(P[:, c0]); res["S4_start_annual_CF_bootstrap_se"] = float(bs0.std())
bsb = boot(P.mean(1)); res["basin_annual_CF_bootstrap_se"] = float(bsb.std())
# median cell
cells = rng.choice(nc, 60, replace=False); se_c = [boot(P[:, c], B=60).std() for c in cells]
res["cell_annual_CF_bootstrap_se_median"] = float(np.median(se_c)); res["cell_annual_CF_bootstrap_se_p90"] = float(np.percentile(se_c, 90))
# 30-day window CF std at start cell and across cells, de-seasoned via monthly means (window-level noise)
win = 30*24; st = np.arange(0, n-win, 24)
w30 = np.stack([P[s:s+win].mean(0) for s in st])      # (nw, nc)
# deseason: subtract smooth seasonal (harmonic fit on window start day)
tsd = (st+win/2)/8760*2*np.pi
Xw = np.column_stack([np.ones(st.size), np.cos(tsd), np.sin(tsd), np.cos(2*tsd), np.sin(2*tsd)])
bw, *_ = np.linalg.lstsq(Xw, w30, rcond=None); rw = w30 - Xw@bw
res["30d_window_CF_resid_std_cellmedian"] = float(np.median(rw.std(0))); res["30d_window_CF_resid_std_S4start"] = float(rw[:, c0].std())
res["30d_window_CF_std_raw_S4start"] = float(w30[:, c0].std())
res["se_of_mean_of_6_windows_cellmedian_if_indep"] = res["30d_window_CF_resid_std_cellmedian"]/np.sqrt(6)
# effective independent samples per season (integral time scale 17 h -> 2*17h)
res["n_independent_synoptic_samples_per_season"] = float(92*24/(2*17))
# annual CF of every cell and its relation to the best point stability: rank correlation of seasonal CF maps (DJF vs JJA, H1 vs H2 months)
def cfm(ms): 
    sel = np.isin(mon, ms); return P[sel].mean(0)
from scipy.stats import spearmanr
res["spearman_cellCF_DJF_vs_JJA"] = float(spearmanr(cfm([12, 1, 2]), cfm([6, 7, 8]))[0])
res["spearman_cellCF_Jan-Jun_vs_Jul-Dec"] = float(spearmanr(cfm([1,2,3,4,5,6]), cfm([7,8,9,10,11,12]))[0])
res["spearman_cellCF_oddmonths_vs_evenmonths"] = float(spearmanr(cfm([1,3,5,7,9,11]), cfm([2,4,6,8,10,12]))[0])
# best-cell stability: best cell using even months -> its CF in odd months vs best in odd
ce, co = cfm([2,4,6,8,10,12]), cfm([1,3,5,7,9,11])
res["best_cell_even_months_CF_in_odd_months"] = float(co[np.argmax(ce)]); res["best_cell_odd_months_CF_in_odd_months"] = float(co.max())
json.dump(res, open(OUT/"a6.json", "w"), indent=1); print(json.dumps(res, indent=1))
