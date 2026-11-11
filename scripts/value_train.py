"""V_theta: leave-one-month-out CV (2015) of the policy-consistent value vs baselines.

Models (target = energy over H_T = 5 d, all evaluated against the REALISED energy of causal runs):
  pol        LightGBM on realised B1 / year-run energy-to-go (rollouts + on-track samples)
  pol_nofc   same without forecast features (ablation)
  hind       LightGBM on V_hind(x, tau; 5 d) at the SAME rows (matched sample size)
  hind_big   LightGBM on V_hind at the same rows + 150 random cells per release time
  clim       climatological terminal value  P_clim(x) * 120 h   (months other than the test month)
  clim_cal   clim with a linear recalibration (a + b * clim) fitted on the training pol targets
Writes ``outputs/value/Vtheta_cv.json``, ``Vtheta_cv.png`` and fold models under
``data/cache/value/models``.
"""

import json
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_s3_backtest as R  # noqa: E402

from horizon.value import FEATURE_NAMES, fit_value_model, leave_month_out_mask  # noqa: E402
from horizon.value.dataset import assemble, build_X  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ["A_B1c_REF_s1", "A_B1c_REF_s2", "A_ENS_REF_s1"]
FC_COLS = [i for i, n in enumerate(FEATURE_NAMES) if n.startswith("fc_")]
NOFC = [i for i in range(len(FEATURE_NAMES)) if i not in FC_COLS]


def metrics(y, p, k):
    ok = np.isfinite(y) & np.isfinite(p)
    y, p, k = y[ok], p[ok], k[ok]
    res = y - p
    r2 = 1 - (res ** 2).sum() / ((y - y.mean()) ** 2).sum()
    yd, pd_ = y.copy(), p.copy()
    for q in np.unique(k):  # within-release-time (spatial ranking) skill
        m = k == q
        yd[m] -= y[m].mean()
        pd_[m] -= p[m].mean()
    r2w = 1 - ((yd - pd_) ** 2).sum() / max((yd ** 2).sum(), 1e-9)
    return {"n": int(len(y)), "R2": float(r2), "MAE_kwh": float(np.abs(res).mean()),
            "bias_kwh": float((p - y).mean()), "R2_within_release": float(r2w),
            "mean_target_kwh": float(y.mean())}


