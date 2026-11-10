"""H1: ENS with all members == control and gamma=0 must reproduce the deterministic 15 d trunk."""
import sys, numpy as np
sys.path.insert(0, "/home/claude/horizon/scripts/diag_s2")
from common import *
from horizon.sim import DeterministicMPCPolicy
from horizon.sim.policies_ens import EnsembleMPCPolicy
from horizon.sim.simulator import ForecastProvider
from horizon.weather.fields import Ensemble

class CloneWx:
    def __init__(self, wx): self._wx, self.grid = wx, wx.grid
    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        e = self._wx.forecast(issue_s, horizon_s, 1, dt_s=dt_s)
        uv = np.repeat(e.uv, n_members, axis=0)
        # tiny jitter-free clones
        return Ensemble(e.grid, e.epoch, e.issue_s, e.times_s, uv, np.full(n_members, 1.0/n_members))

grid, coast, polar, hold, pm = setup()
wx = SyntheticWeather(grid, EPOCH, 12*DAY, seed=101)
x0, y0 = grid.to_xy(*START)
for k in (6,):
  for t in (0.0, 6*3600., 3*DAY, 5*DAY):
    prov = ForecastProvider(CloneWx(wx), t, 12*DAY)
    det = DeterministicMPCPolicy(polar, hold, coast, horizon_days=10.0)
    ens = EnsembleMPCPolicy(polar, hold, coast, horizon_days=10.0, n_members=6, k=k, gamma=0.0)
    pd = det.plan(t, x0, y0, prov); pe = ens.plan(t, x0, y0, prov)
    n = len(pe.x)
    print(f"t={t/DAY:.2f}d trunk n={n}  max|dx|,|dy| vs det first {n}: {np.abs(pd.x[:n]-pe.x).max():.1f} {np.abs(pd.y[:n]-pe.y).max():.1f}  value det {pd.value_kwh:.2f} ens {pe.value_kwh:.2f}")
