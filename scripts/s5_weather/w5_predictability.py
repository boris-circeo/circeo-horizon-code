"""A5: skill of forecast model v2 for 'productive wind at x at lead N' vs climatology and (calibrated) persistence."""
import sys, json, time; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from horizon.weather.forecast_model import ERA5ForecastWeather
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r"); n = uv.shape[0]; ny, nx = g.shape
mon = month_of_hour(arc)
wx = ERA5ForecastWeather(arc, g, np.datetime64("2015-01-01T00:00:00"), 360*86400.0, seed=1)
okp = np.isfinite(ph); php = np.where(okp, ph, 0.0)
jj, ii = np.nonzero(sea)
def Pof(uvf):   # (...,ny,nx,2) -> P kW at sea cells (...,nc), and TWS kn
    w = np.hypot(uvf[..., 0], uvf[..., 1])[..., jj, ii]/KN
    return np.interp(w, tws/KN, php), w
# climatology: per-cell frequency of P>2MW and monthly mean TWS
aw = np.load(OUT/"sea_series.npz")["W"].astype(np.float32)
Ptr_all = np.interp(aw, tws/KN, php)
Ind_all = Ptr_all > 2000
clim_f = Ind_all.mean(0)
clim_m = np.stack([Ind_all[mon == m].mean(0) for m in range(1, 13)])
mu_m = np.stack([aw[mon == m].mean(0) for m in range(1, 13)])      # monthly TWS clim (12, nc)
NL = 41; leads_h = np.arange(NL)*6
# persistence-conditional frequencies per lead (pooled over cells)
F1 = np.zeros(NL); F0 = np.zeros(NL)
for L in range(NL):
    h = L*6
    a = Ind_all[:n-h]; b = Ind_all[h:]
    F1[L] = b[a].mean(); F0[L] = b[~a].mean()
