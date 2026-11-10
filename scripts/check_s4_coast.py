"""S4 coast check: re-run S3 policies on the missions with S3 coast violations and report the
violation count, guard interventions and exact minimum margin (resumable: one json per run).

Usage: ``python3 scripts/check_s4_coast.py --policies Oracle B1_5d --missions 2015-01-15 ...``
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_s3_backtest as R  # noqa: E402

OUT = R.ROOT / "outputs" / "s4_coast"


def main():
    warnings.filterwarnings("ignore", category=UserWarning)
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", nargs="+", required=True)
    ap.add_argument("--missions", nargs="+", required=True)
    ap.add_argument("--no-guard", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = R.Ctx()
    for date in a.missions:
        for name in a.policies:
            f = OUT / f"{name}_{date}.json"
            if f.exists():
                continue
            t0 = time.perf_counter()
            res, _, dt, pol, wx, _ = R.run_one(name, date, ctx, 10, 5)
            sdf = ctx.coast.sdf_at(res.x, res.y)
            cm = ctx.coast.segment_min(res.x[:-1], res.y[:-1], res.x[1:], res.y[1:])
            d = {"policy": name, "date": date, "energy_mwh": float(res.energy_kwh[-1] / 1e3),
                 "coast_violations": res.coast_violations,
                 "guard_interventions": res.guard_interventions,
                 "min_sdf_km": float(np.nanmin(sdf) / 1e3),
                 "min_chord_sdf_km": float(np.nanmin(cm) / 1e3),
                 "min_margin_km": res.min_margin_m / 1e3, "wall_s": time.perf_counter() - t0,
                 "n_dp_fallback": getattr(pol, "n_dp_fallback", None)}
            f.write_text(json.dumps(d, indent=1))
            print(json.dumps(d), flush=True)


if __name__ == "__main__":
    main()
