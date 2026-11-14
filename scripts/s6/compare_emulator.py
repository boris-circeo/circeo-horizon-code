"""S6: real forecasts vs the S5 emulator, router view, and what it implies for the capacity factor.

Inputs: outputs/s6/emu.json (``fc_vs_emulator.py emulator``) and the monthly score files of the
public Release scores-v1 (``meteo.scores``, variables ``r_*`` = router view). Re-run at will: it
uses whatever months are available, so the figures tighten as the archive grows.

    python3 scripts/s6/compare_emulator.py --scores /tmp/s6/scores --out docs/s6
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import xarray as xr

PRODUCTS = {"ecmwf_oper_uv10_0p25": "ECMWF HRES", "ecmwf_aifs_uv10_0p25": "ECMWF AIFS",
            "ecmwf_enfo_uv10_0p5": "ECMWF ENS (control)", "gefs_ctl_uv10_0p25": "GEFS control",
            "gefs_oper_uv10_0p5": "GEFS ENS (control)", "gefs_reforecast_uv10_0p5": "GEFSv12 reforecast (control)"}
# S5 sensitivity (B1c, 6 seeds, 30-day windows): CF vs error_scale
CF_CURVE = ((0.0, 85.0), (0.5, 83.7), (1.0, 79.8), (1.5, 76.0), (2.0, 72.2))
ROUTER_LEADS = list(range(6, 121, 6))  # what the router uses most: refiner 0-48 h, DP 3-5 d


def cf_of_scale(s: float) -> float:
    x, y = zip(*CF_CURVE)
    if s > x[-1]:  # linear extrapolation of the last segment
        return y[-1] + (s - x[-1]) * (y[-1] - y[-2]) / (x[-1] - x[-2])
    return float(np.interp(s, x, y))


def load(scores: Path):
    """{product: {init: Dataset row}} -> per product a Dataset (init, lead) of r_* variables."""
    by = defaultdict(list)
    for f in sorted(scores.rglob("scores_*.nc")):
        m = re.match(r"scores_(.+)_(\d{6})\.nc$", f.name)
        if not m or m.group(1) not in PRODUCTS:
            continue
        ds = xr.open_dataset(f)
        if "r_se_vec" not in ds:
            continue
        keep = [v for v in ds.data_vars if v.startswith("r_")]
        by[m.group(1)].append(ds[keep].load())
    out = {}
    for p, parts in by.items():
        ds = xr.concat(parts, "init", join="outer")
        ds = ds.sel(init=ds.indexes["init"].hour == 0)  # 00 UTC runs only (common to all)
        out[p] = ds.sortby("init")
    return out


def summarise(ds: xr.Dataset, emu: dict, leads) -> dict:
    """Per lead: real stats, month-matched emulator stats, equivalent error scale."""
    months = ds.indexes["init"].month
    w = np.bincount(months, minlength=13)[1:] / len(months)
    rows = {}
    for ld in leads:
        if ld not in ds.lead.values:
            continue
        x = ds.sel(lead=ld)
        ok = np.isfinite(x.r_se_vec.values)
        if ok.sum() < 5:
            continue
        r = {"n": int(ok.sum()), "rmse": float(np.sqrt(np.nanmean(x.r_se_vec))),
             "bias": float(np.nanmean(x.r_bias_spd))}
        tb, ta, tp = (float(np.nanmean(x[v])) for v in ("r_t_bias", "r_t_amp", "r_t_phase"))
        r["phase_share"] = tp / (tb + ta + tp)
        if "r_em_se_vec" in x:
            r["em_rmse"] = float(np.sqrt(np.nanmean(x.r_em_se_vec)))
            r["spread"] = float(np.sqrt(np.nanmean(x.r_var)))
        e2 = sum(wm * emu[f"emu_x1_m{m:02d}"][str(ld)]["rmse_vec"] ** 2
                 for m, wm in enumerate(w, 1) if wm > 0)
        r["emu_rmse"] = float(np.sqrt(e2))
        r["emu_bias"] = float(sum(wm * emu[f"emu_x1_m{m:02d}"][str(ld)]["bias_spd"]
                                  for m, wm in enumerate(w, 1) if wm > 0))
        r["emu_phase_share"] = float(sum(wm * emu[f"emu_x1_m{m:02d}"][str(ld)]["f_phase"]
                                         for m, wm in enumerate(w, 1) if wm > 0))
        r["scale"] = r["rmse"] / r["emu_rmse"]
        rows[int(ld)] = r
    rl = [rows[ld] for ld in ROUTER_LEADS if ld in rows]
    # MSE-weighted equivalent scale over the router leads (errors add in variance)
    s_eq = float(np.sqrt(sum(r["rmse"] ** 2 for r in rl) / sum(r["emu_rmse"] ** 2 for r in rl))) if rl else np.nan
    return {"rows": rows, "s_eq": s_eq, "cf": cf_of_scale(s_eq) if np.isfinite(s_eq) else np.nan,
            "n_inits": int(ds.sizes["init"]),
            "period": f"{str(ds.init.values[0])[:7]} .. {str(ds.init.values[-1])[:7]}",
            "months": sorted(set(int(m) for m in months))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True)
    ap.add_argument("--emu", default="outputs/s6/emu.json")
    ap.add_argument("--out", default="docs/s6")
    a = ap.parse_args()
    emu = json.loads(Path(a.emu).read_text())
    data = load(Path(a.scores))
    leads = list(range(0, 241, 6))
    res = {p: summarise(ds, emu, leads) for p, ds in data.items()}
    # common period: inits present in every wind product that has >= 20 inits
    big = [p for p, ds in data.items() if ds.sizes["init"] >= 20 and p != "gefs_reforecast_uv10_0p5"]
    common = None
    for p in big:
        s = set(data[p].init.values)
        common = s if common is None else common & s
    res_common = {}
    if common and len(common) >= 10:
        idx = sorted(common)
        res_common = {p: summarise(data[p].sel(init=idx), emu, leads) for p in big}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fc_vs_emulator.json").write_text(json.dumps({"all": res, "common": res_common}, indent=1))
    lines = ["# Real forecasts vs the S5 emulator (router view)", "",
             "Generated by `scripts/s6/compare_emulator.py`; numbers change as the archive grows.", "",
             f"CF mapping: S5 sensitivity of B1c to `error_scale` {CF_CURVE}; equivalent scale = "
             "RMSE ratio to the month-matched emulator, MSE-weighted over leads 6-120 h.", ""]
    for title, R in (("All available inits (00 UTC)", res), ("Common inits", res_common)):
        if not R:
            continue
        lines += [f"## {title}", "",
                  "| Product | Period | Inits | RMSE 24 h (emu) | RMSE 72 h (emu) | RMSE 120 h (emu) | "
                  "Speed bias 120 h (emu) | Phase share 120 h (emu) | Equiv. scale | CF (S5 curve) |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for p, r in R.items():
            g = lambda ld, k: r["rows"].get(ld, {}).get(k, np.nan)  # noqa: E731
            lines.append(
                f"| {PRODUCTS[p]} | {r['period']} | {r['n_inits']} | "
                f"{g(24, 'rmse'):.2f} ({g(24, 'emu_rmse'):.2f}) | {g(72, 'rmse'):.2f} ({g(72, 'emu_rmse'):.2f}) | "
                f"{g(120, 'rmse'):.2f} ({g(120, 'emu_rmse'):.2f}) | {g(120, 'bias'):+.2f} ({g(120, 'emu_bias'):+.2f}) | "
                f"{g(120, 'phase_share'):.2f} ({g(120, 'emu_phase_share'):.2f}) | {r['s_eq']:.2f} | {r['cf']:.1f} % |")
        lines.append("")
    (out / "fc_vs_emulator.md").write_text("\n".join(lines))
    print("\n".join(lines))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
        for p, r in res.items():
            L = sorted(r["rows"])
            ax[0].plot(np.array(L) / 24, [r["rows"][ld]["rmse"] for ld in L], label=PRODUCTS[p])
            ax[1].plot(np.array(L) / 24, [r["rows"][ld]["scale"] for ld in L], label=PRODUCTS[p])
        E = emu["emu_x1"]
        L = sorted(int(k) for k in E)
        ax[0].plot(np.array(L) / 24, [E[str(ld)]["rmse_vec"] for ld in L], "k--", lw=2, label="S5 emulator x1")
        ax[1].axhline(1, color="k", ls="--", lw=2)
        ax[0].set(xlabel="lead [d]", ylabel="vector-wind RMSE [m/s]", title="Router view (40 km, sea, 32W-5E 38-65N)")
        ax[1].set(xlabel="lead [d]", ylabel="RMSE / emulator (month-matched)", title="Equivalent error scale")
        ax[1].axvspan(0.25, 5, color="0.9", zorder=0)
        for x in ax:
            x.grid(alpha=0.3)
        ax[0].legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "fc_vs_emulator.png", dpi=130)
    except Exception as exc:  # noqa: BLE001
        print("figure skipped:", exc)


if __name__ == "__main__":
    main()
