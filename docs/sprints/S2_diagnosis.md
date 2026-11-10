# S2 diagnosis: why the ensemble DP does not beat B1_5d

Scripts: `scripts/diag_s2/` (h1_identity, h2_skill, h3_horizon, h4_optimism, h4_fields). No source change (no bug found).
Setup of H3/H5: 10-day missions, seeds 101-103, horizons NOT truncated at mission end (wrapper), 12 members, k=6, 6 h replans.

## H1 bug check: PASS
All members = control, gamma 0, 10 d horizon (trunk 48 h) vs DeterministicMPC 10 d, at t = 0, 6 h, 3 d, 5 d: trunk identical (max |dx|,|dy| = 0 m) and planned value identical. Machinery (scenario DPs, aggregation, trunk DP with terminal v_bar) is correct.

## H2 synthetic ensemble: calibrated but carries no mean information
Wind-vector RMSE [m/s] (control / ens mean / spread): D1 2.43/2.55/2.38, D3 3.25/3.26/3.00, D5 3.85/3.91/4.03, D7 4.23/4.50/4.28, D10 4.80/5.10/4.35.
Mean is never better than control (real EPS: mean clearly better beyond ~D3). Spread-skill ~1; truth lies in the 12-member speed envelope 0.84 (D3), 0.88 (D5), 0.83 (D7) vs 0.85 expected. Rank histograms (speed) are roughly flat with a mild excess of truth at low ranks (members slightly windier; 0.10 vs 0.077 expected in the lowest ranks at D3/D7). Cause: members are built as control + independent perturbation, truth as control - eps_c (equal variance): the control is the exact centre of the distribution, members are individually worse than the control (sqrt2 sigma) and the mean is only as good as the control. So the ensemble can only add spread information, never a better centre. Real EPS: control is itself a draw, mean beats it.

## H3 horizon confound: not the explanation
J [MWh], 10 d, seeds 101/102/103: Oracle 580.6/625.2/663.2; B1_5d 417.3/516.1/589.2; B1_15d 465.7/516.4/589.1; ENS 5 d 414.1/491.7/583.4; ENS 15 d 456.8/497.9/595.3.
Regret mean: B1_5d 18.9 %, B1_15d 16.1 %, ENS5d 20.7 %, ENS15d 17.3 %. ENS5d - B1_5d = -11 MWh (3/3 negative); ENS15d - B1_15d = -7 MWh (1/3 positive). At matched horizon the ensemble does not help. (On 10 d windows without end truncation 15 d is not worse than 5 d: the 30 d ranking B1_5d > B1_15d is itself noisy, seed 101 dominates.)

## H4 optimism / information content of v_bar
Predicted value at t0 vs realised energy over the same window (30 d pickles, seeds 101-103, replans t<=15 d): optimism B1_5d +18 %, B1_15d +30.5 %, ENS_g0 +30.1 %, ENS_g03 +26.8 %; corr(pred, realised) 0.70 / 0.47 / 0.46 / 0.44. The ensemble expectation is as optimistic as the control DP: per-scenario clairvoyance beyond 48 h dominates, averaging 6 scenarios does not remove it.
Value-to-go at the 48 h split vs the truth-clairvoyant value-to-go (seed 101, cells within 700 km, t = 2/6/10/14 d), Pearson: control 0.18/0.45/0.04/0.21; v_bar k=6 0.23/0.62/0.09/0.21; v_bar k=12 0.50/0.73/0.19/0.23. The 13-day value map is almost unpredictable cell by cell; the ensemble improves it only moderately, and the argmax-cell loss under truth (15-30 MWh) is unchanged.

## H5 reduction
k=12 (all members) vs k=6, seed 101, 10 d: 455.8 vs 456.8 MWh: no closed-loop effect, although v_bar correlation with the truth value improves with k (above). Medoid noise is not the bottleneck.

## Verdict
Not a bug. Primarily a modelling artefact (control = distribution centre, ensemble mean has zero skill gain, so the ensemble has nothing to add to a deterministic planner) compounded by structural limits of the method (clairvoyant per-scenario value beyond the split, zero terminal; value map beyond ~5 d barely predictable). The genuine part: with this error model the 15 d ensemble gains ~+1.7 % over B1_15d and nothing over a 5 d horizon. S1 note: the CVaR result is untestable when spread does not change the ranking of positions.

## Recommendations for S3 (ranked)
1. Make the forecast-error model realistic before judging ensembles: control as a random draw (error sqrt2 sigma vs members), ensemble mean skill > control beyond D3, ideally real reforecasts (ECMWF ENS/GEFS). Re-run E1 afterwards.
2. Use the ensemble mean/medoid-weighted field (not the control) for the trunk beyond ~D3, or blend by lead.
3. Replace zero terminal value / clairvoyant tail by a learned or climatological V_theta (Annex A.2) so the far horizon is not wait-and-see; shorter scenario horizon (5-7 d) plus terminal value.
4. Keep the refiner (+3 %, 5/5 on ENS); more seeds (>=10) for significance.
5. Do not tune k or CVaR gamma until 1 is done.
