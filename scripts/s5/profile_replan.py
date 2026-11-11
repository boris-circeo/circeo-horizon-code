"""Profile / benchmark ONE replan of a router on the 40 km ERA5 grid (S5 external review).

Usage: ``python3 scripts/s5/profile_replan.py --router B1c_5d_REF [--t-days 5] [--reps 3]
[--cprofile] [--dump out.npz]``. Prints CPU time per replan (``process_time``), the first call
(JIT / setup) separately, and with ``--cprofile`` the top cumulative entries of the last replan.
``--dump`` stores the returned plan (x, y, value) for before/after identity checks.
"""
import argparse
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402

from horizon.sim.simulator import ForecastProvider  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--router", default="B1c_5d_REF")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--t-days", type=float, default=5.0)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cprofile", action="store_true")
    ap.add_argument("--top", type=int, default=35)
    ap.add_argument("--dump")
    a = ap.parse_args()
    spec = L.normalise({"router": {"name": a.router}, "env": {}, "start": a.start, "days": 30.0,
                        "seed": 1})
    e = L.full_env(spec)
    ctx = L.get_ctx(e["grid_km"])
    start, coast = L.start_point(ctx, e)
    wx, pm, man = L.build_environment(ctx, e, spec["seed"], spec["start"], spec["days"])
    pol = L.build_router(ctx, spec, wx, coast, ctx.grid.to_xy(*start))
    x, y = ctx.grid.to_xy(*start)
    t = a.t_days * 86400.0
    prov = ForecastProvider(wx, t, 30 * 86400.0)
    plans = []
    for r in range(a.reps):
        c0, w0 = time.process_time(), time.perf_counter()
        prof = cProfile.Profile() if (a.cprofile and r == a.reps - 1) else None
        if prof:
            prof.enable()
        plan = pol.plan(t, x, y, prov)
        if prof:
            prof.disable()
        plans.append(plan)
        print(f"replan {r}: cpu {time.process_time() - c0:.2f} s wall "
              f"{time.perf_counter() - w0:.2f} s", flush=True)
    if a.cprofile:
        s = io.StringIO()
        pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(a.top)
        print(s.getvalue())
    if a.dump:
        p = plans[-1]
        np.savez(a.dump, x=p.x, y=p.y, v=p.value_kwh)
        print("plan:", p.x.size, "arcs, value", p.value_kwh)


if __name__ == "__main__":
    main()
