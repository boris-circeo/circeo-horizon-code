"""Tracking helpers: version tags, fingerprints, flatten, and an MLflow round trip in tmp."""
import pytest

from horizon import tracking


def test_flatten_nested_and_lists():
    out = tracking.flatten("router", {"a": 1, "b": {"c": 2.5}, "d": [1, 2]})
    assert out == {"router.a": "1", "router.b.c": "2.5", "router.d": "[1, 2]"}


def test_code_version_has_commit():
    v = tracking.code_version()
    assert set(v) == {"code.commit", "code.branch", "code.dirty"}
    assert v["code.commit"]


def test_fingerprint_changes_with_content(tmp_path, monkeypatch):
    monkeypatch.setattr(tracking, "TRACK_DIR", tmp_path / "t")
    (tmp_path / "e").mkdir()
    (tmp_path / "p").mkdir()
    g = tmp_path / "e" / "wind_2015_01.grib"
    g.write_bytes(b"abc")
    (tmp_path / "p" / "polar.csv").write_text("1,2\n")
    v1 = tracking.data_version(tmp_path / "e", tmp_path / "p", 2015)
    assert v1["data.era5_files"] == "1" and v1["data.era5_kind"] == "grib"
    g.write_bytes(b"abcd")
    v2 = tracking.data_version(tmp_path / "e", tmp_path / "p", 2015)
    assert v1["data.era5_sha"] != v2["data.era5_sha"]
    assert v1["data.polar_sha"] == v2["data.polar_sha"]


def test_log_result_roundtrip(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    monkeypatch.setattr(tracking, "TRACK_DIR", tmp_path)
    uri = f"sqlite:///{tmp_path / 'm.db'}"
    res = {"cf_pct": 80.5, "energy_mwh": 1.0, "manoeuvres": {"per_day": 2.5, "total": 75},
           "segments": [{"cf": 0.8}, {"cf": 0.81}]}
    rid = tracking.log_result("t", res, {"router.name": "X"}, {"code.commit": "abc"}, uri=uri)
    mlflow.set_tracking_uri(uri)
    run = mlflow.get_run(rid)
    assert run.data.metrics["cf_pct"] == 80.5
    assert run.data.metrics["manoeuvres_per_day"] == 2.5
    assert run.data.params["router.name"] == "X" and run.data.tags["code.commit"] == "abc"
