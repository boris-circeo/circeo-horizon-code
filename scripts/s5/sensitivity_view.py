"""Curated S5 sensitivity summary (FR/EN) for the inspector's Sensitivity tab.

Usage: ``python3 scripts/s5/sensitivity_view.py [--out outputs/s5/sensitivity_view.json]``, then
``python3 scripts/build_inspector.py --results ... --sensitivity outputs/s5/sensitivity_view.json``.
Only aggregates (paired deltas, SE, z, oracle gaps) are written.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s5lib as L  # noqa: E402
from sensitivity import compute_rows  # noqa: E402

B1C, ENS = "B1c_5d_REF", "ENS_REF"
# (group fr, group en, [(fr, en, router, router_ovr, env_ovr), ...])
GROUPS = [
    ("Qualité de la prévision", "Forecast quality", [
        ("Prévision parfaite (erreur ×0)", "Perfect forecast (error ×0)", B1C, {},
         {"error_scale": 0.0}),
        ("Erreur ×0,5", "Error ×0.5", B1C, {}, {"error_scale": 0.5}),
        ("Erreur ×1,5", "Error ×1.5", B1C, {}, {"error_scale": 1.5}),
        ("Erreur ×2", "Error ×2", B1C, {}, {"error_scale": 2.0}),
        ("Erreur de position/timing seule", "Displacement-only error", B1C, {},
         {"amp_scale": 0.0, "disp_scale": 1.27, "noise_scale": 0.0}),
        ("Erreur d'intensité + bruit seule", "Intensity + noise error only", B1C, {},
         {"amp_scale": 2.53, "disp_scale": 0.0, "noise_scale": 2.53}),
        ("Erreurs « analogues » ERA5", "ERA5 analog errors", B1C, {},
         {"analog_scale": 0.961, "structure": "analog"}),
        ("Latence 0 h", "Latency 0 h", B1C, {}, {"latency_h": 0.0}),
        ("Latence 12 h", "Latency 12 h", B1C, {}, {"latency_h": 12.0}),
        ("Sans cohérence entre émissions", "No issue-to-issue consistency", B1C, {},
         {"consistency": False}),
    ]),
    ("Polaire réelle (le routeur garde la nominale)", "Truth polar (router keeps nominal)", [
        ("Puissance −10 %", "Power −10 %", B1C, {}, {"truth_polar_scale": 0.9}),
        ("Puissance +10 %", "Power +10 %", B1C, {}, {"truth_polar_scale": 1.1}),
        ("Angle au vent −10°", "TWA −10°", B1C, {}, {"truth_polar_twa_shift": -10.0}),
        ("Angle au vent +10°", "TWA +10°", B1C, {}, {"truth_polar_twa_shift": 10.0}),
    ]),
    ("Architecture du routeur", "Router architecture", [
        ("Sans raffineur continu", "No continuous refiner", B1C, {"refiner_h": 0.0}, {}),
        ("Raffineur 24 h", "Refiner 24 h", B1C, {"refiner_h": 24.0}, {}),
        ("Sans valeur terminale (horizon 5 j)", "No terminal value (5 d horizon)", B1C,
         {"terminal": "zero"}, {}),
        ("Sans valeur terminale, horizon 10 j", "No terminal value, 10 d horizon", B1C,
         {"horizon_days": 10.0, "terminal": "zero"}, {}),
        ("Horizon 3 j", "Horizon 3 d", B1C, {"horizon_days": 3.0}, {}),
        ("Horizon 10 j", "Horizon 10 d", B1C, {"horizon_days": 10.0}, {}),
        ("Replanification 24 h", "Replan every 24 h", B1C, {"replan_h": 24.0}, {}),
        ("Replanification 3 h", "Replan every 3 h", B1C, {"replan_h": 3.0}, {}),
        ("Grille 20 km", "20 km grid", B1C, {}, {"grid_km": 20.0}),
    ]),
    ("Opérations et environnement", "Operations & environment", [
        ("Pertes de manœuvre ignorées", "Manoeuvre losses off", B1C, {}, {"manoeuvre": False}),
        ("Manœuvres 2,5× plus longues", "Manoeuvres 2.5× longer", B1C, {}, {"tau_scale": 2.5}),
        ("Marge côtière 40 km", "Coast clearance 40 km", B1C, {}, {"d_min_km": 40.0}),
        ("Évitement tempête > 45 kn", "Storm avoidance > 45 kn", B1C, {"storm_kn": 45.0}, {}),
        ("Départ de Lorient", "Start from Lorient", B1C, {}, {"start": "lorient"}),
        ("Départ milieu Atlantique", "Mid-Atlantic start", B1C, {}, {"start": "mid_atlantic"}),
    ]),
    ("Routeur d'ensemble (4 fenêtres)", "Ensemble router (4 windows)", [
        ("ENS au lieu de B1c (nominal)", "ENS instead of B1c (nominal)", "ENS_vs_B1c", {}, {}),
        ("ENS 10 membres", "ENS 10 members", ENS, {"members": 10.0}, {}),
        ("ENS 3 scénarios", "ENS 3 scenarios", ENS, {"k": 3.0}, {}),
        ("ENS aversion au risque γ 0,3", "ENS risk aversion γ 0.3", ENS, {"gamma": 0.3}, {}),
    ]),
]


def ens_vs_b1c():
    """Paired ENS - B1c (seed 1, default configs) on the windows both have."""
    import glob
    cf = {}
    for p in glob.glob(str(L.OUT / "runs" / "*.json")):
        r = json.loads(Path(p).read_text())
        s = r.get("spec", {})
        if r.get("status") == "ok" and len(s["router"]) == 1 and not s["env"] and s["seed"] == 1:
            cf.setdefault(s["router"]["name"], {})[s["start"]] = r["cf_pct"]
    d = np.array([cf[ENS][w] - cf[B1C][w] for w in cf.get(ENS, {}) if w in cf.get(B1C, {})])
    se = d.std(ddof=1) / np.sqrt(len(d))
    return {"delta": float(d.mean()), "se": float(se), "z": float(d.mean() / se), "gap": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(L.OUT / "sensitivity_view.json"))
    a = ap.parse_args()
    rows = compute_rows()
    idx = {(r["router"], r["router_ovr"], r["env_ovr"], r["seed"]): r for r in rows}

    def get(router, rov, env):
        if router == "ENS_vs_B1c":
            return ens_vs_b1c()
        k = (router, json.dumps(rov, sort_keys=True), json.dumps(env, sort_keys=True), 1)
        r = idx.get(k)
        if r is None:
            return None
        clean = {k2: (None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v))
                 for k2, v in r.items() if k2 in ("delta", "se", "z", "gap")}
        return clean

    groups = []
    for gfr, gen, items in GROUPS:
        out = []
        for fr, en, router, rov, env in items:
            v = get(router, rov, env)
            if v is not None:
                out.append({"fr": fr, "en": en, **v})
        groups.append({"fr": gfr, "en": gen, "rows": out})
    base = {r["router"]: r["cf"] for r in rows
            if r["router_ovr"] == "{}" and r["env_ovr"] == "{}" and r["seed"] in (0, 1)}
    view = {
        "title": "S5 — sensibilités (2015, 6 fenêtres de 30 j)",
        "note_fr": "Chaque barre change UN réglage du routeur B1c (ou de l'environnement simulé) ; "
                   "effet = différence appariée de CF sur les mêmes fenêtres et la même prévision.",
        "note_en": "Each bar changes ONE knob of the B1c router (or of the simulated environment); "
                   "effect = paired CF difference on the same windows and forecast.",
        "refs": [{"name": n, "cf": base[n]} for n in ("Oracle_REF_H", B1C, ENS, "B0") if n in base],
        "groups": groups}
    Path(a.out).write_text(json.dumps(view, ensure_ascii=False, indent=1))
    print(f"{sum(len(g['rows']) for g in groups)} rows -> {a.out}")


if __name__ == "__main__":
    main()
