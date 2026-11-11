"""Aggregate finished cases: mean CF per experiment variant, paired delta vs the base config, gap
to Oracle_REF_H of the SAME environment.

Usage: ``python3 scripts/s5/aggregate.py [--campaign ...] [--csv outputs/s5/summary.csv]``.
Per variant (router + overrides + env + seed) over its windows: mean CF [%], paired delta vs the
all-default case of the same router / seed on the SAME windows [points], gap to the oracle of the
same environment [points], mean manoeuvres per day, hold share. Variants with missing windows show
``n<6``; deltas use only windows present in both.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402


def load(spec):
    p = L.result_path(L.case_id(spec))
    return json.loads(p.read_text()) if p.exists() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", default=str(L.ROOT / "scripts/s5/campaign.yaml"))
    ap.add_argument("--csv", default=str(L.OUT / "summary.csv"))
    a = ap.parse_args()
    cases = L.expand(L.load_campaign(a.campaign))
    groups = defaultdict(list)  # (router, ovr, env, seed) -> specs by window
    for c in cases:
        s = c["spec"]
        key = (json.dumps(s["router"], sort_keys=True), json.dumps(s["env"], sort_keys=True),
               s["seed"], s["days"])
        groups[key].append(s)
    rows = []
    for (rj, ej, seed, days), specs in groups.items():
        router = json.loads(rj)
        rs = {s["start"]: load(s) for s in specs}
        w_ok = [s["start"] for s in specs if rs[s["start"]]]
        if not w_ok:
            continue
        cf = np.array([rs[w]["cf_pct"] for w in w_ok])
        d_ref, d_orc = [], []
        for s in specs:
            w = s["start"]
            if not rs[w]:
                continue
            b = load(L.normalise({"router": {"name": router["name"]}, "env": {},
                                  "start": w, "days": days, "seed": seed}))
            o = load(L.normalise({"router": {"name": "Oracle_REF_H"}, "env": json.loads(ej),
                                  "start": w, "days": days, "seed": 0}))
            if b:
                d_ref.append(rs[w]["cf_pct"] - b["cf_pct"])
            if o:
                d_orc.append(o["cf_pct"] - rs[w]["cf_pct"])
        rows.append({
            "router": router["name"], "router_ovr": json.dumps({k: v for k, v in router.items()
                                                                if k != "name"}),
            "env_ovr": ej, "seed": seed, "n": len(w_ok), "of": len(specs),
            "cf_mean": cf.mean(), "delta_vs_base": np.mean(d_ref) if d_ref else np.nan,
            "n_delta": len(d_ref), "gap_to_oracle": np.mean(d_orc) if d_orc else np.nan,
            "n_gap": len(d_orc),
            "manoeuvres_per_day": np.mean([rs[w]["manoeuvres"]["per_day"] for w in w_ok]),
            "hold_share": np.mean([rs[w]["hold_share"] for w in w_ok]),
            "wall_min": np.mean([rs[w]["wall_s"] for w in w_ok]) / 60.0})
    rows.sort(key=lambda r: (r["router"], r["router_ovr"], r["env_ovr"], r["seed"]))
    print(f"{'router':14s} {'router_ovr':28s} {'env_ovr':40s} s  n/N  CF%   dBase  gapOr  man/d")
    for r in rows:
        print(f"{r['router']:14s} {r['router_ovr'][:28]:28s} {r['env_ovr'][:40]:40s} {r['seed']} "
              f"{r['n']}/{r['of']} {r['cf_mean']:6.2f} {r['delta_vs_base']:+6.2f} "
              f"{r['gap_to_oracle']:6.2f} {r['manoeuvres_per_day']:5.1f}")
    if rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"-> {a.csv}")


if __name__ == "__main__":
    main()
