# HORIZON v2 — validation on the bench-6 windows (WP6)

Campaign `scripts/s5/campaign_v2.yaml` (72 cases, 2026-11-12, code 2254722; all runs in MLflow,
theme `S5_v2-validation`). Same protocol as `sensitivity.md`: 6 windows of 30 days in 2015,
paired deltas vs the default configuration of the same router and forecast seed.

## HORIZON v2 definition

| Parameter | v1 (`B1c_5d_REF`) | **v2 (`HORIZON_V2`)** | Evidence |
|---|---|---|---|
| DP horizon | 5 d | **3 d** | horizon 3/5/7/10 d within noise when a terminal value is present |
| Terminal value | annual climatology incl. test window | **climatology, leave-window-out** | leak measured at ±0.1 pt; leak-free by construction |
| Refiner window | 48 h | **24 h** | 24 / 48 / 72 h within noise |
| Refiner limits | 200 iterations **and 20 s CPU** | **500 iterations, no CPU limit** | results no longer depend on machine load |
| Replan period | 6 h | 6 h | 24 h −1.4 pt, 3 h no gain |
| Grid, arcs | 40 km / 3 h, span 2 | unchanged | 20 km +0.9 pt n.s. at 3× cost; span 1/3 n.s. |
| Forecast used | control | control | ensemble router = control at nominal error, 5× cost |
| Coast clearance | 20 km | 20 km in evaluation (30–40 km recommended in operation) | 40 km +0.7 pt n.s. |

## Results (mean CF over the 6 windows)

| Router | Seed 1 | Seed 2 | Paired v2 − v1 [pt] | CPU per 30-day window |
|---|---|---|---|---|
| v1 `B1c_5d_REF` | 79.9 % | 80.7 % | — | 5.8 min |
| **v2 `HORIZON_V2`** | **79.8 %** | **80.9 %** | −0.1 ± 0.6 / +0.2 ± 0.6 | **2.4 min** (2.4–3.9× faster) |
| Oracle (leak-free, deterministic refiner) | 86.3 % | | | 4.8 min |
| B0 fixed optimal point | 58.8 % | | | — |

Refiner convergence: 100 % of the 720 v2 replans per seed (v1: 72–97 % depending on the window,
non-converged iterates were accepted when better than the warm start).

Ablations of v2: horizon 5 d +0.2 pt, refiner 48 h +0.1 pt (both n.s.); **no terminal value −2.7 pt
(z −4.2)** — the climatological terminal value is the one ingredient that the short horizon needs.

## Checks on v1 conclusions

* **CPU-time limit.** Removing it with the same 200-iteration budget reproduces v1 *exactly*
  (delta 0.00): at campaign load the limit never bound, so all S5 sensitivity results stand.
  Raising the budget to 500 / 1000 iterations: +0.2 / +0.1 pt (n.s.). Convergence does not drive CF.
* **Climatology leak.** Leave-window-out terminal climatology: −0.1 / +0.1 pt on two seeds (n.s.).
  The leak suspected in the external review is real in principle but immaterial in effect.
* **Oracle.** Leak-free and deterministic: 86.3 % vs 86.2 %.

## Verdict

HORIZON v2 delivers the same capacity factor as v1 (within ±0.2 pt) with **less than half the
computation, deterministic results and no hindsight leak**. The remaining gap to the oracle
(~5–6 pt) is the forecast's, not the algorithm's (perfect forecast: 1.1 pt gap).
