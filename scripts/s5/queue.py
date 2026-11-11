"""Sprint-5 campaign queue: a pool of N workers consumes the expanded campaign by priority.

Usage: ``python3 scripts/s5/queue.py [--workers 2] [--campaign scripts/s5/campaign.yaml]
[--tiers A,B,C] [--retry-failed] [--once]``.

* Single master (``outputs/s5/queue.pid`` + flock): a second start exits at once.
* The campaign file is RE-READ every cycle: experiments appended while it runs are picked up.
* Cases are claimed with per-case lock files (``outputs/s5/locks``); a lock whose pid is dead is
  stale and re-claimed; cases with a result file are skipped (idempotent). Each case runs in its
  own subprocess (``run_case.py``): clean memory, kill-safe (10-day checkpoints are resumed).
* Cases with 3 failed attempts are parked (``--retry-failed`` clears them). Logs:
  ``outputs/s5/logs/<case_id>.log`` and ``queue.log``.
"""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402

MAX_ATTEMPTS = 3


def log(msg):
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)


def pending(camp_path, tiers):
    camp = L.load_campaign(camp_path)
    cases = L.expand(camp)
    return [c for c in cases if (tiers is None or c["tier"] in tiers)
            and not L.is_done(c["id"]) and L.error_attempts(c["id"]) < MAX_ATTEMPTS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--campaign", default=str(L.ROOT / "scripts/s5/campaign.yaml"))
    ap.add_argument("--tiers", default=None, help="e.g. A,B (default: all)")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--once", action="store_true", help="exit when nothing is left to launch")
    a = ap.parse_args()
    tiers = a.tiers.split(",") if a.tiers else None
    L.OUT.mkdir(parents=True, exist_ok=True)
    L.LOGS.mkdir(parents=True, exist_ok=True)
    lockf = open(L.OUT / "queue.flock", "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another queue master is running; exiting")
        return 0
    (L.OUT / "queue.pid").write_text(str(os.getpid()))
    if a.retry_failed:
        for p in L.ERRS.glob("*.json"):
            p.unlink()
    log(f"queue master pid {os.getpid()} workers {a.workers} campaign {a.campaign}")
    running: dict[str, subprocess.Popen] = {}
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    while not stop["flag"]:
        for cid, p in list(running.items()):
            rc = p.poll()
            if rc is not None:
                if rc == 75:
                    log(f"busy {cid} (claimed elsewhere)")
                elif rc != 0 and not L.is_done(cid):
                    if L.error_attempts(cid) == 0 or rc < 0:
                        L.record_error(cid, f"worker exit code {rc} (killed / OOM?)")
                    log(f"FAILED {cid} rc={rc}")
                else:
                    log(f"finished {cid}")
                L.release(cid)
                del running[cid]
        try:
            todo = pending(a.campaign, tiers)
        except Exception as exc:  # a half-written campaign file must not kill the master
            log(f"campaign read error: {exc!r}")
            time.sleep(10)
            continue
        busy = L.live_locks()  # includes children of a previous (killed) master
        free = a.workers - len(busy)
        launched = False
        for c in todo:
            if free <= 0:
                break
            cid = c["id"]
            if cid in busy or cid in running or not L.claim(cid):
                continue
            logf = open(L.LOGS / f"{cid}.log", "a")
            p = subprocess.Popen(
                [sys.executable,
                 os.environ.get("S5_RUN_CASE", str(L.ROOT / "scripts/s5/run_case.py")),
                 "--spec-json",
                 json.dumps(c["spec"])], stdout=logf, stderr=subprocess.STDOUT, cwd=L.ROOT,
                env={**os.environ, "S5_CLAIMED": "1"},
                start_new_session=False)
            L.set_lock_pid(cid, p.pid)
            running[cid] = p
            free -= 1
            launched = True
            log(f"start [{c['tier']}] {cid} ({len(todo)} pending)")
        if a.once and not running and not launched and not busy:
            break
        time.sleep(5)
    log("stopping: terminating workers" if stop["flag"] else "queue empty")
    for p in running.values():
        p.terminate()
    for cid, p in running.items():
        try:
            p.wait(30)
        except subprocess.TimeoutExpired:
            p.kill()
        L.release(cid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
