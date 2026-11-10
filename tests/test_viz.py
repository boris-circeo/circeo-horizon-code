"""Tests of the router inspector export and the static HTML page."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from horizon.geo.coast import CoastModel
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DirectPowerModel,
    EnvelopePowerModel,
    HoldAtPointPolicy,
    run_mission,
)
from horizon.viz import (
    RecordingPolicy,
    SeedRun,
    build_html,
    export_backtest,
    load_export,
    merge_exports,
    save_export,
    validate_export,
)
from horizon.viz.export import decode_array
from horizon.weather.synthetic import SyntheticWeather

DAY = 86400.0
EPOCH = np.datetime64("2026-01-01T00:00:00", "s")


class _DiagPolicy(HoldAtPointPolicy):
    """Hold policy exposing ``last_diagnostics`` like the ensemble policies."""

    last_diagnostics = None

    def plan(self, t_s, x, y, provider):
        self.last_diagnostics = {"medoid_weights": np.array([0.6, 0.4]), "explained_variance": 0.8}
        return super().plan(t_s, x, y, provider)


@pytest.fixture(scope="module")
def export():
    grid = Grid.from_bbox(-20, 0, 40, 55, 80e3)
    sdf = np.full(grid.shape, 5e5, dtype=np.float32)
    sdf[:, :3] = -1e4  # a strip of land
    coast = CoastModel(grid, sdf)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    pm = EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))
    T = 3 * DAY
    wx = SyntheticWeather(grid, EPOCH, T, seed=5)
    truth = wx.truth(dt_s=3600.0)
    x0, y0 = grid.to_xy(-10.0, 47.0)
    runs = {}
    recs = {}
    pols = {"B0": HoldAtPointPolicy(x0 + 2e5, y0), "Oracle": _DiagPolicy(x0, y0 + 1e5)}
    for name, pol in pols.items():
        rp = RecordingPolicy(pol)
        runs[name] = run_mission(rp, wx, truth, (-10.0, 47.0), T, pm, coast)
        recs[name] = rp.records
    sr = [SeedRun(7, truth, runs, wx, recs)]
    mask = np.ones(grid.shape, bool)
    mask[:, -2:] = False
    return export_backtest(sr, coast, start_lonlat=(-10.0, 47.0), fc_horizon_days=1.0,
                           params={"k": 1}, polar=polar, weather_kind="era5",
                           era5_mask=mask), coast


def test_schema_and_roundtrip(export, tmp_path):
    data, _ = export
    validate_export(data)
    assert data["schema_version"] == 1
    for ext in (".json", ".json.gz"):
        p = save_export(data, tmp_path / f"e{ext}")
        assert load_export(p) == data
    s = data["seeds"][0]
    n = len(s["t_s"])
    r = s["runs"]["Oracle"]
    assert len(r["energy_kwh"]) == n and len(r["power_kw"]) == n - 1
    # exported energy is consistent with the metric
    assert r["energy_kwh"][-1] == pytest.approx(r["metrics"]["energy_kwh"], abs=0.2)
    w = s["wind"]
    q = decode_array(w["u"])
    assert q.dtype == np.int8 and q.shape == (w["nt"], w["ny"], w["nx"])
    assert 0.0 <= r["diag"]["productive_share"] <= 1.0
    assert sum(r["diag"]["tws_hist"]) == pytest.approx(1.0, abs=1e-3)
    assert s["forecast_error"]["by_policy"]["B0"]["mae_tws_ms"][0] is not None


def test_polar_and_era5_fields(export):
    data, _ = export
    pl = data["polar"]
    q = decode_array(pl["p"])
    shape = (len(pl["tws_kn"]), len(pl["twa_deg"]), len(pl["u_ms"]))
    assert q.dtype == np.int16 and q.shape == shape
    assert all(abs(k - 2 * round(k / 2)) < 0.6 for k in pl["tws_kn"])
    # round trip of a feasible node within the quantisation step
    from horizon.polar import synthetic_polar
    ref = synthetic_polar()
    i = len(pl["tws_kn"]) // 2
    j = int(np.argmin(abs(ref.tws / 0.514444 - pl["tws_kn"][i])))
    ok = q[i] != pl["infeasible"]
    assert np.allclose(q[i][ok] * pl["scale_kw"], ref.p[j][ok], atol=0.51)
    assert data["meta"]["weather_kind"] == "era5"
    assert decode_array(data["map"]["era5_mask"]).shape == decode_array(data["map"]["sdf"]).shape
    assert data["seeds"][0]["epoch"].startswith("2026-01-01")
    assert len(data["seeds"][0]["runs"]["B0"]["speed_ms"]) == len(data["seeds"][0]["t_s"]) - 1


def test_html_with_polar_and_existing_s2_export(export):
    data, _ = export
    html = build_html(data)
    assert "renderPolar" in html and not re.findall(r"https?://", html)
    s2 = Path(__file__).resolve().parents[1] / "outputs" / "s2_inspector" / "s2_export.json.gz"
    if s2.exists():  # old export without polar / epoch / speed must still build
        d2 = load_export(s2)
        assert "polar" not in d2
        assert "hz-data" in build_html(d2)


def test_recorder_and_diagnostics(export):
    data, _ = export
    reps = data["seeds"][0]["runs"]["Oracle"]["replans"]
    assert reps[0]["diag"]["medoid_weights"] == [0.6, 0.4]
    assert "plan" in reps[0]
    assert "diag" not in data["seeds"][0]["runs"]["B0"]["replans"][0]


def test_merge(export):
    data, _ = export
    import copy
    extra = copy.deepcopy(data)
    extra["policies"] = [{"name": "X"}]
    extra["seeds"][0]["runs"] = {"X": extra["seeds"][0]["runs"]["B0"]}
    extra["seeds"][0].pop("forecast_error")
    merged = merge_exports(copy.deepcopy(data), extra)
    assert "X" in merged["seeds"][0]["runs"] and "X" in [p["name"] for p in merged["policies"]]
    validate_export(merged)


def test_invalid_export_rejected(export):
    data, _ = export
    bad = {**data, "schema_version": 99}
    with pytest.raises(ValueError):
        validate_export(bad)


def test_hold_counts_as_in_twa_band(export):
    data, _ = export
    d = data["seeds"][0]["runs"]["B0"]["diag"]  # B0 holds almost all the time
    assert d["hold_share"] > 0.5
    assert d["productive_share"] > 0.5 * d["tws_band_share"] or d["tws_band_share"] < 0.1
    assert d["productive_share"] <= d["tws_band_share"] + 1e-9


def test_content_bilingual_and_filled(export):
    import json
    import re

    from horizon.viz.inspector import _CONTENT, load_content

    data, _ = export
    c = load_content(data)
    ids = {lang: re.findall(r"\{#([\w-]+)\}", c["guide"][lang]) for lang in ("en", "fr")}
    assert ids["en"] == ids["fr"] and {"use", "matrix", "hyp", "limits", "path"} <= set(ids["en"])
    assert "{{" not in json.dumps(c)
    g = json.loads((_CONTENT / "glossary.json").read_text("utf-8"))
    for sec in ("defs", "captions", "ui", "chips"):
        for k, v in g[sec].items():
            assert v["en"] and v["fr"], (sec, k)
    for step in g["tour"]:
        assert step["en"] and step["fr"]
    # every [[term]] used in texts exists in the glossary
    text = json.dumps(c, ensure_ascii=False)
    for m in re.findall(r"\[\[([^\]|]+)", text):
        assert m in g["defs"] or m.lower() in g["defs"], m


def test_size_budget(export):
    data, _ = export
    html = build_html(data)
    assert len(html.encode()) < 15e6


@pytest.mark.parametrize("gz", [True, False])
def test_html_embeds_data_and_is_offline(export, gz):
    data, _ = export
    html = build_html(data, gzip_data=gz)
    assert 'id="hz-data"' in html and html.count("<script") == 3 and "hz-content" in html
    assert "<!--__DATA__-->" not in html and "<!--__TITLE__-->" not in html
    assert not re.findall(r"https?://", html)
    assert not re.search(r"<(script|link|img)[^>]+(src|href)\s*=", html)
    if not gz:
        assert '"schema_version":1' in html


def test_headless_boot(export):
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if chrome is None:
        pytest.skip("no headless browser")
    data, _ = export
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "i.html"
        f.write_text(build_html(data, gzip_data=False), encoding="utf-8")
        cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
               "--disable-background-networking", "--disable-component-update", "--disable-sync",
               f"--user-data-dir={d}/prof", "--dump-dom", f.as_uri()]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=25).stdout
        except subprocess.TimeoutExpired:
            pytest.skip("headless browser did not terminate")
    assert '<div class="card"><h2>Summary' in out and 'class="err">Failed' not in out
