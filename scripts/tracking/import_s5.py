"""Import finished S5 campaign cases (outputs/s5/runs/*.json) into MLflow.

Usage: ``python3 scripts/tracking/import_s5.py [--code-commit SHA] [--experiment NAME]``

Cases already present in the experiment (same ``case_id`` tag) are skipped, so the script is
idempotent. Results written before tracking existed carry no ``versions`` block: they get
``--code-commit`` (default: the commit the S5 campaign ran on, 54aadcb; ``src/`` was unchanged
from 8d57542 to 54aadcb) with ``code.source=retro-import`` and the data fingerprints of the files
currently on disk (identical to the campaign inputs: the data repo has not changed since).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "s5"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import s5lib as L  # noqa: E402

from horizon import tracking  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-commit", default="54aadcb")
    ap.add_argument("--experiment", default="S5-sensitivity")
    a = ap.parse_args()
    import mlflow
    mlflow.set_tracking_uri(tracking.DEFAULT_URI)
    seen = set()
    exp = mlflow.get_experiment_by_name(a.experiment)
    if exp is not None:
        df = mlflow.search_runs([exp.experiment_id], max_results=100000)
        if len(df) and "tags.case_id" in df:
            seen = set(df["tags.case_id"])
    data = L.versions()
    retro = {"code.commit": a.code_commit, "code.branch": "main", "code.dirty": "False",
             "code.source": "retro-import",
             **{k: v for k, v in data.items() if k.startswith("data.")}}
    n_new = 0
    for p in sorted((L.OUT / "runs").glob("*.json")):
        out = json.loads(p.read_text())
        if out.get("status") != "ok" or out["id"] in seen:
            continue
        if "versions" not in out:
            out["versions"] = retro
        L.track_case(out["spec"], out, experiment=a.experiment,
                     extra_tags={"campaign": "S5", "sprint": "S5"})
        n_new += 1
    print(f"imported {n_new} cases ({len(seen)} already present) into '{a.experiment}'")


if __name__ == "__main__":
    main()
