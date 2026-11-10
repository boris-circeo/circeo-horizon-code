"""S4 smoke test: a 20 d B1c_5d_REF run from the annual best offshore point is KILLED (SIGKILL)
after two committed segments and restarted; the result must be bit-identical to an uninterrupted
run. Usage: ``python3 scripts/smoke_s4_resume.py [--days 20] [--segments 432000]``."""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUN = [sys.executable, str(ROOT / "scripts" / "run_s4_year.py"), "--policy", "B1c_5d_REF"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", default="20")
    ap.add_argument("--segments", default="432000")  # 5 d
    ap.add_argument("--base", default=str(ROOT / "outputs" / "s4_runs" / "smoke"))
    a = ap.parse_args()
    base = Path(a.base)
    shutil.rmtree(base, ignore_errors=True)
    args = ["--days", a.days, "--segments", a.segments]
    full = subprocess.Popen(RUN + args + ["--out", str(base / "full")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = base / "killed"
    p = subprocess.Popen(RUN + args + ["--out", str(d)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    while len(list(d.glob("seg_*.json"))) < 2:
        if p.poll() is not None:
            raise SystemExit("run ended before the kill point")
        time.sleep(0.5)
    p.kill()
    p.wait()
    n_before = len(list(d.glob("seg_*.json")))
    print(f"killed with {n_before} committed segments", flush=True)
    r = subprocess.run(RUN + args + ["--out", str(d)], capture_output=True, text=True)
    print(r.stdout[-400:], flush=True)
    full.wait()
    ok = True
    for k in range(len(list((base / "full").glob("seg_*.json")))):
        za, zb = np.load(base / "full" / f"seg_{k:04d}.npz"), np.load(d / f"seg_{k:04d}.npz")
        for key in za.files:
            same = np.array_equal(za[key], zb[key])
            ok &= same
            if not same:
                print(f"DIFFERENT seg {k} {key}")
    print("IDENTICAL" if ok else "MISMATCH", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
