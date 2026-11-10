"""H2: skill / spread / rank histogram of the synthetic ensemble (speed at sea cells)."""
import sys

import numpy as np

sys.path.insert(0, "/home/claude/horizon/scripts/diag_s2")
from common import *

grid, coast, polar, hold, pm = setup()
sea = coast.sdf >= 100e3
M = 12
leads_d = [1, 2, 3, 4, 5, 6, 7, 8, 10]
res = {d: dict(c=[], m=[], sp=[], rank=[], cm=[], cs=[], env=[], cenv=[]) for d in leads_d}
rng = np.random.default_rng(0)
for seed in (101, 102):
    wx = SyntheticWeather(grid, EPOCH, 40*DAY, seed=seed)
    truth = wx.truth(dt_s=3600.0)
    for iss in np.arange(2, 24, 4.0) * DAY:
        ens = wx.forecast(iss, 10*DAY, M, dt_s=10800.0)
        k0 = int(round((ens.times_s[0]-truth.times_s[0])/3600.0))
        for d in leads_d:
            ti = int(d*8)
            tr = truth.uv[k0 + ti*3]
            tru = tr[sea]                       # (n,2)
            mem = ens.uv[:, ti][:, sea]         # (M,n,2)
            sp_t = np.hypot(*tru.T); sp_m = np.hypot(mem[..., 0], mem[..., 1])
            r = res[d]
            r["c"].append(np.mean(np.sum((mem[0]-tru)**2, -1)))
            r["m"].append(np.mean(np.sum((mem.mean(0)-tru)**2, -1)))
            r["sp"].append(np.mean(mem.var(0, ddof=1).sum(-1)))
            # speed-based: members 1..M-1 vs truth rank (control excluded? use all M)
            rk = (sp_m < sp_t[None]).sum(0) + 0  # 0..M
            r["rank"].append(np.bincount(rk, minlength=M+1))
            # speed errors
            r["cs"].append(np.mean((sp_m[0]-sp_t)**2)); r["cm"].append(np.mean((sp_m.mean(0)-sp_t)**2))
            lo, hi = sp_m.min(0), sp_m.max(0)
            r["env"].append(np.mean((sp_t >= lo) & (sp_t <= hi)))
            # same stat for control within envelope of members 1..M-1 (exch. check)
            lo1, hi1 = sp_m[1:].min(0), sp_m[1:].max(0)
            r["cenv"].append(np.mean((sp_m[0] >= lo1) & (sp_m[0] <= hi1)))
print("lead  RMSE_ctrl RMSE_mean spread | speedRMSE ctrl mean | P(truth in env) (expected (M-1)/(M+1)=%.2f) P(ctrl in env of others)" % ((M-1)/(M+1)))
for d in leads_d:
    r = res[d]
    print(f"D{d:<3} {np.sqrt(np.mean(r['c'])):7.2f} {np.sqrt(np.mean(r['m'])):8.2f} {np.sqrt(np.mean(r['sp'])):7.2f} | {np.sqrt(np.mean(r['cs'])):6.2f} {np.sqrt(np.mean(r['cm'])):6.2f} | {np.mean(r['env']):.3f}   {np.mean(r['cenv']):.3f}")
for d in (3, 5, 7):
    h = np.sum(res[d]["rank"], 0); print(f"rank hist D{d} (speed, 0=truth below all):", np.round(h/h.sum(), 3))
