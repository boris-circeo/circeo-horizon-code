# Sprint 3 — Real data (ERA5 2015, BETA polar) — Review

Date: 2026-11-10. Orchestrator Opus 5.5; agents Sonnet 5.5. Details: `S3_results.md`, `S3_review_notes.md`.
Client data (ERA5 extract, BETA polars) lives in a separate private repository and is never committed here.

## Delivered

| Module | Content |
|---|---|
| `weather.era5` | GRIB → regridded hourly cache on the 40 km LAEA grid (u/v true east/north verified to 1e-6 vs raw); `outside` mask of cells not covered by ERA5 (made non-navigable) |
| `weather.forecast_model` | exchangeable perturbation ensemble on ERA5 truth (displacement + amplitude + noise growing with lead); control RMSE 2.3/3.9/5.0/6.2 m/s at D1/3/5/7, ensemble mean beats control, spread/skill ≈ 1 |
| `polar.beta` | BETA VPP loader: **Psi = TWA (0 = head to wind)** (AWS identity to 2e-5 m/s); optimisation-failure holes repaired (client); slow-downwind sector TWA ≥ 135°, U ≤ 2.5 m/s masked as VPP bug (client, bounds = orchestrator choice); TWS < 10 kn ≈ no production (client) |
| `polar.climatology` | climatological hold-power terminal value |
| `dp` | macro arcs spanning 1-2 steps (K = 49, worst angular gap 18.4°) — fixes "square" tracks; dense arc coast sampling |
| `refine` | coast constraint at nodes + quarter/mid points with 2 km buffer |
| `sim` | `Oracle_REF` (hindsight DP + refiner on truth) = J_hind; `FeasiblePowerModel` |
| `viz` | 4K layout, Polar tab, ship operating-point inset, ERA5 dates/mask |

## Results — 10 missions × 30 d, 2015 (ENS: 6 winter missions)

| Policy | J [MWh] | Regret vs J_hind |
|---|---|---|
| B0 best fixed point | 1364 | 29.4 ± 6.6 % |
| B1 deterministic 5 d | 1708 | 11.5 ± 3.3 % |
| B1 5 d + refiner | 1820 | 5.7 ± 2.8 % |
| B1 5 d + refiner + climatological terminal | 1836 | 4.9 ± 2.3 % |
| ENS 10 d (γ = 0) | 1818 | 7.7 ± 1.9 % |
| **ENS 10 d + refiner** | **1903** | **3.4 ± 2.2 %** |
| Oracle (3 h DP, hindsight) | 1871 | 3.1 ± 0.5 % |

Paired: refiner +112 MWh (10/10); B1 vs B0 +343 MWh (10/10); climatological terminal +16 MWh (7/10);
ENS+REF vs B1c+REF +12 MWh (4/6, not significant). No causal policy beats J_hind.

## Findings

1. Routing is clearly worth it on real data: +25 % energy vs the best fixed point; the continuous refiner is the biggest single lever (+6-7 %).
2. With realistic (exchangeable) forecasts the ensemble now helps without refiner (+66 MWh, 5/6) but its edge over a refined deterministic router with climatological terminal value is small (+0.7 %); to be confirmed on more winters and real reforecasts.
3. The real polar changes the problem vs the spec narrative: in strong wind most of the downwind half-plane is productive; light wind (< 10 kn) is costly; hold = beam-reach tacks at 3.5-4 m/s.

## Known limitations

* One year (2015), overlapping missions, 6-10 missions: indicative statistics only; B0 point chosen on the same year (mild leakage).
* Forecasts are a calibrated perturbation model of the truth, not NWP; errors of successive issues are independent.
* Residual coast-margin violations (strict 20 km): B1_5d_REF min 18.9 km, Oracle_REF min 16.8 km; non-refined DP corner cutting 19.75 km — to fix (S4).
* `FeasiblePowerModel` slightly optimistic when the refiner commands an infeasible velocity (observed once, 4 steps).
* `ForecastProvider` exposes the weather object to policies (structural, unused) — harden before any external router is plugged in.
* VPP-bug mask bounds (135°, 2.5 m/s) to be confirmed by the client.
