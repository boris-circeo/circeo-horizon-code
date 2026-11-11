#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the S5 hypothesis register (docs/s5/hypotheses.yaml) as Markdown fragments.

Output (doc/generated/, included by doc/main.md with `{{include: generated/<file>}}`):

  hyp_summary.md       counts: status totals, category x status matrix, criticality x status
  hyp_verdicts.md      the contradicted / nuanced / refuted / confirmed items, grouped BY STATUS
                       (what the document discusses in chapter 4), with evidence
  hyp_register.md      the complete register, grouped BY CATEGORY then by status (annex)

The register is re-read at every build: when the campaign (WP5) updates the `status` field
(new codes are accepted: confirmed, refuted, nuanced, ...), the tables follow automatically.
Optional fields `statement_fr` and `evidence_fr` are used when present, otherwise the English
register text is shown (register entries are working notes in English).

Usage: python3 tools/hyp_table.py [--yaml PATH] [--out DIR] [--max-evidence N]
"""
import argparse, collections, os, re, sys
from pathlib import Path
import yaml

DOCDEV = Path(__file__).resolve().parent.parent
REPO = Path(os.environ.get('HORIZON_REPO', DOCDEV.parent))

STATUS_FR = {   # order = reading order in the tables
    'contradicted-by-S0-S4': 'contredit (S0-S4)',
    'refuted': 'réfuté (S5)',
    'nuanced': 'nuancé (S5)',
    'supported-by-S0-S4': 'confirmé (S0-S4)',
    'confirmed': 'confirmé (S5)',
    'open': 'ouvert',
    'untestable-here': 'non testable ici',
}
CAT_FR = {
    'algorithm-choice': "choix d'algorithme", 'discretisation': 'discrétisation', 'fleet': 'flottille',
    'forecast': 'prévision', 'numerics': 'numérique', 'operations': 'opérations',
    'problem-structure': 'structure du problème', 'risk': 'risque', 'ship/polar': 'navire / polaire',
    'value-function': 'fonction de valeur', 'weather': 'météo',
}
CRIT_FR = {'high': 'haute', 'medium': 'moyenne', 'low': 'faible'}
CRIT_ORDER = {'high': 0, 'medium': 1, 'low': 2}
TYPE_FR = {'assumption': 'hypothèse', 'quantitative-claim': 'valeur annoncée',
           'design-decision': 'décision de conception', 'dismissed-alternative': 'alternative écartée'}

def sk(e):                                  # natural sort of H-<chapter>-<n>, H-X-* last
    m = re.match(r'H-(\w+)-(\d+)', e['id'])
    ch = m.group(1)
    return (1, 0, int(m.group(2))) if ch == 'X' else (0, int(ch), int(m.group(2)))

def esc(t):
    t = ' '.join(str(t).split())
    t = t.replace('\\', '\\\\').replace('|', '\\|').replace('$', '\\$').replace('*', '\\*')
    t = t.replace('<', '&lt;').replace('>', '&gt;')
    return t

def clip(t, n):
    t = ' '.join(str(t).split())
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(' ', 1)[0]
    return cut + ' […]'

def st(s):
    return STATUS_FR.get(s, s)

def status_rank(s):
    order = list(STATUS_FR)
    return order.index(s) if s in order else len(order)

def exps(test):
    """Experiment ids (E-xx) mentioned in the test field, in order of appearance."""
    ids = list(dict.fromkeys(re.findall(r'\bE-\d{2}\b', str(test))))
    return ', '.join(ids) if ids else '·'

def table(rows, header, widths=None):
    sep = ['-' * w for w in widths] if widths else ['---'] * len(header)   # pandoc: relative column widths
    out = ['| ' + ' | '.join(header) + ' |', '|' + '|'.join(sep) + '|']
    out += ['| ' + ' | '.join(r) + ' |' for r in rows]
    return '\n'.join(out)

def summary(reg):
    stat = collections.Counter(e['status'] for e in reg)
    statuses = sorted(stat, key=status_rank)
    cats = sorted({e['category'] for e in reg}, key=lambda c: CAT_FR.get(c, c))
    L = [f'Le registre compte **{len(reg)} entrées** : ' +
         ', '.join(f'{stat[s]} {st(s)}' for s in statuses) + '.', '']
    mat = collections.Counter((e['category'], e['status']) for e in reg)
    rows = [[CAT_FR.get(c, c)] + [str(mat[(c, s)] or '·') for s in statuses] +
            [f'**{sum(mat[(c, s)] for s in statuses)}**'] for c in cats]
    rows.append(['**Total**'] + [f'**{stat[s]}**' for s in statuses] + [f'**{len(reg)}**'])
    L += [table(rows, ['Catégorie'] + [st(s) for s in statuses] + ['Total']), '',
          ': Registre d\'hypothèses : effectifs par catégorie et par statut.', '']
    cm = collections.Counter((e['criticality'], e['status']) for e in reg)
    rows = [[CRIT_FR[c]] + [str(cm[(c, s)] or '·') for s in statuses] +
            [f'**{sum(cm[(c, s)] for s in statuses)}**'] for c in ('high', 'medium', 'low')]
    L += [table(rows, ['Criticité'] + [st(s) for s in statuses] + ['Total']), '',
          ': Registre d\'hypothèses : effectifs par criticité et par statut.', '']
    return '\n'.join(L)

def txt(e, key, fr_key):
    return e.get(fr_key) or e.get(key) or ''

def verdicts(reg, max_ev, focus=('contradicted-by-S0-S4', 'refuted', 'nuanced',
                                 'supported-by-S0-S4', 'confirmed')):
    L = []
    for s in focus:
        items = sorted([e for e in reg if e['status'] == s], key=lambda e: (CRIT_ORDER[e['criticality']], sk(e)))
        if not items:
            continue
        L += [f'#### {st(s)[0].upper() + st(s)[1:]} : {len(items)} entrées', '']
        rows = [[f'**{e["id"]}**', CRIT_FR[e['criticality']][:4] + '.', esc(txt(e, 'statement', 'statement_fr')),
                 esc(clip(txt(e, 'evidence_so_far', 'evidence_fr'), max_ev))] for e in items]
        L += [table(rows, ['Réf.', 'Crit.', 'Énoncé du v1 (ou hypothèse de notre environnement)', 'Preuve à ce jour'], [8, 4, 38, 50]), '',
              f': Entrées du registre au statut « {st(s)} » (triées par criticité).', '']
    return '\n'.join(L)

def register(reg, max_ev):
    L = []
    cats = sorted({e['category'] for e in reg}, key=lambda c: CAT_FR.get(c, c))
    for c in cats:
        items = sorted([e for e in reg if e['category'] == c], key=lambda e: (status_rank(e['status']), sk(e)))
        L += [f'### {CAT_FR.get(c, c)[0].upper() + CAT_FR.get(c, c)[1:]} ({len(items)})', '']
        rows = [[f'**{e["id"]}**', esc(txt(e, 'statement', 'statement_fr')), CRIT_FR[e['criticality']][:4] + '.',
                 st(e['status']), exps(e['test'])] for e in items]
        L += [table(rows, ['Réf.', 'Énoncé', 'Crit.', 'Statut', 'Exp.'], [8, 58, 5, 17, 8]), '',
              f': Registre complet, catégorie « {CAT_FR.get(c, c)} » (classé par statut puis par référence).', '']
    return '\n'.join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--yaml', default=str(REPO / 'docs/s5/hypotheses.yaml'))
    ap.add_argument('--out', default=str(DOCDEV / 'doc/generated'))
    ap.add_argument('--max-evidence', type=int, default=330)
    a = ap.parse_args()
    reg = yaml.safe_load(open(a.yaml, encoding='utf-8'))
    if not isinstance(reg, list) or not reg:
        sys.exit('registre vide ou illisible')
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'hyp_summary.md').write_text(summary(reg), encoding='utf-8')
    (out / 'hyp_verdicts.md').write_text(verdicts(reg, a.max_evidence), encoding='utf-8')
    (out / 'hyp_register.md').write_text(register(reg, a.max_evidence), encoding='utf-8')
    c = collections.Counter(e['status'] for e in reg)
    print(f'hyp_table: {len(reg)} entrées ->', ', '.join(f'{k}={v}' for k, v in c.items()))

if __name__ == '__main__':
    main()
