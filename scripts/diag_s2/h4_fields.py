"""H4b: how different are ENS decisions from B1_15d / control? v_bar vs control value-to-go at split."""
import sys, pickle, numpy as np
sys.path.insert(0, "/home/claude/horizon/scripts/diag_s2")
from common import *
from scipy.stats import spearmanr
from horizon.dp import build_stencil, solve_dp
from horizon.dp.stochastic import solve_stochastic_dp, RiskSpec
from horizon.ensemble import reduce_ensemble
from horizon.sim.policies import _nearest_cell
grid, coast, polar, hold, pm = setup()
st = build_stencil(grid, 10800.0)
wx = SyntheticWeather(grid, EPOCH, 30*DAY, seed=101)
truth = wx.truth(dt_s=3600.0)
d = pickle.load(open("/home/claude/horizon/outputs/s2_runs/B1_5d_101.pkl", "rb"))["res"]
dt = 10800.0; n = int(15*DAY/dt); ns = 16
X, Y = grid.xy_mesh()
common = dict(polar=polar, hold_curve=hold, coast=coast, d_min=20e3, stencil=st)
for td in (2, 6, 10, 14):
    t = td*DAY
    k = int(np.searchsorted(d.t_s, t)); x, y = d.x[k], d.y[k]
    ens = wx.forecast(t, n*dt, 12, dt_s=dt)
    ctrl = ens.member(0)
    # control DP value at split and truth DP value at split (same horizon)
    vc = solve_dp(ctrl, t+ns*dt, n-ns, dt, polar, hold, coast, d_min=20e3, stencil=st).V[0]
    tr = wx.truth(dt_s=3600.0, start_s=t+ns*dt, end_s=t+n*dt)
    vt = solve_dp(tr, t+ns*dt, n-ns, dt, polar, hold, coast, d_min=20e3, stencil=st).V[0]
    out = {}
    for kk in (6, 12):
        red = reduce_ensemble(ens, kk, window_s=(t+ns*dt, ens.times_s[-1]), tau_s=7*DAY)
        r = solve_stochastic_dp(red.scenarios(ens), red.weights, ctrl, t, n*dt, dt, split_s=ns*dt, risk=RiskSpec(0.0, 0.2), **common)
        out[kk] = r
    # reach region: cells within 800 km of ship, feasible
    reach = np.isfinite(vc) & np.isfinite(vt) & (np.hypot(X-x, Y-y) < 700e3)
    f = lambda a: a[reach]
    print(f"t={td}d  reach cells {reach.sum()}")
    for nm, a in (("v_ctrl", vc), ("vbar6", out[6].v_bar), ("vbar12", out[12].v_bar)):
        rt = spearmanr(f(a), f(vt))[0]; ct = np.corrcoef(f(a), f(vt))[0,1]
        # regret of choosing argmax-in-reach cell under this field, measured with truth V
        j, i = np.unravel_index(np.argmax(np.where(reach, a, -np.inf)), a.shape)
        print(f"   {nm:7s} corr w/ truth V: pearson {ct:.3f} spearman {rt:.3f} | argmax cell truth-V loss vs truth argmax: {(np.nanmax(np.where(reach, vt, -np.inf)) - vt[j,i])/1e3:.1f} MWh")
    # Per-scenario spread of V at the ship's neighbourhood
    sv = out[12].scenario_values[:, reach]
    print(f"   scenario V std across members (reach mean) {sv.std(0).mean()/1e3:.1f} MWh; truth-vs-ctrl |dV| mean {np.abs(f(vt)-f(vc)).mean()/1e3:.1f}; truth-vs-vbar12 |dV| {np.abs(f(vt)-f(out[12].v_bar)).mean()/1e3:.1f}; truth V mean {f(vt).mean()/1e3:.1f}")
