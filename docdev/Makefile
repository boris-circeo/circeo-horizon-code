# ---------------------------------------------------------------------------
# CIRCEO-OPS-DES-861 — HORIZON v2 : documentation chain
#   markdown -> pandoc -> HTML/CSS + KaTeX -> Chromium headless (system Chrome) -> PDF
# Run from docdev/ ; use `nice -n 15 make ...` while the sensitivity campaign is running.
# ---------------------------------------------------------------------------
PY      ?= python3
NODE    ?= node
DOC      = out/CIRCEO-OPS-DES-861_revA_HORIZON_v2.pdf

.PHONY: all pdf figures generated deps clean distclean check

all: pdf

## Build the PDF from doc/main.md (default target)
pdf: $(DOC)

$(DOC): doc/main.md doc/cover.md style.css build.py render.js tools/hyp_table.py $(wildcard fig/*)
	$(PY) build.py

## Run OUR figure generators (horizon.viz.tech_figures, read-only use of src/) -> fig/
figures:
	nice -n 15 $(PY) figures/gen_figures.py

## Regenerate the Markdown fragments derived from the repository (hypothesis register)
generated:
	$(PY) tools/hyp_table.py

## Python deps; Chrome and pandoc are system packages; playwright-core drives Chrome
deps:
	$(PY) -m pip install -r requirements.txt
	@echo "needs: pandoc, google-chrome (CHROME_BIN), node + playwright-core (npm i -g playwright-core)"

## Quick checks on the produced PDF (pagination, TOC, numbering, fonts, placeholders)
check: $(DOC)
	@$(PY) tools/check_pdf.py $(DOC)

clean:
	rm -rf out body.html cover.html doc/generated

distclean: clean
	rm -rf node_modules
