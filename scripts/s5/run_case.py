"""Run ONE Sprint-5 case; writes outputs/s5/runs/<case_id>.json atomically (skip if it exists).

Usage::

    python3 scripts/s5/run_case.py --router B1c_5d_REF --start 2015-01-01 [--days 30] [--seed 1]
        [--set horizon_days=3] [--env error_scale=0.5 --env manoeuvre=false] [--print-id]
    python3 scripts/s5/run_case.py --spec-json '{"router": {"name": ...}, "env": {...}, ...}'

Routers: B1c_5d_REF (base cheap router), ENS_REF (frontier), Oracle_REF_H (hindsight bound,
recomputed per environment), B0 (best fixed point). Router overrides (--set) and environment
overrides (--env): see ``ROUTER_DEFAULTS`` / ``ENV_DEFAULTS`` in s5lib.py. Long windows are
checkpointed every 10 days (outputs/s5/ckpt/<id>) and resumed on restart. The gap to the oracle
is NOT computed here (needs the Oracle case of the same environment: see aggregate.py).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402


def _kv(items):
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--router")
    ap.add_argument("--start")
    ap.add_argument("--days", type=float, default=30.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--set", action="append", help="router override k=v")
    ap.add_argument("--env", action="append", help="environment override k=v")
    ap.add_argument("--spec-json")
    ap.add_argument("--print-id", action="store_true")
    a = ap.parse_args()
    if a.spec_json:
        spec = json.loads(a.spec_json)
    else:
        spec = {"router": {"name": a.router, **_kv(a.set)}, "env": _kv(a.env), "start": a.start,
                "days": a.days, "seed": a.seed}
    if a.print_id:
        print(L.case_id(spec))
        return 0
    return L.main_run(spec)


if __name__ == "__main__":
    sys.exit(main())
