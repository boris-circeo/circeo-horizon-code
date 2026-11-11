"""Build the self-contained router inspector page from an exported backtest.

Usage::

    python3 scripts/build_inspector.py --results outputs/inspector_data.json.gz \
        --out outputs/inspector.html

``--results`` is an export file (``.json`` / ``.json.gz``) or a directory containing one or
more of them (exports are merged: policies of later files are added to the first).
"""

import argparse
from pathlib import Path

from horizon.viz import load_export, merge_exports, write_inspector


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True, help="export file or directory of exports")
    ap.add_argument("--out", default="outputs/inspector.html")
    ap.add_argument("--no-gzip", action="store_true", help="embed plain JSON instead of gzip")
    ap.add_argument("--tech-figures", action="store_true",
                    help="compute the technical Guide figures (client data; slow once)")
    ap.add_argument("--lite", action="store_true",
                    help="shareable lite file (wind every 12 h, tracks every 3 h; ~3 MB, phones)")
    ap.add_argument("--wind-step", type=int, default=2, help="--lite: every n-th wind snapshot")
    ap.add_argument("--track-step", type=int, default=3, help="--lite: every n-th track sample")
    ap.add_argument("--wind-stride", type=int, default=1, help="--lite: keep every n-th wind cell")
    ap.add_argument("--wind-quant", type=int, default=3, help="--lite: wind code rounding step")
    a = ap.parse_args()
    p = Path(a.results)
    files = sorted(f for f in p.iterdir() if f.name.endswith((".json", ".json.gz"))) \
        if p.is_dir() else [p]
    if not files:
        raise SystemExit(f"no export found in {p}")
    data = load_export(files[0])
    for f in files[1:]:
        merge_exports(data, load_export(f))
    lite = {"wind_step": a.wind_step, "track_step": a.track_step,
            "wind_stride": a.wind_stride,
            "wind_quant": a.wind_quant} if a.lite else False
    out = write_inspector(data, a.out, gzip_data=not a.no_gzip, tech_figures=a.tech_figures or None,
                          lite=lite)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
