"""Experiment tracking (MLflow, Apache-2.0) for HORIZON runs.

Every simulated case can be recorded as one MLflow *run* carrying:

* **code version**: ``code.commit`` (git SHA of this repository), ``code.dirty`` (uncommitted
  changes under ``src/`` or ``scripts/`` at run time), ``code.branch``;
* **data version**: ``data.commit`` (git SHA of the private data repository, when it is a git
  clone), ``data.era5_sha`` and ``data.polar_sha`` (content fingerprints of the ERA5 GRIB files and
  of the BETA polar CSVs actually used), ``data.era5_files`` (count) and ``data.year``;
* **parameters**: the full (defaults-expanded) router and environment configuration, flattened as
  ``router.<key>`` / ``env.<key>``, plus the window start and length;
* **metrics**: capacity factor, energy, manoeuvres, storm exposure, coast margin, compute cost.

Storage is local and private by default: an SQLite file plus an artifact folder under
``outputs/tracking/`` (git-ignored, because results are derived from confidential client data).
Override with ``HORIZON_MLFLOW_URI`` (any MLflow tracking URI) and disable recording with
``HORIZON_TRACKING=0``. Browse with::

    mlflow ui --backend-store-uri sqlite:///outputs/tracking/mlflow.db

Content fingerprints hash file bytes once and are cached in ``outputs/tracking/fingerprints.json``
keyed by (path, size, mtime), so recording a run costs milliseconds.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACK_DIR = ROOT / "outputs" / "tracking"
DEFAULT_URI = f"sqlite:///{TRACK_DIR / 'mlflow.db'}"

# MLflow metric name -> key in a result dict produced by scripts/s5/s5lib.run_case
RESULT_METRICS = {
    "cf_pct": "cf_pct", "energy_mwh": "energy_mwh", "hours": "hours", "hold_share": "hold_share",
    "distance_km": "distance_km", "storm35_h": "storm35_h", "storm45_h": "storm45_h",
    "mean_tws_ms": "mean_tws_ms", "min_coast_margin_km": "min_coast_margin_km",
    "guard_interventions": "guard_interventions", "coast_violations": "coast_violations",
    "n_replans": "n_replans", "n_clamped": "n_clamped", "wall_s": "wall_s", "cpu_s": "cpu_s",
    "peak_rss_mb": "peak_rss_mb",
}


def enabled() -> bool:
    """False when ``HORIZON_TRACKING=0`` or MLflow is not installed."""
    if os.environ.get("HORIZON_TRACKING", "1") == "0":
        return False
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return False
    return True


def _git(repo: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                             timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def code_version(repo: Path = ROOT) -> dict:
    """``{"code.commit", "code.branch", "code.dirty"}`` of the repository at call time."""
    status = _git(repo, "status", "--porcelain", "--", "src", "scripts")
    return {"code.commit": _git(repo, "rev-parse", "--short=10", "HEAD") or "unknown",
            "code.branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "unknown",
            "code.dirty": "unknown" if status is None else str(bool(status))}


def _fingerprint(files: list[Path]) -> str:
    """SHA-256 over (name, bytes) of ``files``, with a (path, size, mtime) cache."""
    cache_f = TRACK_DIR / "fingerprints.json"
    try:
        cache = json.loads(cache_f.read_text())
    except (OSError, ValueError):
        cache = {}
    h = hashlib.sha256()
    dirty = False
    for f in sorted(files):
        st = f.stat()
        key = f"{f.resolve()}|{st.st_size}|{int(st.st_mtime)}"
        if key not in cache:
            fh = hashlib.sha256()
            with open(f, "rb") as fp:
                for chunk in iter(lambda: fp.read(1 << 22), b""):
                    fh.update(chunk)
            cache[key] = fh.hexdigest()
            dirty = True
        h.update(f.name.encode())
        h.update(cache[key].encode())
    if dirty:
        TRACK_DIR.mkdir(parents=True, exist_ok=True)
        cache_f.write_text(json.dumps(cache, indent=0))
    return h.hexdigest()[:16]


def data_version(era5_dir: Path, polar_dir: Path, year: int | None = None) -> dict:
    """Version tags of the weather and polar inputs (git commit of their repo + content hashes).

    ``era5_dir`` holds ``wind_<year>_<mm>.grib`` (symlinks are followed); when only derived npz
    caches exist, those are fingerprinted instead and ``data.era5_kind`` says so.
    """
    era5_dir, polar_dir = Path(era5_dir), Path(polar_dir)
    pattern = f"wind_{year}_*.grib" if year else "wind_*.grib"
    gribs = sorted(era5_dir.glob(pattern))
    kind = "grib"
    if not gribs:
        gribs, kind = sorted(era5_dir.glob(f"era5_uv_{year or ''}*.npz")), "npz-cache"
    polars = sorted(polar_dir.glob("*.csv"))
    real = Path(os.path.realpath(gribs[0])).parent if gribs else era5_dir
    return {"data.commit": _git(real, "rev-parse", "--short=10", "HEAD")
            or _git(polar_dir, "rev-parse", "--short=10", "HEAD") or "none",
            "data.era5_sha": _fingerprint(gribs) if gribs else "none",
            "data.era5_kind": kind, "data.era5_files": str(len(gribs)),
            "data.polar_sha": _fingerprint(polars) if polars else "none",
            "data.year": str(year) if year else "all"}


def flatten(prefix: str, d: dict) -> dict:
    """``{"a": {"b": 1}}`` -> ``{"<prefix>.a.b": "1"}`` (MLflow params are strings)."""
    out = {}
    for k, v in d.items():
        name = f"{prefix}.{k}"
        if isinstance(v, dict):
            out.update(flatten(name, v))
        else:
            out[name] = json.dumps(v) if isinstance(v, (list, tuple)) else str(v)
    return out


def log_result(experiment: str, result: dict, params: dict, tags: dict,
               uri: str | None = None, run_name: str | None = None,
               artifacts: list[Path] | None = None) -> str:
    """Record one finished case; returns the MLflow run id.

    result : dict with the :data:`RESULT_METRICS` keys (missing keys are skipped), a
        ``manoeuvres`` dict (``per_day``, ``total``) and optional ``segments`` (per-segment CF,
        logged as the ``segment_cf_pct`` series). params : flat ``str -> str`` mapping.
    tags : flat mapping (code / data versions, campaign, case id...).
    """
    import mlflow

    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(uri or os.environ.get("HORIZON_MLFLOW_URI", DEFAULT_URI))
    if mlflow.get_experiment_by_name(experiment) is None:
        mlflow.create_experiment(experiment,
                                 artifact_location=(TRACK_DIR / "artifacts").as_uri())
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags({k: str(v) for k, v in tags.items()})
        items = list(params.items())
        for i in range(0, len(items), 100):  # MLflow batches params by 100
            mlflow.log_params(dict(items[i:i + 100]))
        m = {name: float(result[key]) for name, key in RESULT_METRICS.items()
             if isinstance(result.get(key), (int, float))}
        man = result.get("manoeuvres") or {}
        for k in ("per_day", "total", "tack", "gybe"):
            if isinstance(man.get(k), (int, float)):
                m[f"manoeuvres_{k}"] = float(man[k])
        mlflow.log_metrics(m)
        for i, seg in enumerate(result.get("segments") or []):
            if isinstance(seg.get("cf"), (int, float)):
                mlflow.log_metric("segment_cf_pct", 100.0 * float(seg["cf"]), step=i)
        for a in artifacts or []:
            mlflow.log_artifact(str(a))
        return run.info.run_id
