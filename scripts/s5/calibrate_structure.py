"""Calibrate E-02 structure variants to the control-RMSE of the default error model.

Finds the scale ``s`` of (a) displacement-only and (b) amplitude+noise-only errors such that the
mean control RMSE over leads D1..D7 matches the default model; reports the analog variant's RMSE
by lead (matched by construction). Usage: ``python3 scripts/s5/calibrate_structure.py``.
"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402

from horizon.weather.forecast_model import (  # noqa: E402
    ERA5ForecastWeather,
    ForecastErrorParams,
    forecast_skill,
)

DAY = 86400.0


def rmse(ctx, params, issues, seed=5):
    wx = ERA5ForecastWeather(ctx.archive, ctx.grid, np.datetime64("2015-01-01T00:00:00"),
                             330 * DAY, params=params, seed=seed)
    mask = ~ctx.outside & (ctx.coast.sdf > 0)
    r = forecast_skill(wx, issues, n_members=3, max_lead_days=7, mask=mask)
    return r["control_rmse"]


def main():
    ctx = L.get_ctx(40.0)
    issues = [d * DAY for d in (10, 100, 190, 280)]
    base = ForecastErrorParams()
    ref = rmse(ctx, base, issues)
    print("default :", np.round(ref, 2))
    cases = (
        ("analog", lambda s: dict(structure="analog", analog_scale=s)),
        ("disp_only", lambda s: dict(disp_scale=s, amp_scale=0.0, noise_scale=0.0)),
        ("ampnoise_only", lambda s: dict(disp_scale=0.0, amp_scale=s, noise_scale=s)))
    for name, kw in cases:
        lo, hi = 0.2, 3.5
        for _ in range(7):
            mid = 0.5 * (lo + hi)
            r = rmse(ctx, replace(base, **kw(mid)), issues)
            lo, hi = (mid, hi) if r[1:].mean() < ref[1:].mean() else (lo, mid)
        s = 0.5 * (lo + hi)
        print(f"{name}: scale {s:.3f}", np.round(rmse(ctx, replace(base, **kw(s)), issues), 2))


if __name__ == "__main__":
    main()
