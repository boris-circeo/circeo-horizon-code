# S3 independent review notes (no src edits made)

1. BETA loader: AWS identity holds to 2e-5 m/s (Psi = TWA OK). Exact at native nodes when axes = native
   (max err 1.2e-4 kW, feasibility mask identical). Default grid is NOT on native nodes (psi step 180/179 deg,
   U step 0.2724), so "exact" is only testable with native axes. Repair: 9078 of 23709 NaN filled; 38 filled
   nodes lie above the row's max feasible U (all inter-TWS block repair at U>=7.6 m/s, 0.3 %). Bug mask is
   applied before repair and re-applied after; regridded boundary row TWA=135 / U=2.5 is feasible via
   nearest-unmasked-node (legit data, 1-cell edge effect). Below 10 kn: P<=0 everywhere, 75 % strictly
   negative, 25 % exactly 0 (positive part scaled to zero). Envelope: reward >= direct (min diff 0.0);
   removing the mask raises hold power at 20 kn from 2461 to 2745 kW => masked nodes are not used.
   Residual: v=0 hold envelope 2.46 MW at 20 kn comes from mixed tacks on non-masked nodes.
2. ERA5: cache cells equal raw GRIB bilinear u/v to 1e-6 (5 cells, hour 100 = 5 Jan 04 UTC); month-boundary
   step diff 0.536 vs 0.496 typical; `outside` identical to index-space outside (26.4 %).
3. Forecast model: determinism and control independence of n_members/seed_offset verified. Control/mean RMSE
   ratio 1.25-1.64 (theory 1.38), rank-hist bins within ~+-20 % of flat (small sample). Exchangeability is
   only approximate (d depends on w). Structural exposure: provider._weather is reachable (truth), and
   forecasts of earlier issue times have independent errors, so averaging past issues would converge to
   truth. No shipped policy does either (all use issue_s = t).
4. FeasiblePowerModel books power at a slowed velocity while the ship moves at full speed: not conservative in
   principle (optimistic, esp. upwind), but clamped_power_steps = 0 in 33 of 34 reported runs (4 steps once).
   Coast/outside: ctx.coast = sdf(land | outside) shared by DP, refiner, sim.
5. Refined > Oracle(3 h DP): 2015-02-15 first 2 days, Oracle_REF (truth) gains +27.9 MWh over Oracle,
   B1c_REF +16.8 MWh; REF policies with very different forecasts gain the same ~9 MWh on day 1 -> discretisation.
6. Regression tests (refine coast, dense sampling, dp macro coast) pass. outputs/S3_results.json (14:59)
   predates the coast fixes (15:01-15:02): 108 violations, min SDF 16.98 km.
