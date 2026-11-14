"""Real archived forecasts (ECMWF HRES / AIFS / ENS, GEFS) as a forecast provider for the router.

Same interface as :class:`~horizon.weather.forecast_model.ERA5ForecastWeather` (truth from the
same ERA5 archive, ``forecast`` with the latency logic, ``forecast_cycle``), but the forecasts are
the real ones, pre-interpolated to the planning grid by ``scripts/s6/build_real_fc.py``
(bilinear in u, v from the lat-lon archive files, cropped to ERA5_BOX like the ERA5 truth).

Availability: a run initialised at ``a`` is usable from ``a + latency_h`` (real dissemination
delay of the product, e.g. ECMWF HRES 00 UTC complete at about 07-08 UTC). At time ``now`` the
latest usable run is taken; missing runs (archive gaps) fall back to the previous one, with a
longer lead, as in operations. Valid times between archived steps are interpolated linearly in
time; beyond the last archived step the last field is held (counted in ``n_held``).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .forecast_model import Ensemble, ERA5ForecastWeather

LATENCY_H = {"hres": 8.0, "aifs": 7.0, "ens": 9.0, "gefs": 6.0, "gefs_ctl": 6.0}


class RealForecastWeather(ERA5ForecastWeather):
    """Router forecast provider backed by real archived forecasts on the planning grid.

    Parameters
    ----------
    archive : ERA5Archive  truth (same year as the forecasts).
    epoch, duration_s : mission start and length.
    fc_dir : directory of ``<product>_<YYYYMM>_<gridsig>.npz`` files (build_real_fc.py).
    product : 'hres' | 'aifs' | 'ens' | 'gefs' | 'gefs_ctl'.
    latency_h : availability delay after the initialisation time [h]; default LATENCY_H.
    """

    def __init__(self, archive, epoch, duration_s: float, fc_dir, product: str,
                 latency_h: float | None = None, seed: int = 0, calib_days: float = 0.0):
        super().__init__(archive, archive.grid, epoch, duration_s, seed=seed)
        self.product = product
        self.latency_s = 3600.0 * (LATENCY_H[product] if latency_h is None else latency_h)
        self.fc_dir = Path(fc_dir)
        self._files = {}
        for f in sorted(self.fc_dir.glob(f"{product}_??????_*.npz")):
            self._files[f.stem.split("_")[-2]] = f
        if not self._files:
            raise FileNotFoundError(f"no {product} forecast files in {fc_dir}")
        self._month_cache: dict = {}
        inits = []
        for ym, f in self._files.items():
            with np.load(f) as z:
                inits.append(z["inits"].astype("datetime64[s]"))
        self.inits = np.unique(np.concatenate(inits))
        self._inits_s = (self.inits - self.epoch) / np.timedelta64(1, "s")
        self.n_held = 0
        self.n_fallback = 0  # requests answered by an older run than the nominal latest
        self.calib = None
        if calib_days > 0:
            self.calib = self._fit_calibration(calib_days)

    # ------------------------------------------------------------------ calibration (E-S6-2)
    def _fit_calibration(self, days: float) -> dict:
        """Per-lead speed factor and spread factor, fitted on runs whose whole forecast lies
        strictly before the mission start (no look-ahead): runs initialised in
        [epoch - days - max_lead, epoch - max_lead], sea cells, verified against ERA5.

        * speed factor a(lead) = mean |truth| / mean |member| (speed bias of the members);
        * spread factor k(lead) = RMSE(ensemble mean) / sqrt(mean ensemble variance), so that
          the calibrated spread matches the error of the mean (spread-skill = 1).
        """
        from ..geo.coast import build_basin_coast  # noqa: F401  (sea cells: archive outside)
        sea = ~self.archive.outside
        lead_max_s = None
        acc = {}
        for init in self.inits:
            leads_h, uv = self._load(init)
            if lead_max_s is None:
                lead_max_s = 3600.0 * float(leads_h[-1])
            a_s = (init - self.epoch) / np.timedelta64(1, "s")
            if not (-(days * 86400.0 + lead_max_s) <= a_s <= -lead_max_s):
                continue
            t = a_s + 3600.0 * leads_h
            try:
                tr = self.archive.fields_at(t, self.epoch)
            except Exception:  # noqa: BLE001  (truth outside the archive year)
                continue
            f = uv.astype(np.float32)  # (L, M, ny, nx, 2)
            em = f.mean(1)
            # member speeds (the ensemble-mean field is smoother, its speed is biased low)
            sp_f = np.hypot(f[..., 0], f[..., 1]).mean(1)[:, sea].mean(1)
            sp_o = np.hypot(tr[..., 0], tr[..., 1])[:, sea].mean(1)
            se = ((em - tr) ** 2).sum(-1)[:, sea].mean(1)
            var = f.var(1, ddof=1).sum(-1)[:, sea].mean(1) if f.shape[1] > 1 else np.zeros_like(se)
            for k, ld in enumerate(leads_h):
                d = acc.setdefault(float(ld), [0.0, 0.0, 0.0, 0.0, 0])
                d[0] += sp_f[k]; d[1] += sp_o[k]; d[2] += se[k]; d[3] += var[k]; d[4] += 1
        if not acc:
            raise ValueError("calibration: no training run before the mission start")
        L = np.array(sorted(acc))
        a = np.array([acc[l][1] / acc[l][0] for l in L])
        k = np.array([np.sqrt(acc[l][2] / acc[l][3]) if acc[l][3] > 0 else 1.0 for l in L])
        n = int(min(acc[l][4] for l in L))
        return {"leads_h": L, "speed": a.astype(np.float32), "spread": k.astype(np.float32),
                "n_runs": n}

    # ------------------------------------------------------------------ data
    def _load(self, init: np.datetime64):
        ym = str(init)[:7].replace("-", "")
        if ym not in self._month_cache:
            with np.load(self._files[ym]) as z:
                self._month_cache[ym] = {"inits": z["inits"].astype("datetime64[s]"),
                                         "leads_h": z["leads_h"].astype(float),
                                         "uv": z["uv"]}
            while len(self._month_cache) > 2:
                self._month_cache.pop(next(iter(self._month_cache)))
        c = self._month_cache[ym]
        k = int(np.nonzero(c["inits"] == init)[0][0])
        return c["leads_h"], c["uv"][k]  # (L, M, ny, nx, 2) float16

    # ------------------------------------------------------------------ cycles
    def analysis_time(self, now_s: float, product: str = "ens") -> float:
        """Initialisation time [s since epoch] of the latest run usable at ``now_s``."""
        ok = self._inits_s <= now_s - self.latency_s + 1e-6
        if not ok.any():
            raise ValueError(f"{self.product}: no run usable at t={now_s / 3600:.0f} h "
                             f"(archive starts {self.inits[0]})")
        a = float(self._inits_s[ok][-1])
        cyc = 12 * 3600.0 if self.product in ("hres", "aifs") else 24 * 3600.0
        if now_s - self.latency_s - a >= cyc:
            self.n_fallback += 1
        return a

    def forecast_cycle(self, analysis_s: float, horizon_s: float, n_members: int,
                       dt_s: float = 10800.0, seed_offset: int = 0) -> Ensemble:
        init = self.epoch + np.timedelta64(int(round(analysis_s)), "s")
        leads_h, uv = self._load(init)
        nt = int(round(horizon_s / dt_s)) + 1
        t = analysis_s + np.arange(nt) * dt_s
        lead = (t - analysis_s) / 3600.0
        m_avail = uv.shape[1]
        n = min(n_members, m_avail)
        if lead[-1] > leads_h[-1]:
            self.n_held += 1
        lc = np.clip(lead, leads_h[0], leads_h[-1])
        j1 = np.clip(np.searchsorted(leads_h, lc, side="left"), 1, leads_h.size - 1)
        j0 = j1 - 1
        w = ((lc - leads_h[j0]) / (leads_h[j1] - leads_h[j0])).astype(np.float32)
        a = uv[j0, :n].astype(np.float32)
        b = uv[j1, :n].astype(np.float32)
        out = a + (b - a) * w[:, None, None, None, None]  # (T, M, ny, nx, 2)
        if self.calib is not None:
            c = self.calib
            fa = np.interp(lead, c["leads_h"], c["speed"]).astype(np.float32)
            fk = np.interp(lead, c["leads_h"], c["spread"]).astype(np.float32)
            mean = out.mean(1, keepdims=True)
            out = (mean + (out - mean) * fk[:, None, None, None, None]) * fa[:, None, None, None, None]
        out = np.ascontiguousarray(np.moveaxis(out, 1, 0))
        return Ensemble(self.grid, self.epoch, float(analysis_s), t, out,
                        np.full(n, 1.0 / n))

    def forecast(self, issue_s: float, horizon_s: float, n_members: int,
                 dt_s: float = 10800.0, seed_offset: int = 0, product: str = "ens") -> Ensemble:
        if not 0 <= issue_s <= self.duration_s:
            raise ValueError("issue_s outside [0, duration_s]")
        a = self.analysis_time(issue_s, product)
        n = 1 if product == "control" else n_members
        h_tot = np.ceil((horizon_s + (issue_s - a)) / dt_s - 1e-9) * dt_s
        return self.forecast_cycle(a, float(h_tot), n, dt_s, seed_offset)
