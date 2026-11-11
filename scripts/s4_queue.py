"""Resumable job queue for the Sprint-4 runs.

Usage: ``python3 scripts/s4_queue.py JOBFILE [--par 2] [--extra "--stop-after 1"]``; each job line
is ``NAME|ARGS`` (arguments of run_s4_year.py). Finished runs (run_info.json) are skipped; relaunch
the same command after a kill to resume (the runs themselves resume from their last month).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("jobs")
ap.add_argument("--par", type=int, default=2)
ap.add_argument("--extra", default="")
a = ap.parse_args()
jobs = [ln.strip().split("|", 1) for ln in open(a.jobs) if ln.strip() and not ln.startswith("#")]
(ROOT / "outputs/logs").mkdir(parents=True, exist_ok=True)
running = []
while jobs or running:
    running = [(n, p) for n, p in running if p.poll() is None]
    while jobs and len(running) < a.par:
        name, args = jobs.pop(0)
        d = ROOT / "outputs/s4_runs" / name
        if (d / "run_info.json").exists() and not a.extra:
            continue
        d.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(ROOT / "scripts/run_s4_year.py"), *args.split(), "--out", str(d),
               *a.extra.split()]
        log = open(ROOT / "outputs/logs" / f"{name}.log", "a")
        print(time.strftime("%H:%M:%S"), "start", name, flush=True)
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        running.append((name, proc))
    time.sleep(5)
print("queue done", flush=True)
