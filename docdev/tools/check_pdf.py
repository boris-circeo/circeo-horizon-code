#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick checks on the produced PDF: pagination, TOC, numbering, fonts, math, placeholders, images.

Exit code 0 = no blocking problem. Placeholders « [À COMPLÉTER ... ] » are counted (expected while
the document is a draft) but are not an error.
"""
import re, sys
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / 'out/CIRCEO-OPS-DES-861_revA_HORIZON_v2.pdf'

def fonts(reader):
    names, notemb = set(), set()
    for pg in reader.pages:
        res = pg.get('/Resources')
        if not res or '/Font' not in res:
            continue
        for f in res['/Font'].get_object().values():
            f = f.get_object()
            base = str(f.get('/BaseFont', ''))
            names.add(base.split('+')[-1])
            d = f.get('/DescendantFonts')
            desc = (d[0].get_object().get('/FontDescriptor') if d else f.get('/FontDescriptor'))
            desc = desc.get_object() if desc else {}
            if f.get('/Subtype') == '/Type3':
                continue                       # Type3 glyphs are self-contained
            if not any(k in desc for k in ('/FontFile', '/FontFile2', '/FontFile3')):
                notemb.add(base)
    return names, notemb

def main(path):
    r = PdfReader(str(path))
    pages = [p.extract_text() or '' for p in r.pages]
    full = '\n'.join(pages)
    toc = '\n'.join(pages[1:4])
    figs = sorted({int(n) for n in re.findall(r'Figure (\d+)\.', full)})
    tabs = sorted({int(n) for n in re.findall(r'Tableau (\d+)\.', full)})
    zeros = len(re.findall(r'\.\s*00\b', toc))
    ph = len(re.findall(r'À COMPLÉTER', full))
    names, notemb = fonts(r)
    htmls = [(ROOT / n).read_text(encoding='utf-8') for n in ('body.html', 'cover.html') if (ROOT / n).exists()]
    katex_err = sum(h.count('katex-error') for h in htmls)           # static HTML: only after rendering
    broken = re.findall(r'<img src="([^"]+)"', '\n'.join(htmls))
    broken = [b for b in broken if not (ROOT / b).exists()]
    leftovers = len(re.findall(r'\{\{include|\$\$|\\\(|\\\[', full))
    ok_figs = figs == list(range(1, len(figs) + 1))
    ok_tabs = tabs == list(range(1, len(tabs) + 1))

    print(f'fichier            : {path}')
    print(f'pages              : {len(r.pages)}')
    print(f'titre              : {r.metadata.get("/Title")}')
    print(f'figures numérotées : {len(figs)} ({"continue" if ok_figs else "DISCONTINUE"})')
    print(f'tableaux numérotés : {len(tabs)} ({"continue" if ok_tabs else "DISCONTINUE"})')
    print(f'sommaire à "00"    : {zeros}   (doit valoir 0)')
    print(f'polices            : {", ".join(sorted(names))}')
    print(f'polices non embarquées : {sorted(notemb) or "aucune"}')
    print(f'images manquantes  : {broken or "aucune"}')
    print(f'math non rendu     : {leftovers} délimiteur(s) résiduel(s) dans le texte (doit valoir 0)')
    print(f'placeholders       : {ph} « À COMPLÉTER » (attendus tant que la campagne S5 n\'est pas intégrée)')
    ok = zeros == 0 and ok_figs and ok_tabs and not notemb and not broken and leftovers == 0
    print('RESULTAT           :', 'OK' if ok else 'A VERIFIER')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT))
