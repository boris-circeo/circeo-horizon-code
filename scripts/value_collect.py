"""Collect hindsight maps, forecast feature fields and B1 rollouts every 3 days of 2015.

Usage: ``python3 scripts/value_collect.py [--step-days 3] [--ships 40] [--only K ...]``.
Output (git-ignored, client-derived): ``data/cache/value/k_XXX.npz`` (resumable).
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_s3_backtest as R  # noqa: E402

from horizon.dp import build_stencil  # noqa: E402
from horizon.polar.climatology import hold_power_vs_tws  # noqa: E402
from horizon.value.collect import hindsight_maps, rollout_group  # noqa: E402
from horizon.value.features import forecast_feature_fields  # noqa: E402
from horizon.weather.forecast_model import ERA5ForecastWeather  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "cache" / "value"
DAY = 86400.0
HORIZONS = (2, 5, 10)


def main():
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--step-days", type=float, default=3.0)
    ap.add_argument("--ships", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--only", type=int, nargs="*")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = R.Ctx()
    epoch = np.datetime64("2015-01-01T00:00:00", "s")
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, epoch, 365 * DAY, seed=a.seed)
    tws_ax, p_ax = hold_power_vs_tws(ctx.env)
    ok = np.isfinite(p_ax)
    stencil = build_stencil(ctx.grid, 3 * 3600.0)
    nav = (ctx.coast.sdf >= 20e3) & ~ctx.outside
    nav_ji = np.argwhere(nav)
    n_k = int((365 - 10) / a.step_days) + 1
    ks = a.only if a.only else range(n_k)
    for k in ks:
        f = OUT / f"k_{k:03d}.npz"
        if f.exists():
            continue
        t0 = time.perf_counter()
        s_k = k * a.step_days * DAY
        tr3 = wx.truth(dt_s=3 * 3600.0, start_s=s_k, end_s=s_k + 10 * DAY)
        hind = hindsight_maps(tr3, s_k, HORIZONS, ctx.polar, ctx.hold, ctx.coast, stencil)
        t1 = time.perf_counter()
        if s_k >= 5 * DAY:
            ens = wx.forecast(s_k - 5 * DAY, 10 * DAY, 1, dt_s=6 * 3600.0)
            fc = forecast_feature_fields(ens.times_s, ens.uv[0], s_k, s_k + 5 * DAY,
                                         tws_ax[ok], p_ax[ok])
        else:
            fc = np.full((6,) + ctx.grid.shape, np.nan, np.float32)
        rng = np.random.default_rng(1000 * a.seed + k)
        cells = nav_ji[rng.choice(len(nav_ji), a.ships, replace=False)]
        trh = wx.truth(dt_s=3600.0, start_s=s_k, end_s=s_k + 5 * DAY + 3600.0)
        ro = rollout_group(wx, trh, ctx.pm, ctx.coast, ctx.polar, ctx.hold, s_k, cells)
        np.savez_compressed(f.with_suffix(".tmp.npz"), hind=hind, fc=fc, cells=cells, s_k=s_k,
                            **ro)
        f.with_suffix(".tmp.npz").replace(f)
        print(f"k={k} s={s_k / DAY:.0f}d hind {t1 - t0:.1f}s total {time.perf_counter() - t0:.1f}s",
              flush=True)


if __name__ == "__main__":
    main()
