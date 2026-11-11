# Sprint 4: offline value function (E0 hindsight bias, learned V_theta)

Scope: the spec's D2 / E0 work at PoC scale (references by section number only: D2, 4.3, 5.1, 6.4, 6.12, 8.3, 10, Annex A). ERA5 2015 truth, BETA polar, 40 km grid, forecast model v2 (seed 1), 6 h replans, 3 h DP. Code: `src/horizon/value/`, `scripts/value_{collect,e0,train,closedloop}.py`, `tests/test_value.py`. Client-derived caches (`data/cache/value`) and outputs are git-ignored. Figures/JSON: `outputs/value/` (`E0_bias_map.png`, `E0_results.json`, `Vtheta_cv.json/png`, `closedloop_{pol,hind}.json`).

## Data (all causal, one core)

* 119 release times `s_k` = every 3 d of 2015 (day 0 ... 354). At each: (a) `V_hind(x, s_k; H)` for H = 2, 5, 10 d, one backward DP on the TRUTH (zero terminal), all cells at once; (b) 40 B1 ships (DP 5 d on the control forecast, no refiner, 6 h replan) released from random navigable cells and flown for 5 d on the true wind: realised energy at 1..5 d = `V_pol(x, s_k; H)` (the DP of a replan does not depend on the ship, so it is shared across the group: 4760 rollouts for 57 min); (c) forecast feature fields (control forecast issued at `s_k - 5 d`, window `[s_k, s_k + 5 d]`).
* On-track states: positions of `A_B1c_REF_s1/s2`, `A_ENS_REF_s1` at the same `s_k`, realised energy over 2/5/10 d from the segment `power_kw` (347 states; policies with refiner/ensemble, concentrated near the best offshore region).

## E0: hindsight bias `V_hind - V_pol` (mean +/- SE clustered by release time)

| H | B1 rollouts (uniform in space) | year-run tracks |
|---|---|---|
| 2 d | +15.8 +/- 0.4 MWh (+15.8 %) | +9.2 +/- 0.7 MWh (+7.4 %) |
| 5 d | +36.6 +/- 0.9 MWh (+13.1 %) | +23.8 +/- 1.2 MWh (+7.7 %) |
| 10 d | n/a | +49.5 +/- 1.8 MWh (+8.0 %) |

(% of V_hind; V_hind 5 d = 279 MWh vs V_pol 242 MWh on rollouts.) Hindsight is biased HIGH at all horizons and the bias grows roughly linearly with H. The tracks (refined / ensemble policies near the good region) have about 40 % less bias than plain B1 from random cells.

Structure (H = 5 d, rollouts):

* Month: relative bias 9.5 % (Jan, Dec) to 19.4 % (Jul), i.e. low in the energetic winter, high in light-wind summer (tracks: 4.7 % Mar to 9.8 % Oct). Strongly non-uniform in time.
* Space: map `outputs/value/E0_bias_map.png`. Relative bias 11.8 % to 23.5 % over 20 lon/lat blocks (ANOVA F = 6.1, p ~ 1e-15, but eta2 = 2.4 %): lowest in the mid-Atlantic (about 11 %), highest on the North Sea / Norwegian side and in the Mediterranean pocket (18-22 %). In absolute kWh the bias is nearly uniform (30-43 MWh block means; no trend with distance to coast: 36.6 MWh at 20-60 km and 36.2 MWh beyond 600 km; lat bands 35.0-39.0 MWh). So the spec's thesis holds (hindsight biased high; bias not uniform) but at this scale the non-uniformity is mostly seasonal and moderate in space (relative 12-23 %), not a large absolute spatial distortion.
* Bias correlates negatively with the realised value (r = -0.47 with V_pol, -0.15 with V_hind): hindsight over-values cells the policy actually could not exploit.

Caveats: V_pol is for plain B1 (no refiner), a policy that is itself 11.9 % below the hindsight bound in the year runs; the bias therefore mixes forecast error and policy sub-optimality. Rollout bias is larger than on-track bias partly because random cells include poor / coastal starts. H = 10 d only on tracks.

## V_theta (policy-consistent terminal value, H_T = 5 d)

Model: LightGBM mean regression (300 trees, 15 leaves, one thread); target = realised energy over 5 d [kWh]. Features (12): x, y [km], sin/cos day of year, climatological hold power (2015 minus the held-out month), distance to coast, and six forecast features from the control forecast issued 5 d before the decision (window mean hold power, early/late thirds, mean and temporal std of TWS, 7 x 7 smoothed mean hold power). Training rows: 4.4-4.6 k per fold (rollouts + tracks). Leave-one-month-out CV on 2015 with a 5 d buffer on both sides of the held-out month (mask asserted in code and tests). 5021 test states (4680 rollouts, 341 tracks), all evaluated against REALISED energy.

