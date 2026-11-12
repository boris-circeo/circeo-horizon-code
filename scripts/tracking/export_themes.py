"""Export tracked runs as one MLflow SQLite store per theme (for sharing, e.g. on Google Drive).

Usage: ``python3 scripts/tracking/export_themes.py [--themes scripts/tracking/themes.yaml]
[--only NAME ...] [--max-mb 2.9]``

Each theme becomes ``outputs/tracking/export/horizon_mlflow_<theme>_<YYYYMMDD-HHMM>.db`` with one
MLflow experiment named after the theme, rebuilt from the result JSONs (``outputs/s5/runs``), so
the files are independent and uncompressed. Themes with no finished case are skipped; a file larger
than ``--max-mb`` is reported (split its theme further in themes.yaml). Prints a JSON manifest
(theme, file, runs, size, sha256) on the last line.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "scripts" / "s5"))
sys.path.append(str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import s5lib as L  # noqa: E402
import yaml  # noqa: E402

from horizon import tracking  # noqa: E402

BASELINE = ("B1c_5d_REF", "Oracle_REF_H", "B0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", default=str(ROOT / "scripts/tracking/themes.yaml"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--max-mb", type=float, default=2.9)
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.themes).read_text())
    stamp = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y%m%d-%H%M")
    out_dir = tracking.TRACK_DIR / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for th in cfg["themes"]:
        if a.only and th["name"] not in a.only:
            continue
        cases = L.expand(L.load_campaign(str(ROOT / th["campaign"])))
        want = set(th["experiments"])
        sel = [c for c in cases if want & set(c["experiments"])]
        wins = {c["spec"]["start"] for c in sel}
        if th.get("with_baseline"):
            base = [c for c in L.expand(L.load_campaign(str(ROOT / "scripts/s5/campaign.yaml")))
                    if c["spec"]["router"]["name"] in BASELINE and len(c["spec"]["router"]) == 1
                    and not c["spec"]["env"] and c["spec"]["start"] in wins]
            ids = {c["id"] for c in sel}
            sel += [c for c in base if c["id"] not in ids]
        done = [c for c in sel if L.is_done(c["id"])]
        if not done:
            continue
        f = out_dir / f"horizon_mlflow_{th['name']}_{stamp}.db"
        f.unlink(missing_ok=True)
        uri = f"sqlite:///{f}"
        for c in done:
            out = json.loads(L.result_path(c["id"]).read_text())
            if "versions" not in out:
                out["versions"] = {"code.commit": "54aadcb", "code.branch": "main",
                                   "code.dirty": "False", "code.source": "retro-import",
                                   **{k: v for k, v in L.versions().items()
                                      if k.startswith("data.")}}
            L.track_case(c["spec"], out, experiment=th["name"], uri=uri,
                         extra_tags={"theme": th["name"], "experiments": ",".join(
                             c["experiments"])})
        mb = f.stat().st_size / 2**20
        manifest.append({"theme": th["name"], "file": str(f), "runs": len(done),
                         "of": len(sel), "mb": round(mb, 2),
                         "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
        warn = "  TOO LARGE: split this theme" if mb > a.max_mb else ""
        print(f"{th['name']}: {len(done)}/{len(sel)} runs, {mb:.2f} MB{warn}", flush=True)
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
