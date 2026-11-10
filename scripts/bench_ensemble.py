"""Benchmark of one full ensemble replan (DES-860 §7.4): forecast, reduction, two-stage DP."""

import time

import numpy as np

from horizon.dp import build_stencil
from horizon.dp.stochastic import RiskSpec, solve_stochastic_dp
from horizon.ensemble import reduce_ensemble
from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.weather.synthetic import SyntheticWeather

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY, DT = 86400.0, 3 * 3600.0


def main():
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    g = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = CoastModel(g, np.full(g.shape, 1e6, np.float32))
    wx = SyntheticWeather(g, EPOCH, 40 * DAY, seed=3)
    st = build_stencil(g, DT)
    n = int(15 * DAY / DT)
    for rep in range(2):  # first pass includes JIT compilation
        t0 = time.perf_counter()
        ens = wx.forecast(10 * DAY, n * DT, 20, dt_s=DT)
        t1 = time.perf_counter()
        red = reduce_ensemble(ens, 7, window_s=(10 * DAY + 48 * 3600.0, ens.times_s[-1]))
        t2 = time.perf_counter()
        res = solve_stochastic_dp(red.scenarios(ens), red.weights, ens.member(0), 10 * DAY,
                                  n * DT, DT, polar, hold, coast, risk=RiskSpec(0.3, 0.2),
                                  stencil=st)
        t3 = time.perf_counter()
        print(f"pass {rep}: forecast {t1 - t0:5.2f} s, reduction {t2 - t1:5.2f} s, "
              f"DP {t3 - t2:5.2f} s, total {t3 - t0:5.2f} s  (grid {g.ny}x{g.nx}, "
              f"k={red.k}, modes={red.eof.n_modes}, medoids={red.members.tolist()}, "
              f"Vbar max {np.nanmax(np.where(np.isfinite(res.v_bar), res.v_bar, np.nan)):.0f} kWh)")


if __name__ == "__main__":
    main()
