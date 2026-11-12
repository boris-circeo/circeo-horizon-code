"""Merge docs/s5/verdicts.yaml into docs/s5/hypotheses.yaml (fields s5_verdict, s5_evidence; the
status becomes ``s5-<verdict>``) and print a count per verdict.

Usage: ``python3 scripts/s5/apply_verdicts.py [--fill KEY=TEXT ...]``; ``--fill`` replaces
``{V2:KEY}`` placeholders (v2 validation results) before merging.
"""
import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", nargs="*", default=[])
    a = ap.parse_args()
    fills = dict(f.split("=", 1) for f in a.fill)
    vtext = (ROOT / "docs/s5/verdicts.yaml").read_text()
    for k, v in fills.items():
        vtext = vtext.replace("{V2:" + k + "}", v)
    verdicts = yaml.safe_load(vtext)
    hp = ROOT / "docs/s5/hypotheses.yaml"
    hyps = yaml.safe_load(hp.read_text())
    header = "".join(ln for ln in hp.read_text().splitlines(True) if ln.startswith("#"))
    counts = {}
    for h in hyps:
        v = verdicts.get(h["id"])
        if v is None:
            continue
        h["s5_verdict"], h["s5_evidence"] = v["verdict"], " ".join(v["evidence"].split())
        h["status"] = f"s5-{v['verdict']}"
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    header += ("# S5 WP5: statuses 's5-<verdict>' come from docs/s5/verdicts.yaml "
               "(scripts/s5/apply_verdicts.py).\n")
    hp.write_text(header + yaml.safe_dump(hyps, sort_keys=False, allow_unicode=True, width=100))
    print(counts, "| still unresolved:", sum(1 for h in hyps if h["status"] == "open"))


if __name__ == "__main__":
    main()
