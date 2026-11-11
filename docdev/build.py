#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the HORIZON v2 document: markdown -> HTML (CIRCEO house style) -> PDF.

Ported from the v1 chain (CIRCEO-OPS-DES-860); differences: document metadata is shared with
render.js through out/meta.json, Chromium is the system Chrome (see render.js), generated Markdown
fragments (hypothesis table) are included through {{include: path}} directives.
"""
import re, subprocess, sys, json, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT  = ROOT / 'out'
OUT.mkdir(exist_ok=True)

def write_fonts_css():
    """@font-face rules pointing at the vendored Plus Jakarta Sans files."""
    faces = []
    for w in (400, 500, 600, 700, 800):
        for style, suffix in (('normal', 'normal'), ('italic', 'italic')):
            f = ROOT / 'vendor' / 'fonts' / f'plus-jakarta-sans-latin-{w}-{suffix}.woff2'
            if f.exists():
                faces.append(f'@font-face{{font-family:"Plus Jakarta Sans";'
                             f'src:url("{f.as_uri()}") format("woff2");'
                             f'font-weight:{w};font-style:{style};font-display:block}}')
    (OUT / 'fonts.css').write_text('\n'.join(faces) + '\n', encoding='utf-8')
    return OUT / 'fonts.css'

DOCID   = "CIRCEO-OPS-DES-861"
REV     = "rev A"
SUBTITLE = "HORIZON v2 : retour d'expérience, validation des hypothèses et algorithme affiné"
TITLE   = f"{DOCID} {REV} — {SUBTITLE}"          # tentative title
SHORT   = SUBTITLE
STATUS  = "EARLY DRAFT"
FINAL_NAME = f"{DOCID}_rev{REV.split()[-1]}_HORIZON_v2.pdf"

def write_meta():
    """Metadata shared with render.js (headers / footers)."""
    (OUT / 'meta.json').write_text(json.dumps(
        {'docid': DOCID, 'rev': REV, 'status': STATUS, 'short': SHORT}, ensure_ascii=False), encoding='utf-8')

INCLUDE = re.compile(r'^\{\{include:\s*(\S+)\s*\}\}\s*$', re.M)

def expand_includes(md: str) -> str:
    """Replace `{{include: relative/path.md}}` lines (relative to doc/) by the file content."""
    def sub(m):
        f = ROOT / 'doc' / m.group(1)
        if not f.exists():
            sys.exit(f'include introuvable : {f} (lancer `make generated`)')
        return f.read_text(encoding='utf-8')
    return INCLUDE.sub(sub, md)

def run_generators():
    """Regenerate the Markdown fragments derived from the repository (hypothesis register)."""
    gen = ROOT / 'tools' / 'hyp_table.py'
    if gen.exists():
        subprocess.run([sys.executable, str(gen)], check=True, cwd=ROOT)

# ---------------------------------------------------------------- markdown -> html
def pandoc(md_text: str) -> str:
    p = subprocess.run(
        ['pandoc', '-f',
         'markdown+pipe_tables+fenced_divs+bracketed_spans+implicit_figures+tex_math_dollars+raw_html-smart',
         '-t', 'html5', '--mathjax', '--wrap=none'],
        input=md_text, capture_output=True, text=True)
    if p.returncode:
        sys.exit('pandoc: ' + p.stderr[:2000])
    return p.stdout

def slug(s, n=[0]):
    n[0] += 1
    base = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    base = re.sub(r'[^a-zA-Z0-9]+', '-', base).strip('-').lower()[:40]
    return f"{base}-{n[0]}"

def postprocess(html: str):
    """callouts, figure/table numbering, heading ids + page markers, TOC."""
    # --- callout label / title paragraphs
    html = re.sub(r'<p><span class="lab">(.*?)</span></p>', r'<p class="lab">\1</p>', html, flags=re.S)
    html = re.sub(r'<p><span class="tit">(.*?)</span></p>', r'<p class="tit">\1</p>', html, flags=re.S)
    html = re.sub(r'<p><span class="eqn">(.*?)</span></p>', r'<p class="eqn">\1</p>', html, flags=re.S)

    # --- inline SVG figures (so that document fonts and CSS apply)
    nsvg = [0]
    def inline_svg(m):
        src = m.group(1)
        f = ROOT / src
        if not f.exists() or not src.endswith('.svg'):
            return m.group(0)
        nsvg[0] += 1
        pre = f'g{nsvg[0]}_'
        s = f.read_text(encoding='utf-8')
        s = re.sub(r'<\?xml[^>]*\?>', '', s)
        s = re.sub(r'<!DOCTYPE[^>]*>', '', s, flags=re.S)
        s = re.sub(r'<!--.*?-->', '', s, flags=re.S)
        s = re.sub(r'id="([^"]+)"', lambda k: f'id="{pre}{k.group(1)}"', s)
        s = re.sub(r'url\(#([^)]+)\)', lambda k: f'url(#{pre}{k.group(1)})', s)
        s = re.sub(r'(xlink:href|href)="#([^"]+)"', lambda k: f'{k.group(1)}="#{pre}{k.group(2)}"', s)
        wm = re.search(r'<svg[^>]*?width="([0-9.]+)(pt|px|in|mm)?"', s)
        wmm = None
        if wm:
            v = float(wm.group(1)); unit = wm.group(2) or 'px'
            wmm = v * {'pt': 25.4 / 72, 'px': 25.4 / 96, 'in': 25.4, 'mm': 1.0}[unit]
        s = re.sub(r'<svg([^>]*?)\s(width|height)="[^"]*"', r'<svg\1', s)
        s = s.replace("font-family: 'DejaVu Sans'", "font-family: 'Plus Jakarta Sans', 'DejaVu Sans'")   # document font for matplotlib text
        style = 'width:100%;height:auto' if (wmm is None or wmm >= 176) else f'width:{wmm:.0f}mm;max-width:100%;height:auto'
        s = re.sub(r'<svg', f'<svg preserveAspectRatio="xMidYMid meet" style="{style}"', s, count=1)
        return s.strip()
    html = re.sub(r'<img src="([^"]+)"[^>]*/?>', inline_svg, html)

    # --- figure numbering
    fig = [0]
    def fignum(m):
        fig[0] += 1
        return f'<figcaption><span class="lbl">Figure {fig[0]}.</span> '
    html = re.sub(r'<figcaption[^>]*>', fignum, html)

    # --- table caption numbering
    tab = [0]
    def tabnum(m):
        tab[0] += 1
        return f'<caption><span class="lbl">Tableau {tab[0]}.</span> '
    html = re.sub(r'<caption[^>]*>', tabnum, html)

    # --- headings: ids, invisible page markers, collect TOC
    toc, hid = [], [0]
    def head(m):
        lvl, attrs, txt = m.group(1), m.group(2), m.group(3)
        plain = re.sub(r'<[^>]+>', '', txt)
        hid[0] += 1
        mark = f'H{hid[0]}'
        idm = re.search(r'id="([^"]+)"', attrs or '')
        _id = idm.group(1) if idm else slug(plain)
        if lvl in ('1', '2') and 'nobreak' not in (attrs or '') and 'notoc' not in (attrs or ''):
            toc.append({'lvl': int(lvl), 'txt': plain, 'id': _id, 'mark': mark})
        at = attrs or ''
        if 'id=' not in at:
            at += f' id="{_id}"'
        return (f'<h{lvl}{at}>{txt}'
                f'<span class="pm" style="color:#fff;font-size:1px">&#x27E6;{mark}&#x27E7;</span></h{lvl}>')
    html = re.sub(r'<h([1-4])([^>]*)>(.*?)</h\1>', head, html, flags=re.S)
    return html, toc

def toc_html(toc, pages=None):
    rows = []
    for e in toc:
        pg = (pages or {}).get(e['mark'], '00')
        cls = 'l1' if e['lvl'] == 1 else 'l2'
        rows.append(f'<li class="{cls}"><span class="t">{e["txt"]}</span>'
                    f'<span class="d"></span><span class="pg">{pg}</span></li>')
    return '<div class="toc"><h1 class="nobreak">Sommaire</h1><ul>' + ''.join(rows) + '</ul></div>'

# ---------------------------------------------------------------- html shell
HEAD = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="{fonts}">
<link rel="stylesheet" href="{katex_css}">
<link rel="stylesheet" href="{style}">
<script defer src="{katex_js}"></script>
<script defer src="{autorender}"></script>
<script>
document.addEventListener("DOMContentLoaded", function(){{
  renderMathInElement(document.body, {{
    delimiters:[{{left:"\\\\[",right:"\\\\]",display:true}},{{left:"\\\\(",right:"\\\\)",display:false}}],
    throwOnError:false, strict:false, macros:{{"\\\\E":"\\\\mathbb{{E}}","\\\\R":"\\\\mathbb{{R}}"}}
  }});
  window.__mathDone = true;
}});
</script>
</head><body>"""

