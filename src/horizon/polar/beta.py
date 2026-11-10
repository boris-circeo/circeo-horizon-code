"""Loader for the client's real power polars ("BETA" VPP output, one CSV per TWS).

DATA ARE CLIENT-OWNED, PROPRIETARY AND CONFIDENTIAL: they live outside this repository and must
never be copied into it or committed.

File format (``polar_BETA_TWS=<kn>_<date>.csv``)
------------------------------------------------
Line 1 ``# Params: {json}`` (vessel configuration), line 2 a comment, line 3 the header
``U,Psi_rad,AWS,AWA,Power``; then one row per node: ``U`` ship speed through water [m/s]
(0.1..8.0, 30 values; 20 values for TWS >= 42 kn), ``Psi_rad`` [rad] in [0, pi],
``AWS`` apparent wind speed [m/s], ``AWA`` [deg], ``Power`` net power [kW] (turbine gross minus
propulsion consumption). Empty ``Power`` = infeasible combination.

Angle convention (verified from the data, see ``tests/test_polar_beta.py``)
---------------------------------------------------------------------------
``Psi = TWA`` of CONVENTIONS §3 directly (0 = head to wind, 180 deg = dead downwind). Evidence:
``AWS^2 = TWS^2 + U^2 + 2 TWS U cos(Psi)`` holds to 1e-3 (AWS = TWS + U at Psi = 0: a ship
moving into the wind sees a stronger apparent wind; AWS = TWS - U at Psi = 180). The reported
``AWA`` is the direction the apparent wind blows *towards*, relative to the bow
(``AWA = -(180 - AWA_std)``, i.e. -180 head to wind, 0 for a tail wind): the toward-convention of
CONVENTIONS §2. A reading "Psi = 0 is downwind" would need the client's apparent wind to be
computed with the wrong sign. Hence ``TWA = degrees(Psi)`` (NOT ``180 - Psi``).

Regridding (default axes = spec grid, CONVENTIONS/DES-860 §2.2.2)
------------------------------------------------------------------
TWS 0-50 kn step 1 kn (m/s), TWA 0-180 deg step 2.5 deg, U 0-10 m/s step 0.25 m/s.

* Per TWS file, bilinear in (TWA, U) using only feasible corner nodes (weights renormalised); a
  target point is feasible iff its nearest native node is. Exact at native nodes.
* Then linear in TWS between files; a point is feasible only if feasible in both bracketing
  files.
* ``U > 8 m/s`` (beyond the data): infeasible. ``0 <= U < 0.1``: constant extension of the
  ``U = 0.1`` value (HYPOTHESIS; the 0.1 m/s offset is negligible for stopped-ship modes).
* Infeasible nodes are NaN in ``PolarTable.p`` and False in ``PolarTable.feasible``; nothing is
  filled with fake values.

TWS < 10 kn (no data) -- HYPOTHESIS, to be confirmed by the client
-------------------------------------------------------------------
Client statement (2026-11-10): "we produce very little, or nothing -- so net power is negative
over almost the whole polar". The gross/consumption split cannot be recovered from the data (the
turbine formula ``0.5 rho A eta 4a(1-a)^2 (AWS (z/10)^0.14)^3`` reproduces the net power only
for a nearly stopped ship downwind, where ``P = 2.594 AWS^3``), so the 10 kn file is split by
sign: the positive part is treated as turbine surplus and scaled by
``m(TWS) (TWS/10 kn)^3``, the negative part (propulsion consumption) is kept::

    P(TWS) = m(TWS) (TWS/TWS_10)^3 max(P_10, 0) + min(P_10, 0),
    m = smoothstep((TWS - cutin) / (10 kn - cutin)),   cutin = 7 kn (default, hypothesis).

So below the cut-in net power is <= 0 everywhere and at TWS = 0 it equals ``min(P_10, 0)``
(~0 only for a stopped ship). The feasibility mask of the 10 kn file is reused (conservative).

Physics note (client, 2026-11-10 12:02)
---------------------------------------
Head to wind the Flettner rotors give no thrust and the electric propeller counters the
turbine's thrust to hold the speed, so net power there is <= 0 (this is normal physics, not rotor
shading). The turbine is always aligned with the apparent wind. Each polar point is the result of
an optimisation (turbine pitch, Flettner spin ratios, propeller power, appendage angle)
maximising net power under heading/speed constraints.

Empty cells and hole repair (client, 2026-11-10 12:02)
------------------------------------------------------
Some NaN cells are artefacts (optimiser hit its iteration limit), others are genuinely
unreachable states. For each (TWS, TWA) the reachable U set is an interval; NaNs strictly inside
it, isolated NaNs in the (TWA, U) plane and NaN blocks surrounded by feasible values in the two
neighbouring TWS files (e.g. the 32 kn stopped-downwind corner) are artefacts and are filled by
interpolation (``repair_holes=True``, default; counts in ``meta["repair"]``). NaNs beyond the
reachable speed (above ``U_max`` at that TWA, U > 8 m/s) stay infeasible.

Operational limits
------------------
Client statement (2026-11-10, 11:43): generator limitation and derating are ALREADY included in the
BETA polars -- no overlay is applied by default. :func:`apply_operational_limits` is an optional
(default off) utility only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from horizon.core.units import KNOT
from horizon.polar.table import PolarTable, default_axes

__all__ = ["BETA_P_BOUNDS_KW", "apply_operational_limits", "load_beta_polar", "read_beta_file"]

BETA_P_BOUNDS_KW = (-3500.0, 3000.0)  #: sanity range of the real polar [kW]
_NAME = re.compile(r"polar_BETA_TWS=(\d+)_")


def read_beta_file(path: str | Path) -> dict:
    """Read one BETA CSV into native-grid arrays.

    Parameters
    ----------
    path : str or Path
        ``polar_BETA_TWS=<kn>_<date>.csv``.

    Returns
    -------
    dict
        ``tws_kn`` (int), ``params`` (dict), ``u`` [m/s] (nU,), ``psi_deg`` [deg] (nPsi,) and
        ``power`` [kW], ``aws`` [m/s], ``awa`` [deg] of shape (nPsi, nU) (NaN power = infeasible).
    """
    path = Path(path)
    m = _NAME.search(path.name)
    if not m:
        raise ValueError(f"unexpected file name {path.name}")
    with open(path) as fh:
        first = fh.readline()
    if not first.startswith("# Params:"):
        raise ValueError("missing '# Params:' line")
    params = json.loads(first[len("# Params:"):])
    raw = np.genfromtxt(path, delimiter=",", skip_header=3)
    u = np.unique(raw[:, 0])
    psi = np.unique(raw[:, 1])
    if raw.shape[0] != u.size * psi.size:
        raise ValueError(f"{path.name}: rows do not form a full (Psi, U) grid")
    iu = np.searchsorted(u, raw[:, 0])
    ip = np.searchsorted(psi, raw[:, 1])
    out = {}
    for name, col in (("power", 4), ("aws", 2), ("awa", 3)):
        a = np.full((psi.size, u.size), np.nan)
        a[ip, iu] = raw[:, col]
        out[name] = a
    return {"tws_kn": int(m.group(1)), "params": params, "u": u, "psi_deg": np.degrees(psi),
            **out}


def _axis_weights(src: np.ndarray, tgt: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lower index, upper weight (clamped to [0, 1]) and in-range flag for linear interpolation."""
    i = np.clip(np.searchsorted(src, tgt, side="right") - 1, 0, src.size - 2)
    w = np.clip((tgt - src[i]) / (src[i + 1] - src[i]), 0.0, 1.0)
    inside = (tgt <= src[-1] + 1e-9) & (tgt >= -1e-9)
    return i, w, inside


