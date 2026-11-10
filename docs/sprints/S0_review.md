# Sprint 0 — Foundations — Review

Date: 2026-11-10. Orchestrator: Opus 5.5. Implementation/review agents: Sonnet 5.5 (3 implementers in parallel + 1 independent reviewer).

## Delivered

| Module | Content | Tests |
|---|---|---|
| `geo.grid` | LAEA equal-area planning grid; Jacobian-based true<->grid heading conversion | 15 |
| `core.units/wind/kinematics`, `geo.vectors` | wind conventions (u,v toward / met from), TWA (signed, tack), apparent wind, smooth C^1 leeway, drift-compensated heading, station-keeping TWA | ~50 |
| `polar` | `PolarTable` (uniform axes, Numba trilinear, CSV loader for real tables), synthetic polar (HYPOTHESES), arc reward tables, hold (station-keeping) curve | ~57 |
| `geo.coast` | Natural Earth 10m -> land mask -> SDF on 10 km grid (~1 s), Numba bilinear, committed 226 kB asset | 9 |
| cross-module | convention consistency, physical bounds, symmetry, packaging | 11 |

Total: 151 tests passing, ruff clean.

## Spec findings (DES-860 rev A)

1. **§2.2.6 TWA formula is off by 180°** when W is the "toward" vector. Code uses `TWA = arccos(-W·e_psi/|W|)` (CONVENTIONS §3).
2. **§2.2.6 leeway** `k_L |W| n_perp` is discontinuous when the wind is along the heading; implemented as `k_L |W| sin(TWA) n_lee` (C^1, required by the NLP).
3. **§2.2.6 apparent wind** must use the through-water velocity, not ground velocity, when a current exists.
4. **§1.6 vs §2.2.6**: hold-curve loss "4-15 %" vs "5-15 %" — minor.
5. **§2.2.1**: "flat optimum ±10-15°" vs "half-width ±20-25°" and "P(45°)≈P(90°)/3-4" cannot all be met by a single smooth shape; synthetic polar favours the last two.

## Engineering notes

* LAEA is not conformal: heading conversion by a pure rotation errs by up to ~0.7° at basin edges — replaced by local Jacobian.
* Grid metres vs ground metres differ by up to ~3 % at basin edges: **the S1 DP must use geodesic arc lengths** (per-cell or per-row correction), not grid lengths.
* Synthetic polar initially generated positive power head-to-wind (Lorentzian tail); fixed with a close-hauled suppression (no generation at TWA ≤ 30°), regression-tested.

## Hypotheses to confirm (with real polars / naval architect)

* All `SyntheticPolarParams` (cut-out 42 kn, derating from 35 kn, close-hauled cutoff, broad-reach shape).
* Port/starboard symmetry of the polar.
* Leeway coefficient k_L = 0.03; manoeuvre cost τm = 4 min, ρm = 0.3; legs 45 min.
* Hold TWA ≈ 85° at 20 kn (drift compensation bias).

## Next: Sprint 1

Synthetic weather generator (truth + ensembles), deterministic DP kernel (bi-resolution, hold arcs, geodesic lengths), closed-loop simulator with baselines B0/B1 and hindsight oracle -> first regret figure.