ASSETS = {}

def shell(body, title=TITLE):
    return HEAD.format(title=title, **ASSETS) + body + "</body></html>"

# ---------------------------------------------------------------- main
def main():
    ASSETS.update(
        fonts=write_fonts_css().as_uri(),
        katex_css=(ROOT / 'vendor/katex/katex.min.css').as_uri(),
        katex_js=(ROOT / 'vendor/katex/katex.min.js').as_uri(),
        autorender=(ROOT / 'vendor/katex/contrib/auto-render.min.js').as_uri(),
        style=(ROOT / 'style.css').as_uri(),
    )
    write_meta()
    run_generators()
    src = expand_includes((ROOT / 'doc' / 'main.md').read_text(encoding='utf-8'))
    body_html, toc = postprocess(pandoc(src))

    cover_md = (ROOT / 'doc' / 'cover.md').read_text(encoding='utf-8')
    cover_html = '<div class="cover">' + pandoc(cover_md)[0:] + '</div>'
    cover_html = re.sub(r'<p><span class="(\w+)">(.*?)</span></p>', r'<p class="\1">\2</p>', cover_html, flags=re.S)
    (ROOT / 'cover.html').write_text(shell(cover_html), encoding='utf-8')

    def write_body(pages=None):
        # phantom first page keeps page numbering aligned with the merged document
        phantom = '<div style="height:2px;break-after:page"></div>'
        (ROOT / 'body.html').write_text(
            shell(phantom + toc_html(toc, pages) + body_html), encoding='utf-8')

    write_body()
    subprocess.run(['node', str(ROOT / 'render.js')], check=True, cwd=ROOT)

    # ---- second pass: real page numbers in the TOC
    from pypdf import PdfReader
    r = PdfReader(str(OUT / 'body.pdf'))
    pages = {}
    for i, pg in enumerate(r.pages):          # page 1 of body.pdf = phantom = page 1 of merged doc
        try:
            txt = pg.extract_text() or ''
        except Exception:
            txt = ''
        for m in re.findall(r'⟦\s*(H\d+)\s*⟧', txt):
            pages.setdefault(m, i + 1)
    write_body(pages)
    subprocess.run(['node', str(ROOT / 'render.js')], check=True, cwd=ROOT)

    # ---- merge: cover + body[2:]
    from pypdf import PdfWriter
    w = PdfWriter()
    cov = PdfReader(str(OUT / 'cover.pdf'))
    assert len(cov.pages) == 1, f'la couverture tient sur {len(cov.pages)} pages'
    w.add_page(cov.pages[0])
    rb = PdfReader(str(OUT / 'body.pdf'))
    for p in rb.pages[1:]:
        w.add_page(p)
    w.add_metadata({'/Title': TITLE, '/Author': 'CIRCEO',
                    '/Subject': STATUS, '/Creator': 'CIRCEO'})
    final = OUT / FINAL_NAME
    with open(final, 'wb') as f:
        w.write(f)
    print(f'pages: {len(w.pages)}  figures/tables ok  ->  {final}')

if __name__ == '__main__':
    main()