def _regrid_plane(psi, u, p, twa_t, u_t):
    """Feasibility-aware bilinear regrid of ``p[psi, u]`` onto ``(twa_t, u_t)``.

    Returns ``(values, feasible)``, both shape (len(twa_t), len(u_t)); infeasible values NaN.
    """
    ia, wa, ina = _axis_weights(psi, twa_t)
    ib, wb, inb = _axis_weights(u, u_t)
    ok = np.isfinite(p)
    pz = np.where(ok, p, 0.0)
    num = np.zeros((twa_t.size, u_t.size))
    den = np.zeros_like(num)
    best_w = np.full(num.shape, -1.0)
    nearest_ok = np.zeros(num.shape, dtype=bool)
    for da in (0, 1):
        wia = (wa if da else 1 - wa)[:, None]
        for db in (0, 1):
            wib = (wb if db else 1 - wb)[None, :]
            w = wia * wib
            ii = (ia + da)[:, None]
            jj = (ib + db)[None, :]
            m = ok[ii, jj]
            num += w * pz[ii, jj] * m
            den += w * m
            better = w > best_w
            nearest_ok = np.where(better, m, nearest_ok)
            best_w = np.where(better, w, best_w)
    feas = nearest_ok & (den > 0) & ina[:, None] & inb[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        val = np.where(feas, num / den, np.nan)
    return val, feas


def _repair_native(power: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Fill artefact NaNs of one native ``power[psi, u]`` plane.

    Rule 1: NaN strictly inside the feasible U interval of its row -> linear in U.
    Rule 2: NaN with >= 7 of 8 feasible neighbours in the (psi, U) plane -> neighbour mean.

    Returns
    -------
    filled : numpy.ndarray
    n_interval, n_isolated : int
        Number of nodes filled by rule 1 / rule 2.
    """
    p = power.copy()
    n1 = n2 = 0
    for i in range(p.shape[0]):
        ok = np.isfinite(p[i])
        if ok.sum() < 2:
            continue
        idx = np.flatnonzero(ok)
        hole = ~ok
        hole[: idx[0]] = False
        hole[idx[-1] + 1:] = False
        if hole.any():
            p[i, hole] = np.interp(np.flatnonzero(hole), idx, p[i, idx])
            n1 += int(hole.sum())
    ok = np.isfinite(p)
    pad = np.pad(np.where(ok, p, 0.0), 1)
    cnt = np.pad(ok.astype(float), 1)
    nsum = np.zeros_like(p)
    ncnt = np.zeros_like(p)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            sl = (slice(1 + di, 1 + di + p.shape[0]), slice(1 + dj, 1 + dj + p.shape[1]))
            nsum += pad[sl]
            ncnt += cnt[sl]
    iso = ~ok & (ncnt >= 7)
    p[iso] = nsum[iso] / ncnt[iso]
    n2 = int(iso.sum())
    return p, n1, n2


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def load_beta_polar(directory: str | Path, tws_kn=None, twa=None, u=None, cutin_kn: float = 7.0,
                    repair_holes: bool = True,
                    p_bounds: tuple[float, float] = BETA_P_BOUNDS_KW) -> PolarTable:
    """Load the client's BETA power polars onto uniform ``(TWS, TWA, U)`` axes.

    See the module docstring for conventions, regridding and the TWS < 10 kn hypothesis.

    Parameters
    ----------
    directory : str or Path
        Folder with ``polar_BETA_TWS=<kn>_*.csv`` (TWS 10, 12, ..., 50 kn).
    tws_kn : array_like  [kn], optional
        Target TWS axis (uniform). Default 0..50 step 1.
    twa : array_like  [deg], optional
        Target TWA axis (uniform, 0 = head to wind). Default 0..180 step 2.5.
    u : array_like  [m/s], optional
        Target speed-through-water axis (uniform). Default 0..10 step 0.25.
    cutin_kn : float  [kn]
        Turbine cut-in below which the extrapolated gross output vanishes (HYPOTHESIS, 7 kn).
    repair_holes : bool
        Fill optimiser-failure artefacts (see module docstring): NaNs inside the feasible U
        interval, isolated NaNs, and blocks feasible in both neighbouring TWS files. Genuinely
        unreachable states stay NaN. Default True (client answer 2026-11-10 12:02).
    p_bounds : (float, float)  [kW]
        Sanity bounds applied to feasible values.

    Returns
    -------
    PolarTable
        Net power [kW] with NaN at infeasible nodes (``feasible`` mask); ``meta`` holds the vessel
        ``params``, source file names and ``hypotheses`` (what is extrapolated).
    """
    d0_tws, d0_twa, d0_u = default_axes()
    tws_kn_a = np.arange(0, 51, dtype=float) if tws_kn is None else np.asarray(tws_kn, float)
    twa_a = d0_twa if twa is None else np.asarray(twa, float)
    u_a = d0_u if u is None else np.asarray(u, float)
    files = sorted(Path(directory).glob("polar_BETA_TWS=*.csv"),
                   key=lambda f: int(_NAME.search(f.name).group(1)))
    if not files:
        raise FileNotFoundError(f"no polar_BETA_TWS=*.csv in {directory}")
    nodes = [read_beta_file(f) for f in files]
    n_nan_native = int(sum(np.isnan(n["power"]).sum() for n in nodes))
    n_interval = n_isolated = 0
    if repair_holes:
        for n in nodes:
            n["power"], a, b = _repair_native(n["power"])
            n_interval += a
            n_isolated += b
    kn_nodes = np.array([n["tws_kn"] for n in nodes], dtype=float)
    planes, masks = [], []
    for n in nodes:
        v, f = _regrid_plane(n["psi_deg"], n["u"], n["power"], twa_a, u_a)
        planes.append(v)
        masks.append(f)
    planes = np.stack(planes)
    masks = np.stack(masks)
    n_block = 0
    if repair_holes:
        pz0 = np.where(masks, planes, 0.0)
        hole = np.zeros_like(masks)
        hole[1:-1] = ~masks[1:-1] & masks[:-2] & masks[2:]
        planes = np.where(hole, 0.5 * (np.roll(pz0, 1, 0) + np.roll(pz0, -1, 0)), planes)
        masks = masks | hole
        n_block = int(hole.sum())
    pz = np.where(masks, planes, 0.0)

    p = np.full((tws_kn_a.size, twa_a.size, u_a.size), np.nan)
    feas = np.zeros(p.shape, dtype=bool)
    k10 = kn_nodes[0]
    for it, kn in enumerate(tws_kn_a):
        if kn < k10 - 1e-9:  # extrapolation below the first file
            m = _smoothstep((kn - cutin_kn) / (k10 - cutin_kn))
            base = pz[0]
            p[it] = m * (kn / k10) ** 3 * np.maximum(base, 0.0) + np.minimum(base, 0.0)
            feas[it] = masks[0]
        else:
            kn_c = min(kn, kn_nodes[-1])
            j = int(np.clip(np.searchsorted(kn_nodes, kn_c, side="right") - 1, 0, len(nodes) - 2))
            w = (kn_c - kn_nodes[j]) / (kn_nodes[j + 1] - kn_nodes[j])
            if abs(w) < 1e-9:
                p[it], feas[it] = pz[j], masks[j]
            elif abs(w - 1) < 1e-9:
                p[it], feas[it] = pz[j + 1], masks[j + 1]
            else:
                p[it] = (1 - w) * pz[j] + w * pz[j + 1]
                feas[it] = masks[j] & masks[j + 1]
    params = {k: v for k, v in nodes[0]["params"].items() if "True Wind speed" not in k}
    meta = {
        "source": "BETA VPP polars (client, confidential)",
        "params": params,
        "files": [f.name for f in files],
        "native_tws_kn": kn_nodes.tolist(),
        "twa_convention": "TWA = degrees(Psi): 0 head to wind, 180 dead downwind",
        "operational_limits": "generator limitation and derating already included; no overlay",
        "hypotheses": {
            "tws_below_native": f"gross scaled (TWS/{k10:g} kn)^3 with cut-in {cutin_kn:g} kn; "
                                "consumption kept; 10 kn mask reused",
            "u_below_0.1": "constant extension of U = 0.1 m/s",
            "u_above_8": "infeasible",
        },
        "cutin_kn": cutin_kn,
        "repair": {"native_nan": n_nan_native, "filled_interval": n_interval,
                   "filled_isolated": n_isolated, "filled_tws_block_regridded": n_block,
                   "kept_infeasible_native": n_nan_native - n_interval - n_isolated},
    }
    return PolarTable(p, tws_kn_a * KNOT, twa_a, u_a, feasible=feas, meta=meta, p_bounds=p_bounds)


def apply_operational_limits(polar: PolarTable, derate_start_kn: float = 25.0,
                             cutout_kn: float = 35.0, mode: str = "none") -> PolarTable:
    """Optional operational overlay (derating then cut-out); DEFAULT OFF (``mode="none"``).

    Client statement (2026-11-10): the BETA polars already include generator limitation and
    derating, so the real polar is used as-is; the 25/35 kn pair is a property of the synthetic
    polar only. The VPP data itself shows no cut-out up to 50 kn. This utility exists only for
    what-if studies.

    ``mode="derate_cutout"``: the positive part of the net power (turbine surplus) is scaled by
    ``f = 1 - smoothstep((TWS - derate_start) / (cutout - derate_start))``; the negative part
    (propulsion consumption) is kept. At and above ``cutout_kn`` the net power is therefore
    ``min(P, 0)``, i.e. NEGATIVE (turbine stopped), NOT zero. The gross/consumption split cannot
    be derived from the data (the AWS turbine formula does not reproduce the net power away
    from the stopped-ship case), hence the sign split. Whether "cut-out" means "turbine stopped
    but consumption continues" must be confirmed by the client.

    Parameters
    ----------
    polar : PolarTable
    derate_start_kn, cutout_kn : float  [kn]
        Derating start and cut-out wind speeds.
    mode : {"none", "derate_cutout"}

    Returns
    -------
    PolarTable
        New table (same axes, mask, metadata plus ``operational_overlay``).
    """
    if mode not in ("none", "derate_cutout"):
        raise ValueError("mode must be 'none' or 'derate_cutout'")
    if mode == "derate_cutout" and not cutout_kn > derate_start_kn:
        raise ValueError("cutout_kn must exceed derate_start_kn")
    p = polar.p.astype(np.float64)
    meta = dict(polar.meta)
    if mode == "derate_cutout":
        kn = (polar.tws / KNOT)[:, None, None]
        f = 1.0 - _smoothstep((kn - derate_start_kn) / (cutout_kn - derate_start_kn))
        p = f * np.maximum(p, 0.0) + np.minimum(p, 0.0)
    meta["operational_overlay"] = {"mode": mode, "derate_start_kn": derate_start_kn,
                                   "cutout_kn": cutout_kn}
    return PolarTable(p, polar.tws, polar.twa, polar.u, strict=polar.strict,
                      feasible=polar.feasible, meta=meta, p_bounds=polar.p_bounds)
