"""Progress of the Sprint-5 campaign: done / total per tier and experiment, CPU-h, ETA, errors.

Usage: ``python3 scripts/s5/status.py [--campaign scripts/s5/campaign.yaml] [--workers 2] [-v]``.
ETA = remaining cases x median wall time of finished cases of the same router type (fallback:
``outputs/s5/timing_estimates.json``, else built-in guesses) / workers.
"""
import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402

FALLBACK_S = {"B0": 5.0, "B1c_5d_REF": 400.0, "ENS_REF": 1500.0, "Oracle_REF_H": 380.0,
              "B1m_5d_REF": 740.0, "GREEDY_HOLD24": 30.0, "GREEDY_MAXWIND": 30.0}


def fmt_h(s):
    return f"{s / 3600:.1f} h"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", default=str(L.ROOT / "scripts/s5/campaign.yaml"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("-v", action="store_true", help="list running / failed cases in detail")
    a = ap.parse_args()
    cases = L.expand(L.load_campaign(a.campaign))
    done = {c["id"]: json.loads(L.result_path(c["id"]).read_text())
            for c in cases if L.is_done(c["id"])}
    locks = L.live_locks()
    master = None
    pf = L.OUT / "queue.pid"
    if pf.exists():
        try:
            pid = int(pf.read_text())
            if L.pid_alive(pid) and "s5/queue.py" in Path(f"/proc/{pid}/cmdline").read_text():
                master = pid
        except (OSError, ValueError):
            pass
    print(f"{time.strftime('%F %T')}  queue master: "
          + (f"ALIVE pid {master}" if master else "NOT RUNNING (run scripts/s5/supervise.sh)")
          + f"; running cases: {len(locks)}")
    est = dict(FALLBACK_S)
    tf = L.OUT / "timing_estimates.json"
    if tf.exists():
        est.update(json.loads(tf.read_text()))
    by_type = defaultdict(list)
    for r in done.values():
        by_type[r["spec"]["router"]["name"]].append(r["wall_s"])
    med = {k: statistics.median(v) for k, v in by_type.items()}
    est.update(med)
    tiers = sorted({c["tier"] for c in cases})
    print(f"\nTier  done/total   remaining wall-h (1 worker)  "
          f"ETA (cumulative, {a.workers} workers)")
    cum = 0.0
    for t in tiers:
        cs = [c for c in cases if c["tier"] == t]
        nd = sum(c["id"] in done for c in cs)
        rem = sum(est[c["spec"]["router"]["name"]] for c in cs if c["id"] not in done)
        cum += rem
        print(f"  {t}   {nd:4d}/{len(cs):<4d}   {fmt_h(rem):>10}   {fmt_h(cum / a.workers):>10}")
    tot_done = len(done)
    print(f"  all  {tot_done:4d}/{len(cases):<4d}")
    wall = sum(r["wall_s"] for r in done.values())
    cpu = sum(r["cpu_s"] for r in done.values())
    print(f"\nCPU used (finished cases): {cpu / 3600:.1f} CPU-h, wall {wall / 3600:.1f} h; "
          f"median wall per case by router: "
          + ", ".join(f"{k} {v / 60:.1f} min (n={len(by_type[k])})"
                      for k, v in sorted(med.items())))
    exps = defaultdict(lambda: [0, 0])
    for c in cases:
        for e in c["experiments"]:
            exps[e][1] += 1
            exps[e][0] += c["id"] in done
    print("\nExperiment                          done/total")
    for e, (d, n) in exps.items():
        print(f"  {e:34s} {d:3d}/{n:<3d}{'  OK' if d == n else ''}")
    now = time.time()
    if locks:
        print("\nRunning:")
        for cid, d in locks.items():
            print(f"  {cid}  ({(now - d['t']) / 60:.0f} min)")
    errs = []
    for p in L.ERRS.glob("*.json") if L.ERRS.exists() else []:
        d = json.loads(p.read_text())
        if p.stem not in done:
            errs.append((p.stat().st_mtime, p.stem, d))
    if errs:
        print(f"\nCases with errors (not done): {len(errs)}; most recent:")
        for _, cid, d in sorted(errs, reverse=True)[:5 if not a.v else 50]:
            last = d["log"][-1]
            print(f"  {cid} attempts={d['attempts']} [{last['t']}] "
                  f"{last['msg'].strip().splitlines()[-1][:160]}")
    else:
        print("\nNo errors.")
    pend = [c for c in cases if c["id"] not in done]
    rem = sum(est[c["spec"]["router"]["name"]] for c in pend)
    from datetime import datetime, timedelta, timezone
    eta = datetime.now(timezone.utc) + timedelta(seconds=rem / a.workers)
    try:
        from zoneinfo import ZoneInfo
        eta = eta.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:  # noqa: BLE001
        pass
    print(f"\nTOTAL remaining: {len(pend)} cases, ~{fmt_h(rem)} CPU -> ETA "
          f"{fmt_h(rem / a.workers)} on {a.workers} workers (finish ~ {eta:%F %H:%M} Paris)")


if __name__ == "__main__":
    main()