issues = np.arange(5, 351, 9)*86400.0
rows = []
acc = {k: np.zeros(NL) for k in ("bs_f", "bs_clim", "bs_pers", "bs_f_day", "bs_clim_day", "bs_pers_day", "bs_clim_seas", "se_ens", "se_ctl", "se_pers")}
cnt = 0
# ACC accumulators
S = {k: np.zeros(NL) for k in ("fa_ta_c", "fa2_c", "ta2", "fa_ta_p", "pa2", "fa_ta_m", "fm2")}
byseason = {sn: {k: np.zeros(NL) for k in ("bs_f", "bs_clim", "bs_pers")} for sn in SEASONS}; cseas = {sn: 0 for sn in SEASONS}
hit = np.zeros(NL); hit_clim = np.zeros(NL)
t0 = time.time()
for iss in issues:
    e = wx.forecast_cycle(float(iss), 10*86400.0, 20, dt_s=6*3600.0)
    tt = e.times_s; hidx = np.round((tt/3600.0)).astype(int)
    truth = wx._truth_at(tt)
    Pt, Wt = Pof(truth)                                 # (NL, nc)
    Pf, Wf = Pof(e.uv)                                  # (M, NL, nc)
    ev_t = Pt > 2000; pf = (Pf > 2000).mean(0)         # prob (NL, nc)
    m_ = mon[hidx[0]]
    sn = [s for s, v in SEASONS.items() if m_ in v][0]
    # climatology and persistence probabilities
    pc = np.broadcast_to(clim_f, ev_t.shape)
    pp = np.where(ev_t[0][None, :], F1[:, None], F0[:, None])
    bsf = ((pf - ev_t)**2).mean(1); bsc = ((pc - ev_t)**2).mean(1); bsp = ((pp - ev_t)**2).mean(1)
    bscs = ((np.broadcast_to(clim_m[m_-1], ev_t.shape) - ev_t)**2).mean(1); acc["bs_clim_seas"] += bscs
    acc["bs_f"] += bsf; acc["bs_clim"] += bsc; acc["bs_pers"] += bsp
    for k, v in (("bs_f", bsf), ("bs_clim", bsc), ("bs_pers", bsp)): byseason[sn][k] += v
    cseas[sn] += 1
    hit += (((pf > 0.5) == ev_t).mean(1)); hit_clim += (((clim_f > 0.5)[None, :] == ev_t).mean(1))
    # daily-mean event (lead day d: samples 4d..4d+3)
    dd = np.arange(NL)  # store by lead hours of day start; compute for d=0..9 into index 4d
    for d in range(10):
        sl = slice(4*d, 4*d+4)
        evd = Pt[sl].mean(0) > 2000
        pfd = (Pf[:, sl].mean(1) > 2000).mean(0)
        pd_clim = (Ind_all.reshape(-1, 1, aw.shape[1])[: (n//24)*24].reshape(-1, 24, aw.shape[1]).mean(1) > 0).mean() if False else None
        acc["bs_f_day"][4*d] += ((pfd - evd)**2).mean()
        acc["bs_clim_day"][4*d] += ((clim_f - evd)**2).mean()   # (note: instantaneous clim freq as ref)
    # anomaly correlation (TWS kn)
    mu = mu_m[m_-1]
    ta = Wt - mu; fc = Wf[0] - mu; fm = Wf.mean(0) - mu; pa = (Wt[0] - mu)[None, :]*np.ones((NL, 1))
    S["fa_ta_c"] += (fc*ta).sum(1); S["fa2_c"] += (fc**2).sum(1); S["ta2"] += (ta**2).sum(1)
    S["fa_ta_m"] += (fm*ta).sum(1); S["fm2"] += (fm**2).sum(1)
    S["fa_ta_p"] += (pa*ta).sum(1); S["pa2"] += (pa**2).sum(1)
    acc["se_ens"] += ((Wf.mean(0) - Wt)**2).mean(1); acc["se_ctl"] += ((Wf[0] - Wt)**2).mean(1); acc["se_pers"] += ((Wt[0][None] - Wt)**2).mean(1)
    cnt += 1
    if cnt == 1: print("per issue", time.time()-t0, flush=True)
N = cnt
res = {"leads_h": leads_h.tolist(), "n_issues": N, "n_members": 20}
res["BSS_forecast_vs_clim"] = (1 - acc["bs_f"]/acc["bs_clim"]).tolist()
res["BSS_forecast_vs_seasonal_clim"] = (1 - acc["bs_f"]/acc["bs_clim_seas"]).tolist()
res["BSS_calibrated_persistence_vs_clim"] = (1 - acc["bs_pers"]/acc["bs_clim"]).tolist()
res["BSS_daily_event_forecast_vs_clim"] = [float(1 - acc["bs_f_day"][4*d]/acc["bs_clim_day"][4*d]) for d in range(10)]
res["Brier_forecast"] = (acc["bs_f"]/N).tolist(); res["Brier_clim"] = (acc["bs_clim"]/N).tolist()
res["hit_rate_forecast_p>0.5"] = (hit/N).tolist(); res["hit_rate_clim_mode"] = (hit_clim/N).tolist()
res["ACC_control"] = (S["fa_ta_c"]/np.sqrt(S["fa2_c"]*S["ta2"])).tolist()
res["ACC_ens_mean"] = (S["fa_ta_m"]/np.sqrt(S["fm2"]*S["ta2"])).tolist()
res["ACC_persistence"] = (S["fa_ta_p"]/np.sqrt(S["pa2"]*S["ta2"])).tolist()
res["RMSE_TWS_kn"] = {"ens_mean": np.sqrt(acc["se_ens"]/N).tolist(), "control": np.sqrt(acc["se_ctl"]/N).tolist(), "persistence": np.sqrt(acc["se_pers"]/N).tolist()}
res["BSS_by_season"] = {sn: {"forecast": (1 - byseason[sn]["bs_f"]/byseason[sn]["bs_clim"]).tolist(), "persistence": (1 - byseason[sn]["bs_pers"]/byseason[sn]["bs_clim"]).tolist(), "n": cseas[sn]} for sn in SEASONS}
json.dump(res, open(OUT/"a5.json", "w"), indent=1)
def first_below(x, thr):
    k = np.nonzero(np.array(x) < thr)[0]; return float(leads_h[k[0]]) if k.size else None
for nm in ("BSS_forecast_vs_clim", "BSS_calibrated_persistence_vs_clim", "ACC_control", "ACC_ens_mean", "ACC_persistence"):
    v = np.array(res[nm]); print(nm, "lead0 %.2f  24h %.2f 48h %.2f 72h %.2f 120h %.2f 168h %.2f 240h %.2f" % tuple(v[[0, 4, 8, 12, 20, 28, 40]]))
print("ACC ctl <0.6 at h", first_below(res["ACC_control"], .6), "ens", first_below(res["ACC_ens_mean"], .6), "persist", first_below(res["ACC_persistence"], .6))
print("BSS fc <0.2 at", first_below(res["BSS_forecast_vs_clim"], .2), "<0.1", first_below(res["BSS_forecast_vs_clim"], .1), "pers<0.1", first_below(res["BSS_calibrated_persistence_vs_clim"], .1))
print("daily", np.round(res["BSS_daily_event_forecast_vs_clim"], 2))
