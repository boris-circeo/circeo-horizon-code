# Sprint 1 — Deterministic core & closed-loop backtest — Review

Date: 2026-11-10. Orchestrator Opus 5.5; agents Sonnet 5.5 (3 implementers, 1 independent reviewer).
Detailed numbers: `S1_results.md`.

## Delivered

| Module | Content |
|---|---|
| `weather.fields` | `WindField` / `Ensemble` containers (binding interface) |
| `weather.synthetic` | synthetic North-Atlantic winter: westerly jet, cyclones (genesis, ENE drift 20-35 kn, lifecycle), NAO-like regime, noise; causal forecasts with lead-dependent errors; spread/skill 0.84-0.93 at D3-D7 |
| `dp` | geodesic stencil (true lengths/headings per cell, coast clearance), Numba backward DP, path extraction; 40 km basin 13 days in 0.5 s |
| `polar.envelope` | **mixed-heading power envelope**: upper concave envelope of P over ground velocity in the wind frame (zig-zag/tacking), unifies transit and hold arcs, removes stencil-quantisation bias (low-wind "sit still" 83 % -> 0 %) |
| `sim` | causal closed-loop simulator (forecast access guarded), power models, policies B0 / B1 (5 d, 15 d) / oracle, metrics, backtest script |

192 tests, ruff clean. Physical tests §8.4 (i)-(iv) implemented; toy front: DP anticipates (7.0 vs 4.3 MWh for a myopic policy).

## First regret figure (synthetic weather — indicative only)

| Policy | J [MWh / 30 d] | CF | Regret |
|---|---|---|---|
| Oracle (hindsight) | 1838 ± 111 | 0.85 | 0 |
| B1 deterministic MPC 5 d | 1608 ± 161 | 0.75 | 12.6 ± 4.3 % |
| B1 deterministic MPC 15 d | 1542 ± 155 | 0.71 | 16.2 ± 4.7 % |
| B0 best fixed point (46.7N 2.8W) | 1411 ± 178 | 0.65 | 23.5 ± 5.1 % |
| B0 at spec point 50N 15W | 1073 ± 166 | 0.50 | 41.8 ± 6.5 % |

Independent review: no information leakage (bit-identical forecasts after erasing the future), energy independently recomputed to 1e-5, float32 accumulation error 6e-7. Regrets are biased ~2 points low (oracle sees truth at 3 h only).

## Findings

1. **Longer deterministic horizon hurts** (15 d worse than 5 d): consistent with the spec's thesis (Jensen, §2.2.3/§4.4) — deterministic long-lead forecasts mislead. Motivates S2 (ensembles + CVaR) and a policy-consistent terminal value.
2. **Synthetic climatology bias**: best fixed point is near the French coast (Bay of Biscay), not 48-52N/12-18W as the spec expects; storms in the generator intensify eastward. Real ERA5 is needed before drawing any conclusion on B0 vs routing value.
3. **Stencil angular resolution** (40 km / 3 h -> K = 21, gaps up to 26.6°): staircase tracks, ~6 % orientation dependence of energy. The spec's "~55 neighbours" is inconsistent with U_max = 8 m/s at 45 km / 3 h. Options: multi-step arcs, finer fine-layer grid, or continuous refiner (S2).
4. Cells within d_min (20 km) of the coast are infeasible: departure from Lorient needs a harbour-exit corridor (F-legs, later).

## Simplifications (S1)

No leeway/current at graph level; no forecast latency; zero terminal value; no return-to-port constraint; single resolution 40 km / 3 h; truth hourly at 40 km.
