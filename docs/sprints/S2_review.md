# Sprint 2 — Uncertainty, continuous refiner, results inspector — Review

Date: 2026-11-10. Orchestrator Opus 5.5; agents Sonnet 5.5 (3 implementers, 1 experiment runner, 1 independent diagnostician).
Details: `S2_results.md` (numbers), `S2_diagnosis.md` (ensemble diagnosis).

## Delivered

| Module | Content |
|---|---|
| `ensemble` | in-house weighted vector-wind EOF + PAM k-medoids (GPL `eofs`/`kmedoids` avoided); medoids are real members |
| `dp.stochastic` | Annex A.2 recursion: per-scenario DP to 48 h, aggregation (1-γ)E + γ·CVaR_α, deterministic 48 h trunk (non-anticipativity) |
| `refine` | CasADi/IPOPT multiple-shooting OCP 0-48 h at 30 min on the **power envelope** (concave in velocity), exact derivatives, SDF constraint, DP value field as terminal, retry ladder + safe fallback |
| `sim` | `EnsembleMPCPolicy`, `RefinedMPCPolicy`, resumable S2 backtest |
| `viz` | self-contained offline HTML inspector (overview, explorer with synced map/time series, diagnostics, biggest losses, replan diagnostics) + pedagogical layer (captions, ⓘ, glossary, attention chips, FR/EN guide, tour) |

## Results (5 synthetic winters × 30 d)

| Policy | Regret vs oracle |
|---|---|
| **B1_5d_REF** (deterministic 5 d + refiner) | **10.0 ± 1.8 %** |
| B1_5d | 12.6 ± 4.3 % |
| ENS_g03_REF | 13.0 ± 3.4 % |
| ENS_g0 (15 d, expectation) | 14.8 ± 4.3 % |
| ENS_g03 (15 d, CVaR γ=0.3) | 15.4 ± 3.8 % |
| B1_15d | 16.2 ± 4.7 % |
| B0 / B0_spec | 23.5 / 41.8 % |

* **Refiner**: +44-46 MWh/month (≈ +3 %), 4/5 and 5/5 paired wins, halves inter-winter spread. Clearest effect.
* **Ensemble (E1)**: ENS_g0 vs B1_15d +1.7 % (3/5) but ENS does not beat B1_5d. CVaR: no tail benefit.

## Diagnosis of the ensemble result — no bug, data artefact

* Exact reduction to deterministic DP when all members = control (bit-identical trunk).
* The synthetic ensemble is calibrated in spread (spread/skill ≈ 1, flat-ish rank histograms) but **its mean has no skill over the control** (RMSE D7 4.50 vs 4.23 m/s): the generator places the control at the exact centre of the error distribution, so members add spread, not information. Real ensembles' means beat their control beyond ~D3.
* Matched-horizon test (ENS 5 d vs B1 5 d) confirms no gain on this data; per-scenario tails after 48 h are clairvoyant within each scenario → plan optimism ≈ +30 % for both ENS and B1_15d.
* **Conclusion: the value of ensembles cannot be evaluated on the current synthetic forecasts.**

## Recommendations for S3 (ranked)

1. Realistic forecast information: real reforecasts (GEFS v12) or, failing that, an ERA5-based error model where the control is a random draw and the ensemble mean beats it. Re-run E1.
2. Trunk beyond ~D3 from ensemble mean / lead-blended field rather than the control.
3. Terminal value: replace zero / clairvoyant tails by a climatological then learned (policy-consistent) value — the spec's D2; shorter scenario horizon 5-7 d.
4. Keep the refiner as default; ≥ 10 seeds for statistics.
5. No tuning of k / γ before item 1.
