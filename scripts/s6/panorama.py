"""S6 progress panorama (markdown, French): archive coverage, extraction runs, router replays on
real forecasts, forecast scores vs the S5 emulator. Run every ~30 min for the client update.

    python3 scripts/s6/panorama.py [--no-scores]
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FC = "boris-circeo/circeo-meteo-forecasts"
FETCH = "/home/claude/circeo-meteo/client/fetch_meteo.py"


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


def coverage() -> list[str]:
    out = ["**Archive (mois disponibles)**", ""]
    rels = gh(f"repos/{FC}/releases?per_page=100") or []
    by = collections.defaultdict(set)
    for r in rels:
        tag = r["tag_name"]
        if tag.startswith(("scores", "verify")):
            continue
        prod = re.sub(r"-\d{4}$", "", tag)
        assets = r.get("assets", [])
        if len(assets) >= 100:  # embedded list truncated: page through
            assets, p = [], 1
            while True:
                a = gh(f"repos/{FC}/releases/{r['id']}/assets?per_page=100&page={p}") or []
                assets += a
                if len(a) < 100:
                    break
                p += 1
        for a in assets:
            m = re.search(r"_(\d{6})(\d{2})?(_d\d+)?\.nc$", a["name"])
            if m:
                by[prod].add(m.group(1))
    for prod in sorted(by):
        ms = sorted(m for m in by[prod] if m <= "202512")
        yrs = collections.Counter(m[:4] for m in ms)
        out.append(f"- {prod} : {len(ms)} mois ({', '.join(f'{y}:{n}' for y, n in sorted(yrs.items()))})")
    return out


def runs() -> list[str]:
    d = gh(f"repos/{FC}/actions/runs?per_page=60") or {"workflow_runs": []}
    act = [r for r in d["workflow_runs"] if r["status"] != "completed"]
    c = collections.Counter(r["name"] for r in act)
    return ["**Extraction en cours** : " + (", ".join(f"{n} {k} run(s)" for k, n in c.items()) or "aucune"), ""]


def replays() -> list[str]:
    rows = collections.defaultdict(dict)
    for f in glob.glob(str(ROOT / "outputs/s5/runs/*_30d__*.json")):
        r = json.loads(Path(f).read_text())
        cid = r["id"]
        m = re.search(r"__((20(2[3-9]))-\d\d-\d\d)_30d__s(\d)", cid)
        if not m:
            continue
        name, ovr = cid.split("__")[:2]
        lab = {"B0": "Point fixe B0", "Oracle_REF_H": "Oracle (borne)"}.get(name)
        if lab is None and name == "ENS_REF":
            lab = "Routeur ENSEMBLE — " + {"base": f"émulateur (s{m.group(4)})"}.get(
                ovr, "réel " + ovr.split("=")[-1].upper())
        if lab is None:
            lab = {"base": f"Émulateur S5 (s{m.group(4)})", "error_scale=0": "Prévision parfaite"}.get(
                ovr, "Réelle : " + ovr.split("=")[-1].upper() + (" (contrôle)" if ovr == "forecast=ens" else ""))
        rows[(m.group(2), lab)][m.group(1)[5:7]] = r["cf_pct"]
    out = ["**Rejeux du routeur HORIZON v2 (zone S5, fenêtres de 30 j, FC %)**", ""]
    for year in sorted({y for y, _ in rows}):
        wins = sorted({w for (y, _), v in rows.items() if y == year for w in v})
        out += [f"_{year}_", "", "| Prévision | " + " | ".join(wins) + " | Moyenne |",
                "|---|" + "---|" * (len(wins) + 1)]
        order = ["Point fixe B0", "Émulateur S5 (s1)", "Émulateur S5 (s2)"]  # then real, perfect, ENS router
        labs = sorted({l for (y, l) in rows if y == year},
                      key=lambda l: (order.index(l) if l in order else 3 if l.startswith("Réelle") else
                                     7 if l.startswith("Routeur") else 5, l))
        for lab in labs:
            v = rows[(year, lab)]
            cells = [f"{v[w]:.1f}" if w in v else "…" for w in wins]
            full = len(v) == len(wins)
            mean = f"{sum(v.values()) / len(v):.1f}" + ("" if full else "*")
            out.append(f"| {lab} | " + " | ".join(cells) + f" | {mean} |")
        out.append("")
    out.append("(* moyenne partielle)")
    return out


def scores() -> list[str]:
    d = Path("/tmp/s6/scores")
    subprocess.run(["python3", FETCH, "--repo", FC, "--release", "scores-v1", "--pattern",
                    "scores_*.nc", "--dest", str(d)], capture_output=True)
    r = subprocess.run(["python3", str(ROOT / "scripts/s6/compare_emulator.py"), "--scores", str(d),
                        "--emu", str(ROOT / "outputs/s6/emu.json"),
                        "--out", str(ROOT / "outputs/s6/report")], capture_output=True, text=True,
                       cwd=ROOT)
    md = (ROOT / "outputs/s6/report/fc_vs_emulator.md")
    if not md.exists():
        return ["**Scores vs émulateur** : indisponibles (" + r.stderr[-200:] + ")"]
    txt = md.read_text().split("## Common inits")[0]
    tab = [l for l in txt.splitlines() if l.startswith("|")]
    return ["**Qualité des prévisions vs émulateur (vue routeur ; entre parenthèses : émulateur)**",
            ""] + tab + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scores", action="store_true")
    a = ap.parse_args()
    lines = replays() + [""]
    if not a.no_scores:
        lines += scores()
    lines += coverage() + [""] + runs()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
