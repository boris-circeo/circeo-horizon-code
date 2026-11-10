"""H3/H5: 10-day missions, horizons NOT truncated at mission end (wrapper). Usage: h3_horizon.py SEED POL [POL...]"""
import json
import sys
import time

sys.path.insert(0, "/home/claude/horizon/scripts/diag_s2")
from common import *

from horizon.sim import DeterministicMPCPolicy, OraclePolicy, run_mission
from horizon.sim.policies_ens import EnsembleMPCPolicy
from horizon.sim.simulator import ForecastProvider


class NoTrunc:
    def __init__(self, pol): self.pol = pol
    def plan(self, t, x, y, prov):
        return self.pol.plan(t, x, y, ForecastProvider(prov._weather, prov.now_s, 40*DAY))

def make(name, polar, hold, coast):
    if name.startswith("B1_"):
        return NoTrunc(DeterministicMPCPolicy(polar, hold, coast, horizon_days=float(name[3:-1])))
    # ENS<H>d_g<gamma>_k<k>  e.g. ENS5d_g0_k6
    _h, g, k = name.split("_"); h = _h[3:]
    H = float(h[:-1]); gam = float(g[1:]) / 10; kk = int(k[1:])
    return NoTrunc(EnsembleMPCPolicy(polar, hold, coast, horizon_days=H, n_members=12, k=kk,
                                     gamma=gam, alpha=0.2))
seed = int(sys.argv[1]); pols = sys.argv[2:]
grid, coast, polar, hold, pm = setup()
T = 10*DAY
wx = SyntheticWeather(grid, EPOCH, T, seed=seed)
truth = wx.truth(dt_s=3600.0)
for name in pols:
    t0 = time.perf_counter()
    pol = OraclePolicy(truth, polar, hold, coast, T) if name == "Oracle" else make(name, polar, hold, coast)
    res = run_mission(pol, wx, truth, START, T, pm, coast, replan_s=6*3600.0)
    J = float(res.energy_kwh[-1])/1e3
    print(json.dumps({"seed": seed, "pol": name, "J_MWh": J, "wall": time.perf_counter()-t0}), flush=True)
