# HORIZON S5 - External critical review

Reviewer: external, branch `s5-review` (worktree). Scope: core, geo, polar, weather, dp, refine,
ensemble, sim, scripts. Not read line by line: `value/`, `viz/`, `polar/beta.py`, `polar/table.py`
(skimmed only). Timings are CPU seconds (`process_time`) of ONE replan on the 40 km ERA5 grid
(79 x 82 cells), start 2015-01-01 offshore point, t = 5 d, shared 2-core machine (+/- 15 %).
Reproduce: `python scripts/s5/profile_replan.py --router B1c_5d_REF|ENS_REF --cprofile`.

## 1. Findings

| # | Sev | Location | Issue | Status / evidence |
|---|---|---|---|---|
| 1 | Med | `forecast_model.py` `forecast()` | Valid times fell up to dt/2 short of `now + horizon` when `now - analysis` is not a multiple of dt (replan period or latency not a multiple of 6 h: e.g. now = 4 h -> last valid 51 h vs 52 h needed); the DP tail silently read persistence. Not triggered by the current campaign grid (replan 3/6/12/24 h, latency 0/6/12 h). | FIXED (ceil), tests `test_forecast_covers_requested_horizon_off_cycle` |
| 2 | Med | `longrun`/`s5lib.run_case` | `n_clamped`, `n_dp_fallback` (and any policy counter) counted only post-resume segments: results of resumed runs under-reported fallbacks. | FIXED: `CounterStateMixin` get/set_state in checkpoints; `n_clamped` summed from segment metrics; test `test_policy_counters_survive_checkpoint_state` |
| 3 | Med | `policies*.py`, `nlp.py` | Silent fallbacks: hold plan when no feasible start; refiner returns warm start / non-converged iterate with no record in results. | FIXED (counters): `n_hold_fallback`, `n_refined`, `n_warm_start`, `n_not_converged`, written to run json as `policy_stats` |
| 4 | **High (validity)** | `refine/nlp.py` | IPOPT hits `Maximum_Iterations_Exceeded` (200 it.) in a large share of replans (6 of 10 probed replans, both attempts in 3), and the non-converged iterate is accepted. Attempt 2 (5x smoothing, adaptive mu) improves the objective by 0.3-0.6 % when attempt 1 stalls. Plans are therefore partly solver-limit artefacts; `ipopt.max_cpu_time = 20 s` is CPU time -> load-dependent, not strictly reproducible. | OPEN, reported via counter 3. L-BFGS tested: worse (-0.6 to -2 % objective, never converges) -> rejected |
| 5 | Med | `s5lib.start_point/clim`, `run_s4_year` | Terminal climatology and B0 point use the whole year 2015 including the evaluated window (leak; S3 excluded touched months, S4/S5 do not). Affects all routers equally (paired comparisons fine), but absolute CF and the B0 gap are optimistic. | OPEN (exclude window months; changes results) |
| 6 | Med | `sim/power.py` `FeasiblePowerModel` | Infeasible commanded velocity is valued at a slowed velocity, ship still moves at full speed; if no slowed velocity works the power is 0 kW (not the hold power, which can be negative below 10 kn): optimistic. Counter exists; was 0 in 33/34 runs. | OPEN, documented |
| 7 | Low | `simulator.advance` vs `refine` | Simulator uses the nearest-cell constant Jacobian, refiner a cubic spline of it (<= ~1 % per cell mismatch in executed vs planned displacement). | OPEN |
| 8 | Low | `forecast_model._unit_fields` | Linear interpolation of the 3 h lattice AR(1) latent fields lowers variance between nodes (about -3 % at 48 h tau, -8 % at 18 h tau): error amplitude is slightly time-of-day dependent. FFT filter is periodic (fields wrap across the grid edges). | OPEN, modelling note |
| 9 | Low | `ForecastProvider._weather`, `_MeanProvider` | Truth reachable from a policy via `provider._weather` (python cannot prevent it); no shipped policy does it. Forecast = truth + perturbation by construction (H-X-1). | OPEN, design limit |
| 10 | Low | `dp/solver._envelope_for` | md5 of the polar at every solve (0.7 ms, negligible). | no action |
| 11 | Low | `policies.py` | Dead `_nearest_cell`. | REMOVED |
| 12 | Info | `DeterministicMPCPolicy.plan` | `ceil` of the horizon: last DP step may exceed the data end by < dt (persistence); documented behaviour. | no action |
| 13 | Info | float32 | `V` float32 with values up to 1e6 kWh (ulp 0.06 kWh) and accumulation in float64 per step: adequate; ties between arcs closer than 0.06 kWh are arbitrary. | no action |

No convention error (u/v, TWA, headings, units) found in `core/`, kernel, envelope, simulator,
manoeuvre detection; DP wind-time alignment (trapezoid on nodes, midpoint rule for macro arcs) checked.

## 2. Profile of one replan (CPU s)

| Component | B1c_5d_REF | ENS_REF |
|---|---|---|
| Forecast generation (DP + refiner calls) | 1.04 | 9.2 |
| DP (1 / 7 solves; ~0.6 / 0.83 s each) | 0.61 | 5.85 |
| Refiner (IPOPT; `nlpsol` build only 0.04-0.09 s) | 1.0 (probe: 1.0-3.9, typically 2-4 with 2 attempts) | 2.7 |
| Ensemble reduction (EOF + PAM) | - | 0.05 |
| Total | 2.4-2.6 | 17.5 |

