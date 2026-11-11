"""E0: hindsight bias V_hind - V_pol (DES-860 §8.3/§10). Needs ``value_collect.py`` output.

Writes ``outputs/value/E0_results.json`` and ``outputs/value/E0_bias_map.png``.
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
from scipy import stats  # noqa: E402
from scipy.ndimage import gaussian_filter  # noqa: E402

from horizon.value.dataset import assemble  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ["A_B1c_REF_s1", "A_B1c_REF_s2", "A_ENS_REF_s1"]
HN = {0: 2, 1: 5, 2: 10}


def summ(b, vh, k):
    """mean / SE (clustered by release time) / relative bias / n."""
    ok = np.isfinite(b)
    b, vh, k = b[ok], vh[ok], k[ok]
    if len(b) < 3:
        return None
    ks = np.unique(k)
    cm = np.array([b[k == q].mean() for q in ks])
    se = float(cm.std(ddof=1) / np.sqrt(len(ks))) if len(ks) > 1 else float("nan")
    return {"n": int(len(b)), "mean_kwh": float(b.mean()), "se_kwh": se,
            "rel_pct": float(100 * b.mean() / vh.mean()), "std_kwh": float(b.std()),
            "p10": float(np.percentile(b, 10)), "p90": float(np.percentile(b, 90))}


def main():
    warnings.filterwarnings("ignore")
    ctx = R.Ctx()
    g, sdf = ctx.grid, ctx.coast.sdf
    ds = assemble(ROOT / "data/cache/value", g, [ROOT / "outputs/s4_runs" / r for r in RUNS])
    from horizon.value.dataset import sample_map
    sdf_km = sample_map(g, np.where(ctx.outside, np.nan, sdf), ds.x, ds.y) / 1e3
    lon, lat = g.to_lonlat(ds.x, ds.y)
    res = {"n_release": int(len(ds.s_k)), "n_rows": int(len(ds))}
    # --- by horizon / source
    res["by_H_source"] = {}
    for h in (0, 1, 2):
        for name, m in (("rollout", ds.src == 0), ("track", ds.src > 0), ("all", ds.src >= 0)):
            m = m & (ds.src >= 0)
            b = ds.V[:, h] - ds.E[:, h]
            r = summ(b[m], ds.V[m, h], ds.k[m])
            if r:
                mk = m & np.isfinite(b)
                r["V_pol_mean"] = float(ds.E[mk, h].mean())
                r["V_hind_mean"] = float(ds.V[mk, h].mean())
                res["by_H_source"][f"H{HN[h]}d_{name}"] = r
    # --- by month, by distance to coast, by region (H = 5 d, rollouts and tracks)
    b5 = ds.V[:, 1] - ds.E[:, 1]
    for nm, m0 in (("rollout", ds.src == 0), ("track", ds.src > 0)):
        res[f"by_month_{nm}"] = {int(mo): summ(b5[m0 & (ds.month == mo)],
                                               ds.V[m0 & (ds.month == mo), 1],
                                               ds.k[m0 & (ds.month == mo)]) for mo in range(1, 13)}
        edges = [20, 60, 150, 300, 600, 1e9]
        res[f"by_coast_{nm}"] = {}
        for a, c in zip(edges[:-1], edges[1:], strict=True):
            m = m0 & (sdf_km >= a) & (sdf_km < c)
            res[f"by_coast_{nm}"][f"{a:.0f}-{c:.0f}km"] = summ(b5[m], ds.V[m, 1], ds.k[m])
        res[f"by_region_{nm}"] = {}
        for rn, m in (("lat<45", lat < 45), ("45-52", (lat >= 45) & (lat < 52)),
                      ("52-58", (lat >= 52) & (lat < 58)), ("lat>=58", lat >= 58)):
            res[f"by_region_{nm}"][rn] = summ(b5[m0 & m], ds.V[m0 & m, 1], ds.k[m0 & m])
    # --- spatial structure: ANOVA over lon/lat blocks (rollouts, H = 5 d)
    m0 = (ds.src == 0) & np.isfinite(b5)
    bl = (np.floor((lon[m0] + 45) / 10).astype(int) * 10 + np.floor((lat[m0] - 35) / 6).astype(int))
    groups = [b5[m0][bl == q] for q in np.unique(bl) if (bl == q).sum() >= 15]
    F, p = stats.f_oneway(*groups)
    grand = b5[m0].mean()
    ss_b = sum(len(q) * (q.mean() - grand) ** 2 for q in groups)
    ss_t = sum(((q - grand) ** 2).sum() for q in groups)
    rel = b5[m0] / ds.V[m0, 1]
    relg = [rel[bl == q] for q in np.unique(bl) if (bl == q).sum() >= 15]
    res["spatial_anova_H5_rollout"] = {
        "n_blocks": len(groups), "F": float(F), "p": float(p), "eta2": float(ss_b / ss_t),
        "block_mean_range_kwh": [float(min(q.mean() for q in groups)),
                                 float(max(q.mean() for q in groups))],
        "block_rel_range_pct": [float(100 * min(q.mean() for q in relg)),
                                float(100 * max(q.mean() for q in relg))]}
    # correlation of bias with the hindsight value itself
    res["corr_bias_Vhind_H5_rollout"] = float(np.corrcoef(b5[m0], ds.V[m0, 1])[0, 1])
    res["corr_bias_Vpol_H5_rollout"] = float(np.corrcoef(b5[m0], ds.E[m0, 1])[0, 1])
    Path(ROOT / "outputs/value/E0_results.json").write_text(json.dumps(res, indent=1))
    # --- maps (rollouts, H = 5 d): kernel-smoothed over cells
    nav = (ctx.coast.sdf >= 20e3) & ~ctx.outside
    ji = np.stack(g.index_of(ds.x, ds.y), 1)
    fields = {}
    for nm, val in (("bias (kWh)", b5), ("relative bias (%)", 100 * b5 / ds.V[:, 1]),
                    ("V_hind (MWh)", ds.V[:, 1] / 1e3), ("V_pol (MWh)", ds.E[:, 1] / 1e3)):
        num, den = np.zeros(g.shape), np.zeros(g.shape)
        mm = (ds.src == 0) & np.isfinite(val)
        np.add.at(num, (np.rint(ji[mm, 0]).astype(int), np.rint(ji[mm, 1]).astype(int)), val[mm])
        np.add.at(den, (np.rint(ji[mm, 0]).astype(int), np.rint(ji[mm, 1]).astype(int)), 1.0)
        sm = gaussian_filter(num, 2.5, mode="constant") / np.maximum(
            gaussian_filter(den, 2.5, mode="constant"), 1e-9)
        sm[(gaussian_filter(den, 2.5, mode="constant") < 0.15) | ~nav] = np.nan
        fields[nm] = sm
    lonm, latm = g.lonlat_mesh()
    fig, axs = plt.subplots(2, 2, figsize=(13, 9.5))
    for ax, (nm, f) in zip(axs.ravel(), fields.items(), strict=True):
        cmap = "RdBu_r" if "bias" in nm else "viridis"
        vmin, vmax = (np.nanpercentile(f, 2), np.nanpercentile(f, 98))
        pc = ax.pcolormesh(lonm, latm, f, cmap=cmap, vmin=vmin, vmax=vmax, shading="auto")
        ax.contour(lonm, latm, np.where(ctx.outside, -1, sdf), levels=[0], colors="k",
                   linewidths=0.6)
        ax.set_title(f"{nm}, H = 5 d, B1 rollouts 2015 (n={int((ds.src == 0).sum())})", fontsize=9)
        ax.set_xlabel("lon [deg]"), ax.set_ylabel("lat [deg]")
        fig.colorbar(pc, ax=ax, shrink=0.85)
    fig.suptitle("E0: hindsight V_hind minus policy-consistent V_pol (B1, 5 d forecasts)")
    fig.tight_layout()
    fig.savefig(ROOT / "outputs/value/E0_bias_map.png", dpi=110)
    keys = ("by_H_source", "spatial_anova_H5_rollout", "corr_bias_Vhind_H5_rollout")
    print(json.dumps({k: v for k, v in res.items() if k in keys}, indent=1))


if __name__ == "__main__":
    main()
