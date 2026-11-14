"""Pre-interpolate real archived forecasts (circeo-meteo-forecasts Releases) to the planning grid.

Per product and month: download the archive file(s), crop to ERA5_BOX (as the ERA5 truth),
bilinear (u, v) to the 40 km LAEA grid, keep leads <= --max-lead-h and members < --members,
store float16 ``data/cache/realfc/<product>_<YYYYMM>_<gridsig>.npz`` (inits, leads_h, uv
(I, L, M, ny, nx, 2)), then delete the raw download.

    python3 scripts/s6/build_real_fc.py hres 202302 202303 ...
"""
from __future__ import annotations

import argparse
import glob
import shutil
import subprocess
from pathlib import Path

import numpy as np

from horizon.geo.grid import Grid
from horizon.weather.era5 import ERA5_BOX, grid_signature, regrid_indices, regrid_uv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "cache" / "realfc"
FETCH = "/home/claude/circeo-meteo/client/fetch_meteo.py"
REPO = "boris-circeo/circeo-meteo-forecasts"
PRODUCTS = {  # release (year templated), file prefix, default members kept, default max lead
    "hres": ("ecmwf-oper-uv10-0p25-v2", "ecmwf_oper_uv10_0p25", 1, 240),
    "aifs": ("ecmwf-aifs-uv10-0p25-v2", "ecmwf_aifs_uv10_0p25", 1, 240),
    "ens": ("ecmwf-enfo-uv10-0p5-{year}", "ecmwf_enfo_uv10_0p5", 21, 144),
    "gefs": ("gefs-oper-uv10-0p5-{year}", "gefs_oper_uv10_0p5", 21, 144),
    "gefs_ctl": ("gefs-ctl-uv10-0p25-v2", "gefs_ctl_uv10_0p25", 1, 240),
}


def build(product: str, ym: str, grid: Grid, members: int, max_lead: int, tmp: Path) -> Path | None:
    import xarray as xr
    rel, pfx, _, _ = PRODUCTS[product]
    rel = rel.replace("{year}", ym[:4])
    out = OUT / f"{product}_{ym}_{grid_signature(grid)}.npz"
    if out.exists():
        return out
    d = tmp / f"{product}_{ym}"
    subprocess.run(["python3", FETCH, "--repo", REPO, "--release", rel,
                    "--pattern", f"{pfx}_{ym}*.nc", "--dest", str(d)], check=False,
                   capture_output=True)
    files = sorted(glob.glob(str(d / "*" / f"{pfx}_{ym}*.nc")))
    if not files:
        print(f"{product} {ym}: no archive file")
        return None
    lo, hi, la, lb = ERA5_BOX
    inits, uvs, leads_ref, st = [], [], None, None
    for f in files:
        ds = xr.open_dataset(f).sel(lat=slice(la, lb), lon=slice(lo, hi))
        ds = ds.sel(lead=[ld for ld in ds.lead.values if ld <= max_lead])
        if "member" in ds.dims:
            ds = ds.isel(member=slice(0, members))
        if st is None:
            st = regrid_indices(grid, ds.lon.values, ds.lat.values)
        leads = ds.lead.values.astype(int)
        leads_ref = leads if leads_ref is None else leads_ref
        if not np.array_equal(leads, leads_ref):
            raise ValueError(f"{f}: lead set differs within the month")
        for it in ds.init.values:
            x = ds.sel(init=it)
            u, v = x.u10.values, x.v10.values  # (L[, M], lat, lon)
            if u.ndim == 3:
                u, v = u[:, None], v[:, None]
            L, M = u.shape[:2]
            if np.isnan(u).all(axis=(2, 3)).any():
                print(f"  {str(it)[:13]}: missing fields, run skipped")
                continue
            r = regrid_uv(u.reshape(L * M, *u.shape[2:]), v.reshape(L * M, *v.shape[2:]), st)
            uvs.append(r.reshape(L, M, *r.shape[1:]).astype(np.float16))
            inits.append(np.datetime64(it, "s"))
    OUT.mkdir(parents=True, exist_ok=True)
    tmpf = out.with_name(out.name + ".tmp.npz")
    np.savez_compressed(tmpf, inits=np.array(inits), leads_h=leads_ref,
                        uv=np.stack(uvs))
    tmpf.replace(out)
    shutil.rmtree(d, ignore_errors=True)
    print(f"{product} {ym}: {len(inits)} runs, leads {leads_ref[0]}-{leads_ref[-1]} h, "
          f"{uvs[0].shape[1]} member(s), {out.stat().st_size / 2**20:.0f} MiB", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("product", choices=PRODUCTS)
    ap.add_argument("months", nargs="+")
    ap.add_argument("--members", type=int)
    ap.add_argument("--max-lead-h", type=int)
    ap.add_argument("--tmp", default="/tmp/s6/raw")
    a = ap.parse_args()
    _, _, m0, l0 = PRODUCTS[a.product]
    grid = Grid.from_bbox(*ERA5_BOX, 40e3)
    for ym in a.months:
        build(a.product, ym, grid, a.members or m0, a.max_lead_h or l0, Path(a.tmp))


if __name__ == "__main__":
    main()