Refiner: 65 % of the solver time is the exact Lagrangian Hessian of the MX B-spline graph
(`t_wall_nlp_hess_l` 1.0-1.8 s per attempt), MUMPS ~25 %. Rebuilding the NLP each replan is NOT the
problem (setup 1-4 %): reusing CasADi function objects buys nothing. A real gain needs data-as-
parameters on fixed-size windows + code generation (est. 3-5x on the Hessian), not attempted.
Forecast (ENS): 23 member draws x 0.37 s = latent RNG 3.4 s (RNG bound, 115 M normals/s),
FFT filtering 3.5 s (prime axis length 79 -> Bluestein), latent sums 1.1 s, warp 1.15 s.
DP arc-feasibility was recomputed at every solve (0.056 s of 0.6).

### Before / after

| Change | Result identical? | B1c replan | ENS replan |
|---|---|---|---|
| Baseline | - | 2.39 | 17.4 |
| Exact: arc-feasibility cache, in-place latent sums, latent-series LRU (160 MB), ceil fix | **bit-identical plans** (x, y, value) | 1.94 (x1.2, same-issue repeat; across replans the level-1/2 series are reused) | 17.3 (x1.0: cache budget < 21 streams x 40 MB) |
| + `fast_filter=True` (dense circulant matrix products instead of FFT; `HORIZON_FAST_FILTER=1` in s5lib) | NOT bit-identical: filter differs by 1e-6 (float32), which IPOPT/DP amplify to plan differences of 34-68 km at one replan and 0.1-0.2 % in plan value | 3.4-3.6 (IPOPT iteration count fluctuates) | 11.7 (x1.5; forecast 9.2 -> 3.6) |

`fast_filter` is OFF by default so that results stay comparable with the running campaign. It is
statistically equivalent (same law) but not path-identical; switch it on only for NEW runs
(v2 validation) and do not mix with old paired results. Not done: numba/vectorised DP kernel
(0.04 us per arc-evaluation, trilinear envelope lookup dominates; est. <= 1.3x), RNG speed-up
(would change all draws).

## 3. Tunables inventory (what matters)

| Parameter | Default | Where | Sensitivity | Recommended range / action |
|---|---|---|---|---|
| refiner on/off, `refiner_h` | 48 h | `RefinedMPCPolicy` | **very high** (+6-7 % energy, S3) | keep 24-72 h |
| `horizon_days` | B1 5, ENS 10, Oracle 15 | config | high | 3-7 (B1), 7-12 (ENS) |
| `terminal` clim, `terminal_days` | clim, 5 | config | medium (+2.8 %) | keep; fix leak (#5) |
| `members`/`k` (ENS) | 20/6 | config | low-medium (+1.2 % n.s.) | 10-20 / 5-8 |
| `replan_h` | 6 | s5lib | medium | 3-12 |
| `max_span` | 2 | stencil | medium (3 = +3 % energy at 2x DP) | 2 |
| `d_min_km`, grid 40 km | 20 | env | medium (discretisation 3-7 %) | fixed |
| `gamma`, `alpha`, `reduction_tau_d`, `split_h` | 0, 0.2, 7 d, 48 h | ENS | low | hide (fixed) |
| refiner `rho` (100,100), `max_iter` 200, `max_cpu_s` 20, `margin_m`, `safety_m`, `verify_m` | | `refine_plan` | medium for `rho`/`max_iter` (#4) | hide; make iterations explicit |
| DP `dt` 3 h, `u_bounds` (0.5, 8) | | solver | medium | fixed |
| envelope `f_avail` (tau 240 s, rho 0.3, t_leg 2700 s), `dv` 0.25 | | polar | medium | fixed, calibrate with client |
| `ManoeuvreModel` (tau, rho 0.3, turn 30 deg) | | sim | env, not router | environment only |
| forecast law (`ForecastErrorParams`, 30+ fields) | | weather | very high but environment | experiment knobs only: `error_scale`, `latency_h`, `consistency`, `spread_factor` |

`HorizonConfig` (src/horizon/config.py) now exposes the router tunables in one validated frozen
dataclass; everything in the table marked "hide" stays at class defaults.

## 4. Refactor summary

* `horizon.config.HorizonConfig` + `make_policy`: replaces the three copies of router
  construction (`run_s3_backtest.make_policy`, `run_s4_year.build`, `s5lib.build_router`);
  `run_s4_year.build` and `s5lib.build_router` now call it (s3 script left as historical).
  Validation at construction (unknown kind/overrides, ranges, `k <= members`). `s5lib` keeps its
  `ROUTER_DEFAULTS` dicts untouched so case ids / result files are unchanged; a test asserts the
  s5 defaults equal `PRESETS`. Plans of B1c and ENS were verified bit-identical before/after.
* Not done (recommended): move `Ctx` (client paths hard-coded in `run_s3_backtest`) to
  `horizon.context` with an explicit data-dir argument; unify the power-model stack
  (Direct/Envelope/Feasible) construction, still repeated in `s5lib._build_ctx_other_dx`;
  `GreedyPolicy`/`_safe_start` coast checks.

## 5. Open recommendations

1. Make refiner convergence explicit: log `n_not_converged`/`n_warm_start` per run; study
   `max_iter`, first-attempt choice; consider reusing the previous solution shifted as warm start.
2. Exclude the evaluated months from the climatology / B0 point (#5) and re-validate absolute CF.
3. Parameterised, code-generated refiner NLP (fixed window size) for a 3-5x refiner speed-up.
4. Switch `fast_filter` on for new runs only; re-validate once (paired, 6 windows).
5. Use CPU-independent solver limits (iteration only) for reproducibility.
