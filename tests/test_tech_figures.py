"""Technical Guide figures (real data and code): generation, content and size budgets.

The generator runs on the S4 year export (client data stays local, git-ignored); every test is
skipped when it is absent. Figures whose inputs (ERA5 cache, value models) are missing are skipped
by the generator itself, so only the figures that can be built are checked.
"""

import json
import re
from pathlib import Path

import pytest

from horizon.viz.tech_figures import FIGURE_IDS, _SafeStats, build_tech_figures
from horizon.viz.tech_figures_text import TEXTS

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "outputs" / "s4_inspector" / "year.json.gz"
pytestmark = pytest.mark.skipif(not EXPORT.exists(), reason="S4 year export not available")

BUDGET = 160_000
UNIT = re.compile(r"\[(kW|m/s|km|deg|MWh|GWh|%|days|h|kn)[^\]]*\]|percentage points|\bkW\b|\bm/s\b")


@pytest.fixture(scope="module")
def figures():
    from horizon.viz import load_export

    figs = build_tech_figures(load_export(EXPORT))
    if not figs:
        pytest.skip("no client data to build the figures")
    return figs


def test_texts_cover_all_figures():
    assert set(TEXTS) == set(FIGURE_IDS)
    for t in TEXTS.values():
        assert set(t) == {"title_fr", "title_en", "caption_fr", "caption_en", "body_fr", "body_en"}


def test_each_figure_is_complete(figures):
    assert {f["id"] for f in figures} <= set(FIGURE_IDS)
    for f in figures:
        for k in ("title_fr", "title_en", "caption_fr", "caption_en", "body_fr", "body_en", "svg"):
            assert isinstance(f[k], str) and f[k].strip(), (f["id"], k)
        assert f["svg"].lstrip().startswith("<svg") and "viewBox" in f["svg"]
        assert "width=" not in f["svg"][:f["svg"].index(">")]  # scales with its container
        for k in ("body_fr", "body_en"):
            n = len(f[k].split())
            assert 150 <= n <= 520, (f["id"], k, n)
            assert "{" not in f[k] and not re.search(r"\bnan\b", f[k].lower()), (f["id"], k)
        assert "{" not in f["caption_en"] + f["caption_fr"]


def test_story_order_and_pointers(figures):
    ids = [f["id"] for f in figures]
    order = ["architecture", "polar", "forecast", "safety", "envelope", "dp", "ensemble",
             "terminal", "refiner", "mpc", "results"]
    assert ids == list(FIGURE_IDS) == order
    for i, f in enumerate(figures):
        assert f["title_en"].startswith(f"Fig. {i + 1}/11"), f["title_en"]
        assert f["title_fr"].startswith(f"Fig. {i + 1}/11"), f["title_fr"]
        if f["id"] != "architecture":
            assert "Where we are in the story" in f["body_en"]
            assert "Où nous en sommes" in f["body_fr"]
        assert "What to look at in the inspector" in f["body_en"] or f["id"] == "architecture"
    for f in figures:
        if f["id"] in ("envelope", "refiner"):
            assert "S5" in f["body_en"] and "S5" in f["body_fr"]


def test_axes_have_units(figures):
    for f in figures:
        texts = " ".join(re.findall(r">([^<>]+)</text>", f["svg"]))
        assert len(UNIT.findall(texts)) >= 3, f["id"]  # axis labels carry units
        assert "m/s" in texts or "kW" in texts or "MWh" in texts or "%" in texts


def test_size_budget(figures):
    for f in figures:
        assert len(f["svg"]) <= BUDGET, (f["id"], len(f["svg"]))
    assert sum(len(f["svg"]) for f in figures) <= 1_500_000


def test_numbers_come_from_the_run(figures):
    by = {f["id"]: f for f in figures}
    if "results" in by:
        body = by["results"]["body_en"]
        assert "optimal fixed station (perfect hindsight)" in body
        assert "points" in body and "50 km" in body
        assert "poste fixe optimal (avec clairvoyance)" in by["results"]["body_fr"]
        cf = [float(x) for x in re.findall(r"Annual CF: oracle ([\d.]+) %", body)]
        assert cf and 50 < cf[0] < 100
    if "safety" in by:
        assert "20 km" in by["safety"]["body_en"]


def test_safe_stats_and_hook(figures):
    assert _SafeStats({"a": 1.0})["missing"] != _SafeStats({"a": 1.0})["missing"]  # nan
    from horizon.viz import build_html, load_export

    data = load_export(EXPORT)
    page = build_html(data, tech_figures=figures[:1], gzip_data=False)
    m = re.search(r'<script id="hz-content" type="application/json">(.*?)</script>', page, re.S)
    content = json.loads(m.group(1).replace("\\u003c", "<"))
    assert content["tech_figures"][0]["id"] == figures[0]["id"]
    assert "tech_figures" not in page.split('id="hz-data"')[1].split("</script>")[0][:50]
