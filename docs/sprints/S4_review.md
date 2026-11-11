# Sprint 4 — Full year 2015, forecast v2, coast margin, port departures, value function — Review

Date: 2026-11-11. Orchestrator Opus 5.5; agents Sonnet 5.5. Details: `S4_results.md`, `S4_value.md`,
`S4_forecast_notes.md`, `S4_review_notes.md`.

## Delivered
* Forecast model v2: issue-to-issue consistency (no convergence to truth by averaging), availability
  latency (ENS 6 h, control 4 h, 00/06/12/18 cycles), seasonal skill, lazy 50 members.
* Coast margin: exact bilinear chord minimum in DP, refiner re-check on the bilinear SDF, safe start,
  simulator guard. **0 violations, 0 guard interventions** on all year runs.
* Lorient harbour-exit corridor; resumable year-long persistent runs (monthly checkpoints, survived two
  server restarts).
* Inspector: capacity factor first, perceptual wind palette with isotachs, per-router polar occupancy,
  Seasons tab, "Models explained" guide with schematics and primer.
* E0 hindsight-bias study; learned policy-consistent terminal value Vθ (LightGBM, MIT).

## Results — median fleet ship at sea all 2015 (CF recomputed independently from raw segments)

| Policy | Annual CF | Regret vs Oracle_REF_H |
|---|---|---|
| Oracle_REF_H (15 d hindsight + refiner, approx. bound) | 0.880 | 0 |
| ENS_REF (20 members, 10 d, clim terminal, refiner) | 0.807 | 8.3 % |
| B1c_5d_REF (seeds 1 / 2) | 0.797 / 0.799 | 9.4 / 9.2 % |
| B1_5d_REF | 0.775 | 11.9 % |
| B0 best fixed point | 0.571 | 35.1 % |

Routing vs B0 +44 % (12/12 months; July CF 0.67 vs 0.35). Climatological terminal +2.8 % (10/12).
ENS vs B1c +1.2 % (9/12, n.s.). Lorient departures: CF 0.71 vs 0.78 at sea over 14 d (≈ −68 MWh per
departure); 50 km offshore in < 5 h.

E0: hindsight values biased high, +7 to +16 % at 2-5 d (≈ 17 % of it DP discretisation), seasonal
(9.5 % winter → 19.4 % July), moderately non-uniform in space. Vθ: R² 0.44 on 5-day energy vs 0.06
climatological, but no better spatial ranking than a hindsight-trained model; closed loop +0.6 CF pt
(3 months, n.s.).

## Limitations
One year of data, perturbation-model forecasts (not NWP), one ENS forecast seed, B0/climatology from
the same year (mild leakage), Oracle_REF_H is an approximate bound, year = 8759 h (archive ends 23 UTC).
