"""S6: real archived forecasts vs the S5 forecast emulator, seen exactly as the router sees them.

Both are scored on the planning grid (LAEA 40 km, ERA5_BOX, sea cells) against ERA5 interpolated
the same way (bilinear in u, v):

* ``rmse_vec``      control / deterministic vector-wind RMSE [m/s]
* ``bias_spd``      mean wind-speed error [m/s]
* MSE decomposition of the wind-speed field per (init, lead):
  ``mse_spd = bias^2 + (sd_f - sd_o)^2 + 2 sd_f sd_o (1 - r)``
  -> ``f_bias``, ``f_amp`` (intensity-type) and ``f_phase`` (pattern / displacement-type) shares.
* ensembles: ``em_rmse_vec`` (ensemble mean), ``spread`` (sqrt mean variance u+v).

Usage
  python3 scripts/s6/fc_vs_emulator.py emulator --out outputs/s6/emu.json
  python3 scripts/s6/fc_vs_emulator.py real --files <dir>/*.nc --era5 <dir> --product NAME \
          --out outputs/s6/real_NAME.json [--every 1] [--hours 0]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from horizon.geo.coast import build_basin_coast
from horizon.geo.grid import Grid
from horizon.weather.era5 import ERA5_BOX, ERA5Archive, regrid_indices, regrid_uv

D, H = 86400.0, 3600.0
LEADS_H = list(range(0, 241, 6))
GRID = Grid.from_bbox(*ERA5_BOX, 40e3)
DATA = Path("/home/claude/circeo-horizon-data/era5-data")


def sea_mask(outside=None):
    sea = build_basin_coast(40e3, bbox=ERA5_BOX).sdf > 0
    return sea if outside is None else sea & ~outside


def metrics(f: np.ndarray, o: np.ndarray, sea: np.ndarray) -> dict:
    """f, o: (ny, nx, 2) forecast / truth on the grid."""
    e = f[sea] - o[sea]
    sf, so = np.hypot(*f[sea].T), np.hypot(*o[sea].T)
    d = sf - so
    b = d.mean()
    sdf, sdo = sf.std(), so.std()
    r = np.corrcoef(sf, so)[0, 1]
    return {"se_vec": float((e ** 2).sum(1).mean()), "bias_spd": float(b),
            "mse_spd": float((d ** 2).mean()), "t_bias": float(b * b),
            "t_amp": float((sdf - sdo) ** 2), "t_phase": float(2 * sdf * sdo * (1 - r))}


class Acc:
    def __init__(self):
        self.s = defaultdict(lambda: defaultdict(list))

    def add(self, key, lead, m: dict):
        for k, v in m.items():
            self.s[key][(lead, k)].append(v)

    def table(self) -> dict:
        out = {}
        for key, d in self.s.items():
            leads = sorted({ld for ld, _ in d})
            row = {}
            for ld in leads:
                g = {k: np.mean(v) for (l2, k), v in d.items() if l2 == ld}
                n = len(d[(ld, "se_vec")])
                r = {"n": n, "rmse_vec": float(np.sqrt(g["se_vec"])), "bias_spd": g["bias_spd"],
                     "rmse_spd": float(np.sqrt(g["mse_spd"]))}
                tot = g["t_bias"] + g["t_amp"] + g["t_phase"]
                r.update(f_bias=g["t_bias"] / tot, f_amp=g["t_amp"] / tot, f_phase=g["t_phase"] / tot)
                if "em_se_vec" in g:
                    r.update(em_rmse_vec=float(np.sqrt(g["em_se_vec"])),
                             spread=float(np.sqrt(g["var"])))
                row[int(ld)] = r
            out[key] = row
        return out


def emulator(a):
    from horizon.weather.forecast_model import ERA5ForecastWeather, ForecastErrorParams
    arch = ERA5Archive(DATA, GRID)
    arch.build_cache()
    sea = sea_mask(arch.outside)
    ep = np.datetime64("2015-01-01T00:00:00")
    acc = Acc()
    for scale in a.scales:
        P = ForecastErrorParams.with_knobs(error_scale=scale)
        wx = ERA5ForecastWeather(arch, GRID, ep, 360 * D, params=P, seed=a.seed)
        for iss in np.arange(2, 349, a.step_days) * D:
            ens = wx.forecast_cycle(iss, 10 * D, a.members, dt_s=6 * H)
            tr = wx._truth_at(ens.times_s)
            month = int(str(ep + np.timedelta64(int(iss), "s"))[5:7])
            for k, ld in enumerate(LEADS_H):
                m = metrics(ens.uv[0, k], tr[k], sea)
                if a.members > 1:
                    em = ens.uv[:, k].mean(0)
                    m["em_se_vec"] = float(((em[sea] - tr[k][sea]) ** 2).sum(1).mean())
                    m["var"] = float(ens.uv[1:, k][:, sea].var(0, ddof=1).sum(-1).mean())
                for key in (f"emu_x{scale:g}", f"emu_x{scale:g}_m{month:02d}"):
                    acc.add(key, ld, m)
            print(f"scale {scale} issue d{iss / D:.0f} lead5d rmse "
                  f"{np.sqrt(acc.s[f'emu_x{scale:g}'][(120, 'se_vec')][-1]):.2f}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(acc.table(), indent=1))


class Era5Truth:
    def __init__(self, d: Path):
        import xarray as xr
        self.xr, self.d, self.cache, self.st = xr, Path(d), {}, None

    def at(self, t: np.datetime64):
        ym = str(t)[:7].replace("-", "")
        if ym not in self.cache:
            f = next(self.d.rglob(f"era5_uv10_0p25_{ym}.nc"), None)
            if f is None:
                self.cache[ym] = None
            else:
                ds = self.xr.open_dataset(f).load()
                if self.st is None:
                    self.st = regrid_indices(GRID, ds.lon.values, ds.lat.values)
                self.cache[ym] = (ds.time.values, regrid_uv(ds.u10.values, ds.v10.values, self.st))
            if len(self.cache) > 2:
                self.cache.pop(next(iter(self.cache)))
        c = self.cache[ym]
        if c is None:
            return None
        k = np.searchsorted(c[0], t)
        return c[1][k] if k < c[0].size and c[0][k] == t else None


def real(a):
    import xarray as xr
    truth = Era5Truth(Path(a.era5))
    sea = sea_mask()
    acc = Acc()
    files = sorted(Path(f) for f in a.files)
    st = None
    for f in files:
        ds = xr.open_dataset(f)
        if st is None:
            st = regrid_indices(GRID, ds.lon.values, ds.lat.values)
            sea = sea & ~st[4]
        inits = [t for t in ds.init.values if int(str(t)[11:13]) in a.hours]
        for t0 in inits[:: a.every]:
            fi = ds.sel(init=t0)
            month = int(str(t0)[5:7])
            for ld in LEADS_H:
                if ld not in fi.lead.values:
                    continue
                tr = truth.at(t0 + np.timedelta64(ld, "h"))
                if tr is None:
                    continue
                fl = fi.sel(lead=ld)
                U, V = fl.u10.values, fl.v10.values
                if U.ndim == 3:
                    good = np.isfinite(U).all(axis=(1, 2))
                    c = regrid_uv(U[:1], V[:1], st)[0]
                    ok = sea & np.isfinite(c).all(-1)
                    if ok.sum() < 0.95 * sea.sum():
                        continue
                    m = metrics(c, tr, ok)
                    if good.sum() > 2:
                        Ug, Vg = U[good], V[good]
                        em = regrid_uv(Ug.mean(0)[None], Vg.mean(0)[None], st)[0]
                        var = Ug.var(0, ddof=1) + Vg.var(0, ddof=1)
                        vg = regrid_uv(var[None], np.zeros_like(var)[None], st)[0][..., 0]
                        m["em_se_vec"] = float(((em[ok] - tr[ok]) ** 2).sum(1).mean())
                        m["var"] = float(vg[ok].mean())
                else:
                    c = regrid_uv(U[None], V[None], st)[0]
                    ok = sea & np.isfinite(c).all(-1)
                    if ok.sum() < 0.95 * sea.sum():
                        continue
                    m = metrics(c, tr, ok)
                for key in (a.product, f"{a.product}_m{month:02d}"):
                    acc.add(key, ld, m)
            l0 = acc.s[a.product].get((ld, "se_vec")) if a.product in acc.s else None
            print(f"{a.product} {str(t0)[:13]} last-lead rmse {np.sqrt(l0[-1]) if l0 else float('nan'):.2f}",
                  flush=True)
    out = Path(a.out)
    old = json.loads(out.read_text()) if out.exists() and a.append else {}
    # raw sums are not kept: append mode merges by re-weighting the per-lead means with n
    new = acc.table()
    for key, rows in new.items():
        if key in old:
            for ld, r in rows.items():
                o = old[key].get(str(ld))
                if o:
                    n0, n1 = o["n"], r["n"]
                    for k in r:
                        if k == "n":
                            continue
                        if k in ("rmse_vec", "rmse_spd", "em_rmse_vec", "spread"):
                            r[k] = float(np.sqrt((o[k] ** 2 * n0 + r[k] ** 2 * n1) / (n0 + n1)))
                        else:
                            r[k] = (o.get(k, r[k]) * n0 + r[k] * n1) / (n0 + n1)
                    r["n"] = n0 + n1
            old[key] = {**old[key], **{str(k): v for k, v in rows.items()}}
        else:
            old[key] = rows
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(old, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emulator")
    e.add_argument("--scales", type=float, nargs="+", default=[1.0])
    e.add_argument("--members", type=int, default=11)
    e.add_argument("--step-days", type=float, default=7.0)
    e.add_argument("--seed", type=int, default=3)
    e.add_argument("--out", default="outputs/s6/emu.json")
    r = sub.add_parser("real")
    r.add_argument("--files", nargs="+", required=True)
    r.add_argument("--era5", required=True)
    r.add_argument("--product", required=True)
    r.add_argument("--every", type=int, default=1)
    r.add_argument("--hours", type=int, nargs="+", default=[0])
    r.add_argument("--append", action="store_true")
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    emulator(a) if a.cmd == "emulator" else real(a)


if __name__ == "__main__":
    main()