def main():
    warnings.filterwarnings("ignore")
    ctx = R.Ctx()
    g, sdf = ctx.grid, ctx.coast.sdf
    ds = assemble(ROOT / "data/cache/value", g, [ROOT / "outputs/s4_runs" / r for r in RUNS],
                  extra_cells_per_k=150)
    models_dir = ROOT / "data/cache/value/models"
    models_dir.mkdir(parents=True, exist_ok=True)
    names = ["pol", "pol_nofc", "hind", "hind_big", "clim", "clim_cal"]
    pred = {n: np.full(len(ds), np.nan) for n in names}
    imp = np.zeros(len(FEATURE_NAMES))
    HT_H = 120.0
    for m in range(1, 13):
        clim = ctx.clim_hold_kw({m})
        X = build_X(ds, g, clim, sdf)
        valid = np.isfinite(X).all(1)
        test = valid & (ds.month == m) & (ds.src >= 0)
        tr_ok = valid & leave_month_out_mask(ds.tau, ds.epoch, m, 5.0)
        tr_pol = tr_ok & (ds.src >= 0) & np.isfinite(ds.E[:, 1])
        tr_hind = tr_ok & (ds.src >= 0) & np.isfinite(ds.V[:, 1])
        tr_big = tr_ok & np.isfinite(ds.V[:, 1])
        assert not (ds.month[tr_ok] == m).any()
        if test.sum() == 0:
            continue
        mp = fit_value_model(X[tr_pol], ds.E[tr_pol, 1], meta={"target": "pol", "holdout": m})
        mp.save(models_dir / f"vtheta_pol_m{m:02d}.joblib")
        pred["pol"][test] = mp.predict(X[test])
        gain = mp.booster.booster_.feature_importance("gain")
        imp += gain / gain.sum()
        mn = fit_value_model(X[tr_pol][:, NOFC], ds.E[tr_pol, 1])
        pred["pol_nofc"][test] = mn.predict(X[test][:, NOFC])
        mh = fit_value_model(X[tr_hind], ds.V[tr_hind, 1], meta={"target": "hind", "holdout": m})
        mh.save(models_dir / f"vtheta_hind_m{m:02d}.joblib")
        pred["hind"][test] = mh.predict(X[test])
        mb = fit_value_model(X[tr_big], ds.V[tr_big, 1], meta={"target": "hind_big", "holdout": m})
        pred["hind_big"][test] = mb.predict(X[test])
        ci = FEATURE_NAMES.index("clim_kw")
        pred["clim"][test] = X[test, ci] * HT_H
        b, a = np.polyfit(X[tr_pol, ci], ds.E[tr_pol, 1], 1)
        pred["clim_cal"][test] = a + b * X[test, ci]
        print(f"month {m}: train {tr_pol.sum()} / {tr_big.sum()} test {test.sum()}", flush=True)
    y = ds.E[:, 1]
    sets = {"all": ds.src >= 0, "rollout": ds.src == 0, "track": ds.src > 0}
    out = {"n_rows": int(len(ds)), "features": list(FEATURE_NAMES), "metrics": {},
           "importance_gain_pol": dict(zip(FEATURE_NAMES, (imp / 12).round(4).tolist(),
                                           strict=True)), "by_month": {}}
    for sn, sm in sets.items():
        out["metrics"][sn] = {n: metrics(y[sm], pred[n][sm], ds.k[sm]) for n in names}
    # hindsight model against its own target (information)
    sm = ds.src >= 0
    out["hind_vs_own_target"] = {n: metrics(ds.V[sm, 1], pred[n][sm], ds.k[sm])
                                 for n in ("hind", "hind_big")}
    for mo in range(1, 13):
        sm = (ds.src == 0) & (ds.month == mo)
        out["by_month"][mo] = {n: metrics(y[sm], pred[n][sm], ds.k[sm])["MAE_kwh"] for n in
                               ("pol", "hind_big", "clim", "clim_cal")} if sm.any() else None
    # final models on all data
    clim_all = ctx.clim_hold_kw(set())
    X = build_X(ds, g, clim_all, sdf)
    v = np.isfinite(X).all(1)
    t = v & (ds.src >= 0) & np.isfinite(ds.E[:, 1])
    fit_value_model(X[t], ds.E[t, 1], meta={"target": "pol", "holdout": None}).save(
        models_dir / "vtheta_pol_all.joblib")
    Path(ROOT / "outputs/value/Vtheta_cv.json").write_text(json.dumps(out, indent=1))
    fig, axs = plt.subplots(1, 4, figsize=(17, 4.4), sharex=True, sharey=True)
    sm = ds.src == 0
    for ax, n in zip(axs, ("clim_cal", "hind_big", "pol", "pol_nofc"), strict=True):
        ax.scatter(pred[n][sm] / 1e3, y[sm] / 1e3, s=2, alpha=0.3)
        ax.plot([0, 300], [0, 300], "k-", lw=0.6)
        r = out["metrics"]["rollout"][n]
        ax.set_title(f"{n}: R2 {r['R2']:.2f}, MAE {r['MAE_kwh'] / 1e3:.1f} MWh", fontsize=9)
        ax.set_xlabel("LOMO prediction [MWh]")
    axs[0].set_ylabel("realised 5 d energy (B1 rollouts) [MWh]")
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/value/Vtheta_cv.png", dpi=110)
    for sn in sets:
        print(sn)
        for n in names:
            r = out["metrics"][sn][n]
            print(f"  {n:9s} n={r['n']:5d} R2 {r['R2']:.3f} MAE {r['MAE_kwh'] / 1e3:6.1f} MWh "
                  f"bias {r['bias_kwh'] / 1e3:+6.1f} R2w {r['R2_within_release']:.3f}")
    print(out["importance_gain_pol"])


if __name__ == "__main__":
    main()
