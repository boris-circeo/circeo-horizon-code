# docdev — production chain of the HORIZON v2 description document

Builds **CIRCEO-OPS-DES-861 rev A — "HORIZON v2 : retour d'expérience, validation des hypothèses et
algorithme affiné"** (French client deliverable; title tentative). The chain is a port of the one that
produced the v1 note (CIRCEO-OPS-DES-860); the house style (`style.css`), the callout boxes, the
two-pass table of contents and the print header/footer are unchanged. Only the tooling was reused,
none of the v1 text.

```
doc/main.md + doc/cover.md          source (Markdown, French)
        |  tools/hyp_table.py       register (docs/s5/hypotheses.yaml) -> doc/generated/*.md
        |  {{include: ...}}         expanded by build.py
        v  pandoc                   Markdown -> HTML5 (pipe tables, fenced divs, $math$)
        v  build.py post-process    callouts, inline SVG figures, Figure/Tableau numbering,
        |                           heading ids + invisible page markers, 2-pass TOC
        v  render.js                headless Chrome (system binary) -> PDF, A4, header/footer
        v  pypdf                    cover (no header) + body merge, metadata
out/CIRCEO-OPS-DES-861_revA_HORIZON_v2.pdf
```

## Quick start

```bash
cd docdev
nice -n 15 make figures     # our figure generators -> fig/   (read-only use of ../src)
nice -n 15 make             # build the PDF (also regenerates the register tables)
make check                  # pagination, TOC, numbering, fonts, images, math, placeholders
```

Use `nice -n 15` while the sensitivity campaign is running; a full build takes ~20 s and `make figures` ~25 s.

## Requirements

| Tool | Notes |
|---|---|
| `pandoc` >= 3 | Markdown -> HTML |
| `node` >= 18 + `playwright-core` (or `playwright`) | used **only as a driver**: `render.js` launches the system Chrome |
| Google Chrome / Chromium | default `/usr/bin/google-chrome`; override with `CHROME_BIN=/path/to/chrome`. No Playwright browser download is needed |
| Python >= 3.10 | `pypdf`, `pyyaml`; figures also need `numpy`, `matplotlib` and the `horizon` package (`pip install -e ..[value]`) |

`render.js` looks for `playwright-core`/`playwright` in `node_modules`, then in `NODE_PATH` and in the usual
global locations (`/opt/node22/lib/node_modules`, `/usr/lib/node_modules`, `/usr/local/lib/node_modules`).
Chrome is started with `--no-sandbox` (the build runs as root in a container).

KaTeX and Plus Jakarta Sans are **vendored** (`vendor/`), so the build needs no network. Licences:
KaTeX is MIT (`vendor/katex/LICENSE`), Plus Jakarta Sans is SIL OFL 1.1 (`vendor/fonts/OFL.txt`); see `vendor/README.md`.
The logo comes from the v1 repository (`assets/logo_circeo.png`).

## Layout

```
Makefile               targets: all/pdf, figures, generated, check, clean, distclean, deps
build.py               orchestrator; DOCID/REV/TITLE/STATUS constants at the top; writes out/meta.json
render.js              Chrome printing; reads out/meta.json for header/footer text; embeds fonts in templates
style.css              CIRCEO house style (+ ".todo" placeholder style at the end)
doc/cover.md           cover page: metadata table and revision history
doc/main.md            the document (chapters 1-9, annexes A-E); {{include: generated/x.md}} directives
doc/generated/         produced by tools/hyp_table.py (git-ignored)
figures/gen_figures.py figure generator (see below)
fig/                   generated figures (SVG are inlined in the HTML so document fonts apply; PNG referenced)
tools/hyp_table.py     register -> Markdown tables (summary matrix, verdicts by status, full register by category)
tools/check_pdf.py     post-build checks (exit code 1 on a blocking problem)
vendor/                KaTeX, Plus Jakarta Sans (+ licences)
out/                   products (PDF, intermediate HTML/PDF) — git-ignored
```

## Figures (`make figures`)

`figures/gen_figures.py` **imports `horizon` read-only** (`src/` is never modified) and
(1) runs `horizon.viz.tech_figures.build_tech_figures` on `outputs/s4_inspector/year.json.gz`, the BETA polar and the
ERA5 caches, writing `fig/tech_<id>.svg` for architecture, polar, forecast, safety, envelope, dp, ensemble,
terminal, refiner, mpc and results, plus `fig/tech_captions.json` (French captions and texts from the same run);
(2) copies the S5 weather figures (`docs/s5/fig/w_*.png`) and the S4 analysis figures (`outputs/S4_*.png`) into `fig/`.
Missing inputs (client data) cause a figure to be skipped, never a crash. `HORIZON_REPO` overrides the repository path.
Axis labels inside these figures are in English (working figures); captions are French.

## The register tables (`tools/hyp_table.py`)

Reads `docs/s5/hypotheses.yaml` at every build and writes three fragments included in the document:
`hyp_summary.md` (category x status and criticality x status matrices), `hyp_verdicts.md` (items grouped by
status — contradicted / refuted / nuanced / confirmed — with evidence, annex B) and `hyp_register.md` (complete register
by category, annex C). New status codes (`confirmed`, `refuted`, `nuanced`) are already mapped to French labels; optional
`statement_fr` / `evidence_fr` fields are used when present. After the campaign, update the YAML and rebuild.

## Writing conventions

* Callouts: `::: {.cal .key}` + `[LABEL]{.lab}` (classes `key dec req ass eq acc safe open note todo`).
* Pending results: put `<span class="todo">[À COMPLÉTER S5-campagne]</span>`; `make check` counts them.
* Figures: `![Caption.](fig/name.svg)` (SVG is inlined, numbered "Figure n."); tables: pipe table followed by `: Caption.`
  ("Tableau n."). Relative column widths of pipe tables follow the number of dashes in the separator line.
* Math: `$...$` and `$$...$$` (KaTeX). Decimal comma in prose; `$` must be escaped as `\$` when it is not math.

## Caveats

* `make check` flags `DejaVuSans` among the fonts: it is only a fallback for a few glyphs (embedded, not an error).
* The PDF title/status/header text come from the constants at the top of `build.py`.
* Page numbering: the body PDF starts with a 2 px phantom page that is dropped at merge time, so Chrome's `pageNumber/totalPages`
  match the merged document (cover included), as in v1.
