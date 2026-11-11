#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure generator of the HORIZON v2 document (`make figures`).

READ-ONLY use of the repository: imports `horizon` (src/ is never modified), runs the technical
figure code of `horizon.viz.tech_figures` on the real data and writes the results under
`docdev/fig/`:

  fig/tech_<id>.svg        one SVG per technical figure (architecture, polar, dp, ensemble, ...)
  fig/tech_captions.json   captions / bodies (FR) produced with the same run (numbers consistent)
  fig/w_*.png, s4_*.png    weather-analysis (docs/s5/fig) and S4 (outputs/) figures, copied

Figures whose inputs are missing (client data, caches) are skipped with a message; the document
build does not fail on a missing figure (the Markdown image is then left as a broken link, which
tools/check_pdf.py reports).

Usage:  python3 figures/gen_figures.py [--only architecture polar ...] [--no-tech] [--jobs-nice 15]
"""
import argparse, gzip, json, os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCDEV = HERE.parent
REPO = Path(os.environ.get('HORIZON_REPO', DOCDEV.parent))
FIG = DOCDEV / 'fig'

COPIES = {  # destination name in fig/ -> source relative to the repository
    **{p.name: Path('docs/s5/fig') / p.name for p in sorted((REPO / 'docs/s5/fig').glob('w_*.png'))},
    's4_monthly_cf.png': Path('outputs/S4_monthly_cf.png'),
    's4_annual.png': Path('outputs/S4_annual.png'),
    's4_paired.png': Path('outputs/S4_paired.png'),
    's4_tws.png': Path('outputs/S4_tws.png'),
    's4_lorient.png': Path('outputs/S4_lorient.png'),
}

def copy_static():
    for dst, src in COPIES.items():
        s = REPO / src
        if s.exists():
            shutil.copyfile(s, FIG / dst)
            print(f'copied  {dst}')
        else:
            print(f'MISSING {src}')

def tech(only):
    sys.path.insert(0, str(REPO / 'src'))            # read-only import of the frozen package
    from horizon.viz.tech_figures import build_tech_figures
    export = REPO / 'outputs/s4_inspector/year.json.gz'
    if not export.exists():
        print('MISSING outputs/s4_inspector/year.json.gz : technical figures skipped')
        return
    data = json.load(gzip.open(export))
    figs = build_tech_figures(data, only=only or None, progress=print)
    caps = {}
    cap_file = FIG / 'tech_captions.json'
    if cap_file.exists():
        caps = json.loads(cap_file.read_text(encoding='utf-8'))
    for f in figs:
        (FIG / f"tech_{f['id']}.svg").write_text(f['svg'], encoding='utf-8')
        caps[f['id']] = {k: f[k] for k in ('title_fr', 'caption_fr', 'body_fr', 'title_en', 'caption_en')}
        print(f"wrote   tech_{f['id']}.svg  {len(f['svg'])/1e3:.0f} kB")
    cap_file.write_text(json.dumps(caps, ensure_ascii=False, indent=1), encoding='utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*', default=[])
    ap.add_argument('--no-tech', action='store_true')
    ap.add_argument('--nice', type=int, default=15)
    a = ap.parse_args()
    try:
        os.nice(a.nice)
    except OSError:
        pass
    FIG.mkdir(exist_ok=True)
    copy_static()
    if not a.no_tech:
        tech(a.only)

if __name__ == '__main__':
    main()