| Model (LOMO) | R2 | MAE [MWh] | bias [MWh] | within-release R2 |
|---|---|---|---|---|
| clim terminal, raw (P_clim x 120 h) | -1.45 | 85.1 | -77.8 | 0.21 |
| clim, linearly recalibrated | 0.06 | 50.5 | +1.8 | 0.24 |
| hindsight-trained (same rows) | 0.09 | 47.6 | +39.4 | 0.40 |
| hindsight-trained (+150 cells/release) | 0.08 | 47.9 | +39.5 | 0.40 |
| **V_theta (policy-consistent)** | **0.44** | **37.3** | +3.8 | 0.38 |
| V_theta without forecast features | 0.26 | 42.8 | +4.7 | 0.18 |

(rollout rows; all rows similar: 0.44 / 37.1 MWh.) On the 341 on-track states all models do poorly (R2 <= 0.08): tracks sit in a narrow good-wind region (little variance) and the refined / ensemble policies beat the B1-dominated training target (V_theta bias -16 MWh there).

Reading: (i) V_theta is far better calibrated than the climatological terminal (hold power is about 3x below the energy a moving ship harvests) and than the hindsight-trained model, whose level is biased by +39 MWh (the E0 bias, inherited). (ii) The hindsight model fits its own target (R2 0.55 vs V_hind) but not the realised outcome. (iii) The spatial ranking within one release time (within-release R2) is the same for the hindsight and the policy-consistent model (0.40 vs 0.38) and much better than climatology (0.24): the "better generalisation" of the policy-consistent target is a LEVEL / calibration effect here; for a DP terminal value a constant offset is irrelevant, so the routing-relevant benefit is not demonstrated by the CV. (iv) Forecast features matter (R2 0.26 to 0.44; smoothed forecast hold power is the top gain feature, 33 %, followed by day of year, x, fc_tws).

## Closed loop: B1v_5d_REF vs B1c_5d_REF (30 d, seed 1, leave-month-out models)

Start = B1c year-run position at the month start; both policies use the climatology without the test month and the same forecasts (epoch = month start, so values differ from the year-run months); V_theta evaluated on the grid at `t + 5 d` from the forecast issued at `t` (10 d, 6 h control member), scaled down near the segment end like the climatological terminal. 0 guard interventions, 0 coast violations, 0 DP fallbacks.

| Month | B1c CF | B1v (policy-consistent) | dCF | B1v (hindsight-trained) | dCF |
|---|---|---|---|---|---|
| March | 0.863 | 0.865 | +0.002 | 0.865 | +0.001 |
| July | 0.643 | 0.656 | +0.013 | 0.656 | +0.012 |
| October | 0.787 | 0.791 | +0.004 | 0.787 | +0.000 |
| mean | 0.764 | 0.771 | **+0.006** (+13.6 MWh/month; +4.3, +27.2, +9.3) | 0.769 | +0.004 |

3/3 months positive for the policy-consistent model; the effect is small (+0.6 CF points, about +0.8 %) and the sample is three months with one forecast seed: not significant, and the hindsight-trained terminal gives nearly the same gain (consistent with the equal within-release ranking above). Wall time +5-35 % (extra 10 d forecast and a 6.5 k-cell prediction per replan, about 0.1 s).

## Limitations

* One year, one forecast seed, forecasts are the perturbation model (not NWP); targets and the closed loop share ERA5 2015 (LOMO removes only same-month leakage: neighbouring months and the same weather regime remain; the 5 d buffer removes window overlap).
* V_pol targets come from plain B1 rollouts, not from the policy in which V_theta is finally used (B1 + refiner + V_theta): not a fixed point of the policy-consistent iteration (spec 6.12); a second iteration (re-collect with B1v) was not done.
* E0 bias mixes forecast error and sub-optimality of the policy; H = 10 d only on tracks; hindsight uses zero terminal value.
* Within-release ranking, not level, is what a DP needs; CV R2 therefore overstates the routing benefit of policy-consistent targets.
* Mean regression only (quantile fitting is implemented, `fit_value_model(quantile=q)`, untested closed loop); no ensemble features (control forecast only); region/month effects are partly absorbed by day-of-year and position features.
* LightGBM (MIT) is an optional dependency (`value` extra, `docs/LICENSES.md`).

## Review note (independent review, 2026-11-11)

E0 compares the 3 h DP model value (V_hind) with energy realised on 15 min chords (V_pol). Executing
the hindsight DP plan on the truth (16 cells × 4 dates, H = 5 d) realises 97.4 % of its predicted value,
so about 6 of the 36.6 MWh rollout bias (~17 %) is DP discretisation, not forecast error or policy
sub-optimality. The remaining hindsight bias (~+11 % at 5 d) is still substantial and seasonal.
