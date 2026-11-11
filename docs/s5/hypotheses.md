# HORIZON S5 / WP1 - Hypothesis register and experiment plan

*Registre d'hypothèses et plan d'expériences - v1 design note DES-860 rev A (confidentiel, propriété du client; paraphrases uniquement) et notre propre environnement de test.*

Companion file: `docs/s5/hypotheses.yaml` (119 entries; ids `H-<chapter>-<n>`, `H-X-*` = hypotheses about OUR environment). Sources: v1 note, S0-S4 reviews/results, `docs/CONVENTIONS.md`. A few small computations were done during the review (ERA5 2015 cache on the 40 km grid, BETA polar aggregates): seasonal wind of the reference zone, polar shape/knee, Jensen ratio on the reduced polar, first-72 h power of the Lorient departures; they are marked 'S5 computation' in the register.

## 1. Counts / Décompte

| | high | medium | low | total |
|---|---|---|---|---|
| algorithm-choice | 6 | 14 | 0 | 20 |
| discretisation | 1 | 6 | 1 | 8 |
| fleet | 1 | 5 | 3 | 9 |
| forecast | 7 | 6 | 1 | 14 |
| numerics | 0 | 2 | 7 | 9 |
| operations | 7 | 11 | 2 | 20 |
| problem-structure | 3 | 1 | 0 | 4 |
| risk | 1 | 2 | 0 | 3 |
| ship/polar | 2 | 9 | 2 | 13 |
| value-function | 7 | 4 | 0 | 11 |
| weather | 1 | 7 | 0 | 8 |
| **total** | **36** | **67** | **16** | **119** |

Status: open 69, contradicted-by-S0-S4 23, supported-by-S0-S4 12, untestable-here 15. Type: assumption 47, quantitative-claim 39, design-decision 21, dismissed-alternative 12. Test cost: cheap 52, medium 56, expensive 11.

Reading rules / règles de lecture: 'contradicted' means contradicted by what S0-S4 (or the S5 arithmetic/computations) show **in our test environment**; several 'contradicted' items (ensemble value, 2-layer claim, hindsight terminal) depend on our forecast law and have weak statistical power (section 6); they are flagged as such and are re-tested in section 5.

## 2. Top 20 high-criticality items / Les 20 points les plus critiques

1. **H-X-1** (forecast, open, medium) - Forecast = perturbed truth keeps true storm structure at all leads: may inflate long horizons/ensembles.  
   *FR:* Les prévisions sont la vérité perturbée : elles conservent la structure réelle des dépressions à toute échéance.
2. **H-2-22** (forecast, open, expensive) - Forecast error law (RMSE, timing, skill horizon) is hypothesised, never fitted to real forecasts; everything on horizon/ensemble/latency inherits it.  
   *FR:* La loi d'erreur de prévision n'est jamais calée sur de vraies prévisions.
3. **H-4-12** (forecast, contradicted-by-S0-S4, medium) - Ensemble scenarios 'mandatory beyond D2': measured gain +0.65 to +1.4 % (n.s.), single forecast seed.  
   *FR:* Valeur de l'ensemble : +0,65 à +1,4 % non significatif.
4. **H-4-13** (algorithm-choice, open, cheap) - Dismissed ensemble-mean field never tested; mean beats control by x1.38 in our model, so ENS-vs-B1 gain may be 'mean beats control'.  
   *FR:* Moyenne d'ensemble jamais testée ; le gain ENS/B1 peut n'être que 'moyenne > contrôle'.
5. **H-4-14** (algorithm-choice, contradicted-by-S0-S4, cheap) - Two-stage trunk is called conservative; logic and S2 data (optimism +30 %) say optimistic.  
   *FR:* Le two-stage est dit conservateur ; il est en fait optimiste.
6. **H-2-25** (forecast, untestable-here, medium) - Spread-skill (flow-dependent confidence) cannot appear in our forecast model: structural blind spot for adaptive k and CVaR.  
   *FR:* Le spread n'a pas de contenu dépendant du régime dans notre modèle.
7. **H-3-3** (value-function, contradicted-by-S0-S4, medium) - EVPI claimed 15-40 %; we measure 3-12 % against an approximate bound.  
   *FR:* EVPI annoncée 15-40 % ; mesuré 3-12 % (borne approchée).
8. **H-8-6** (problem-structure, contradicted-by-S0-S4, medium) - Hindsight DP is not a strict upper bound (3 h DP beaten by refined policies by up to 3.9 %); Oracle_REF_H is approximate: all regrets inherit this.  
   *FR:* L'oracle n'est pas une borne stricte ; tous les regrets en héritent.
9. **H-4-8** (value-function, contradicted-by-S0-S4, medium) - Policy-consistent V as an architectural pillar: V_theta +0.6 pt vs hindsight-trained +0.4 pt vs clim +2.8 % (all n.s.).  
   *FR:* V policy-consistent : gain non démontré par rapport à la climatologie ou au hindsight.
10. **H-4-1** (algorithm-choice, open, medium) - Two-layer claim: the offline layer's added value over a single online DP with climatological terminal is unproven (0.797 vs 0.807 CF).  
   *FR:* Valeur de la couche offline non démontrée.
11. **H-4-30** (operations, open, medium) - Manoeuvre cost (4-15 % hold loss) never charged by the simulator; B0 (97 % holding) and routed ships affected unequally.  
   *FR:* Coût de manoeuvre jamais facturé par le simulateur.
12. **H-9-1** (risk, open, medium) - No survival/storm constraint in the PoC and no derating in BETA up to 50 kn: CF 0.80 may include storm time.  
   *FR:* Aucune contrainte de survie dans le PoC ; la polaire ne plafonne pas jusqu'à 50 kn.
13. **H-2-4** (ship/polar, contradicted-by-S0-S4, cheap) - Narrow-optimum / beam-reach narrative contradicted by BETA (P(45)~0, plateau wide above 22 kn).  
   *FR:* Le récit 'optimum étroit au travers' est contredit par BETA.
14. **H-6-3** (discretisation, contradicted-by-S0-S4, medium) - Numerical (grid/stencil) error 'fractions of a percent': measured 3-7 % (orientation 6 %, refiner +3-7 %, E0 3 %).  
   *FR:* L'erreur numérique mesurée est de 3 à 7 %, pas 0,x %.
15. **H-4-26** (operations, contradicted-by-S0-S4, cheap) - '~60 independent winters' vs 20 (GEFS) / 45 (ERA5) / 1 (ours): most effects are below v1's own 2-3 % detectability.  
   *FR:* Puissance statistique : la plupart des effets sont sous le seuil 2-3 %.
16. **H-5-1** (value-function, open, expensive) - Offline training on 5-member GEFS reforecasts vs online 51-member ENS (k=6-8 > 5): information set mismatch breaks policy-consistency.  
   *FR:* Reforecast 5 membres vs ENS 51 : l'information offline n'est pas celle de l'online.
17. **H-8-3** (operations, open, cheap) - Simple heuristics ('go to max smoothed forecast hold power') never tried; could capture much of the 40 % routing gain.  
   *FR:* Heuristiques simples jamais testées.
18. **H-2-23** (forecast, open, medium) - Useful horizon D5-6 deterministic / D8-10 probabilistic: no horizon sweep on ERA5; built into our error law.  
   *FR:* Pas de balayage d'horizon sur ERA5.
19. **H-2-9** (ship/polar, open, medium) - Jensen argument: sign flips at ~18 kn (+19 % at 14 kn, -15 % at 20 kn, sd 4 kn); effect on position RANKING untested.  
   *FR:* Jensen : signe vérifié sur BETA, impact sur le classement des positions non testé.
20. **H-4-35** (fleet, contradicted-by-S0-S4, cheap) - Recall field lambda: arithmetic error in v1 (bracket 1100 not 2100 kW; 4.2 not 10.5 kWh/NM/h) and g_out 500 kW vs 1.54 MW measured.  
   *FR:* Champ de rappel lambda : erreur de calcul (facteur 2,5) et g_out 500 kW vs 1,54 MW mesuré.

Other high items: H-1-1, H-1-2, H-2-2, H-2-24, H-2-26, H-3-6, H-4-10, H-4-2, H-4-4, H-4-6, H-4-7, H-4-9, H-8-1, H-X-5, H-X-6, H-X-7.

## 3. Already contradicted or qualified by S0-S4 / Déjà contredits ou nuancés

| id | v1 claim (paraphrase) | what S0-S4 / S5 showed | note |
|---|---|---|---|
| H-1-4 | Surplus compute should buy ensemble width, never spatial/temporal resolution; numerical error is a fraction of a percent, negligible agains… | S1: stencil quantisation gives ~6 % orientation dependence; S3: macro arcs (K=21->49) cured 'square tracks'; refiner (continuous heading, 30 min) = +3.2 % (S2), +6.6 % (S3, 10/10); E0 review: ~17 % of the 5 d hindsight bias is DP… | Resolution matters at the 3-7 % level here, larger than the ensemble gain we could measure (+1.2 %). Partly b… |
| H-2-4 | The optimum is sharp and narrow: >2400 kW only at beam reach TWA 75-105 deg, P(45 deg) = P(90 deg)/3-4, half-width +-20-25 deg, a 30 deg er… | BETA (S3, plot_beta_polar; re-checked in S5): at 20 kn peak 2756 kW at TWA 95; P(45)~0 (not 1/3); P>=0.9 peak only 88-105; P>=0.5 peak 70-135 (asymmetric). Above 24 kn the plateau widens (26 kn: >=0.9 peak at 88-140 deg; 35 kn: 8… | Narrow only below ~22 kn; in strong wind most of the downwind half-plane is productive (S3 finding 3). The 'b… |
| H-2-5 | Peak power is ~1500 kW at 18 kn, 2100 at 20, >2700 at 22, cubic in TWS (~15 %/kn); the 3 MW plateau starts around 24-26 kn. | BETA: 2008 kW at 18 kn, 2756 at 20, 2986 at 22, 2984 flat to 50 kn (S5 re-computation). Cubic confirmed (14->20 kn exponent 3.0); gain 17 %/kn at 18-20 kn, 26 %/kn at 12-14 kn; knee at 21-22 kn not 24-26. | Real band is '>= ~21 kn' not '18-26 kn': stronger wind is free energy (plateau) and the interesting regime is… |
| H-2-6 | Net power is negative up close to the wind (down to -300 kW), so upwind repositioning has an explicit energy price. | BETA: max-over-U power at TWA<=45 deg is -1 to -43 kW (about zero), but individual (TWA, U) nodes reach -3500 kW (PolarTable bounds must be (-3500, 3000)); beam reach at U=8 m/s already -800 kW. Hence the price is lost production… | A ship that slows down is never forced into the -3 MW nodes; the 'explicit price' is the opportunity cost of… |
| H-2-11 | TWA = arccos(W.U/|W||U|) with W in the 'toward' convention. | S0: gives 0 deg for downwind, an error of 180 deg versus the polar convention (0 = head to wind); code uses arccos(-W.e/|W|). BETA files confirm Psi = TWA via AWS^2 = TWS^2+U^2+2 TWS U cos(Psi) (S3). | A literal implementation would swap upwind and downwind - catastrophic but already neutralised. |
| H-2-14 | At high wind the polar derates or cuts out ('bridage par vent fort' in the figure; synthetic polar: derating from 35 kn, cut-out 42 kn). | BETA (real data) already includes the generator limit and shows no derating: 2.95-2.99 MW from 22 to 50 kn at the best TWA (client: no overlay; CONVENTIONS 6). Cut-out/derating exist only in our synthetic polar (S0). | If the real ship does derate above 35-40 kn, routers tuned on BETA overvalue storm sectors. |
| H-2-16 | The natural harvesting zone is 42-55N / 10-35W and the best fixed point is near 48-52N / 12-18W. | S4: annual best offshore point of 2015 is 56.5N 21.6W (~849 NM from Lorient), S1 synthetic gave 46.7N 2.8W; ERA5 box here is 32W-5E / 38-65N (v1 basin 45W-5E / 30-60N), so the western boundary at 32W and the northern one at 65N b… | One year; box truncated vs v1; 'best point' depends on the polar (plateau above 21 kn favours windier norther… |
| H-3-3 | The expected value of perfect information is of the order of 15-40 % of total energy. | Best causal ENS_REF is 8.3 % below the approximate bound over 2015 (S4); S3 3.4-5.7 % (30 d, ERA5); synthetic S1/S2 10-13 %. Bound is approximate (15 d lookahead + clim terminal), so true EVPI is >= these. | Small EVPI because the BETA plateau makes the ship insensitive to timing (CF 0.88 even for hindsight). Direct… |
| H-3-9 | A small CVaR weight gamma is justified by under-sampled tails, asymmetric constraints and set-point chattering damping. | S2 (synthetic, gamma 0.3, alpha 0.2): -11 MWh mean, no tail benefit (worst seed 1362 vs 1378). S3/S4 use gamma = 0 only. | Untestable without flow-dependent spread or a risk event; current evidence is vacuous. |
| H-4-7 | The clairvoyance bias is spatially heterogeneous (high in the storm-track core, low in calms) and therefore deforms the policy. | S4_value: relative bias 11.8-23.5 % over 20 blocks but absolute bias 30-43 MWh almost uniform, no trend with distance to coast; ANOVA eta2 = 2.4 %. v1's own E0 criterion ('small and homogeneous -> constant-factor hindsight') is p… | The decisive closed-loop comparison (+0.4 vs +0.6 pt, n=3) is too small to conclude. |
| H-4-8 | Using hindsight values as terminal is an error of nature; only a policy-consistent learned value gives unbiased arbitrages. | Closed loop on 3 months: B1v policy-consistent +0.6 CF pt, hindsight-trained +0.4 pt vs B1c (both n.s.); equal within-release ranking R2; V_theta has level bias +3.8 MWh vs +39.4 MWh for hindsight but a DP is level-blind (S4_valu… | Low power (3 months, 1 seed). Level calibration matters when comparing against the terminal at +48 h/5 d with… |
| H-4-10 | A raw climatological terminal ignores corridor geometry and optionality and should only be an embedded fallback. | S4: climatological hold-power terminal = +2.8 % (10/12 months, t=2.6) over zero terminal; V_theta adds +0.6 pt on top (n.s.). Raw clim level is biased -78 MWh (hold power ~3x below harvest) but recalibrated clim has R2 0.06 vs V_… | Climatology is from 2015 itself (leakage, see H-X-3): its +2.8 % may be overstated. |
| H-4-12 | Representing uncertainty by 6-8 scenarios with a CVaR aggregator clearly outperforms deterministic MPC. | S2 synthetic: ENS_g0 +1.7 % vs B1_15d (3/5), no gain vs B1_5d. S3 (6 missions): +66 MWh without refiner (+3.9 %, 5/6), +26 MWh with refiner (+1.4 %), +12 MWh matched with clim terminal (+0.65 %, 4/6). S4 year: ENS_REF vs B1c +1.2… | Ensemble gain depends on our forecast law (S2 showed an uninformative law kills it); gain may be under- or ov… |
| H-4-14 | The two-stage approximation (48 h common trunk, free recourse per scenario) is conservative because it ignores future information branches. | Logic: recourse after T_b is a relaxation (each scenario knows its own future), hence optimistic for maximisation. S2 diag H4: plan optimism +30 % for ENS (as large as B1_15d) due to per-scenario clairvoyance beyond 48 h; corr(pr… | v1's reasoning is inverted: two-stage over-values flexibility; the trunk length drives aggressiveness. |
| H-4-21 | The stencil has about 55 neighbours for 45 km cells, 3 h steps and U_max = 8 m/s (coprime offsets within 3 cells). | S1: U_max dt = 86 km = 2.2 cells at 40 km, so a 3-cell radius is unreachable: K=21 (angular gaps up to 26.6 deg, ~6 % orientation dependence); S3 macro arcs spanning 1-2 steps: K=49, worst gap 18.4 deg. | Also 6.1.2 uses ~30 neighbours in the fine zone vs 55 in 4.6.3 (internal inconsistency). |
| H-4-26 | There are about 60 independent winters (60-100 effective samples) for training and validating the value model. | Internal inconsistency in v1: GEFS reforecast 2000-2019 gives 20 winters, ERA5 1979+ gives ~45. We have exactly 1 year (12 correlated months). A difference below 2-3 % is 'not significant' by v1's own rule: ENS +1.2 %, V_theta +0… | Most open questions are below detectability with our data. |
| H-4-35 | lambda(d) ~ 25/(T_cyc v_eff) [2 g_core - g_out - g_in] = 10-11 kWh per NM per hour, i.e. ~0.7 % of core gain per 100 NM. | Arithmetic (S5 review): with g_core = 1500, g_out = 500, g_in = 1400 kW the bracket is 1100 kW (not 2100), so lambda = 25/(1080 h x 6 kn) x 1100 = 4.2 kWh/NM/h; relative to the core's 21 x 1500 kW it is 1.3 %/100 NM; v1's 0.7 % m… | The result steers the recall strength: a factor 2.5 error. |
| H-4-36 | Outbound legs average ~500 kW (upwind), inbound ~1400 kW, core 1500 kW. | S4 Exp. B (free routing from Lorient, 14 d, B1c): mean first 72 h = 1.54 MW (0.43-2.31 per month), later 2.30 MW, 14 d mean 2.1 MW; t(50 km) ~4-5 h. At-sea year: 2.39 MW avg. Not constrained to reach a moving fleet. | g_core 1500 kW is also low vs measured 2.4 MW (CF 0.8). |
| H-4-38 | With turnaround 1-2 d and a rotation every 1.8 d (25 ships / 45 d) the quay is 60-100 % occupied; target 75-85 %. | Arithmetic: 2 d / 1.8 d = 111 % > 100 %; 1 d gives 56 %. 'Saturated' (4.13.1) and 'target 75-85 %' (9.6) are in tension; 3-5 ships in transit = 12-20 % OK. | Operations-only. |
| H-5-2 | One policy-iteration pass is 1e4-1e5 simulated missions (~5000 in Annex B), at 3-10 min each, i.e. 'a few hundred' to 1500 core-hours. | Internal inconsistency (5000 x 3-10 min = 250-830 core-h; 1e5 x 10 min = 17 000 core-h). Measured: B1c_5d_REF 30 d mission ~5 min CPU, ENS_REF ~30 min CPU; V collect 4760 shared B1 rollouts in 57 min. | With ENS+REF the training set costs ~6x more than v1's estimate. |
| H-6-3 | DP error from space/time/heading quantisation is a fraction of a percent and is dwarfed by forecast error. | Measured effects are several percent: 6 % orientation dependence (S1), 3 % of V from discretisation (E0 review: DP plan realises 97.4 % of V_dp), refiner +3-7 %, Oracle_REF - Oracle = +47-75 MWh/30 d (S3). | If true, the 'forecast is everything' priority is partly wrong at 40 km/3 h. |
| H-8-2 | B1 (5 d deterministic MPC, zero terminal) is the baseline that quantifies the value of the whole long-term structure. | B1_5d is itself anticipative: regret 11.5 % (S3) / 11.9 % (S4); the long-term structure (terminal, ENS) adds only +2.8 % (clim) and +1.2 % (ENS) on top. | - |
| H-8-6 | A hindsight DP on the realised weather is an upper bound for any causal policy. | S3: Oracle (3 h DP) beaten by REF policies by up to 3.9 %; J_hind := max(Oracle, Oracle_REF); S4 Oracle_REF_H is a 15 d lookahead + clim terminal bound, 'approximate'. Margins of causal runs to it are 280-360 MWh in the worst mon… | All regrets are relative to this bound. |

Specific items asked for: S0 TWA formula (H-2-11); polar shape vs BETA (H-2-4, H-2-5, H-2-6); '~55 neighbours' (H-4-21); cut-out/derating (H-2-14); beam-reach narrative vs real polar (H-2-4); ensemble value (H-4-12); 2-layer claim (H-4-1, status open but weakly supported); hindsight bias (H-4-6 supported in level, H-4-7/H-4-8 contradicted in spatial structure and closed-loop consequence); two-stage 'conservative' (H-4-14); EVPI (H-3-3); lambda arithmetic (H-4-35); '60 winters' (H-4-26).

### Supported / à peu près confirmés
- **H-1-2** - Routing must beat the best fixed 'virtual mooring' B0 by a wide margin; if the gap is small the whole project is oversized (to be tested first).
- **H-2-7** - Production needs ship motion (optimum at 6-9 kn): a nearly stopped ship produces almost nothing and cannot hold position; hold = beam-reach tacks wit…
- **H-2-17** - Mean 10 m wind in the reference zone (48-52N, 12-20W): DJF 20-24 kn, MAM 16-20, JJA 11-15, SON 16-22.
- **H-3-1** - Weather is exogenous, so the problem is an MDP without action-observation coupling and the forecast/replan MPC decomposition loses little in theory.
- **H-3-6** - Decisions depend on V only through differences/gradients; a level-accurate but gradient-wrong V is useless.
- **H-4-4** - A continuous refiner on 0-48 h consuming the strategic value field as terminal adds more than 1 %.
- **H-4-6** - Hindsight value V_hind is biased high versus a causal policy's realised value; the bias grows with the horizon and is not uniform.
- **H-4-29** - The refiner uses ~96 steps (30 min over 48 h), exact derivatives, C2 splines and converges in under 1-3 s when warm-started.
- **H-5-7** - ENS cycles arrive 5-7 h late, so each replan uses the previous cycle.
- **H-6-2** - The compiled kernel handles 2-5e8 arcs/s on 16 cores (about 3-6 ns per arc, memory-bound).
- **H-6-11** - Without a hold arc corrected for manoeuvres and drift the DP over-immobilises the ship; the 1D curve captures the correction.
- **H-8-5** - Four physical unit tests (uniform wind racetrack to +-1 %, advected toy front, constant invariance, rank conservation under grid refinement) validate…

### v1 internal inconsistencies found / incohérences internes de v1
- lambda(d) arithmetic: bracket 2100 kW should be 1100 kW; 10-11 kWh/NM/h should be ~4.2; '0.7 %/100 NM' matches neither (H-4-35).
- Neighbours: ~55 (4.6.3, 6.1.1, 6.11) vs ~30 in the fine zone (6.1.2) vs U_max dt = 2.2 cells at 40 km (H-4-21).
- Winters: 'about sixty' (4.8) vs GEFS reforecast 2000-2019 = 20 winters (H-4-26).
- Offline cost: 1e4-1e5 missions per iteration (5.2.1) vs ~5000 (B.1) vs 'few hundred core-hours' vs 600-1500 core-h (H-5-2).
- Quay occupancy 60-100 % with 1-2 d turnaround (up to 111 %) vs target 75-85 % (H-4-38).
- Hard ban at survival limits (4.9, 9.1) vs penalty instead of ban at 45 kn (6.1.1) (H-9-1).
- Two-stage called conservative but relaxes nonanticipativity after T_b (H-4-14).
- Polar: peak width +-20-25 deg and P(45)=P(90)/3-4 and flat top +-10-15 deg are mutually inconsistent (S0), and none matches BETA (H-2-4).
- Reforecast has 5 members, operation clusters 51 members into 6-8 medoids (k>N offline) (H-5-1).

## 4. Dismissed alternatives worth re-testing / Alternatives écartées à retester

| id | alternative (v1 verdict) | why it may deserve a test | priority | experiment |
|---|---|---|---|---|
| H-4-13 | Ensemble-mean field / lead-blended deterministic (dismissed: smoothed) | cheapest way to separate 'scenarios' from 'better centre'; our control is a draw, mean is x1.38 better | 1 | E-11, E-02 |
| H-8-3 | Simple heuristics: go to max (smoothed) forecast wind / hold-power in reach; monthly best point + drift | V_theta's top feature is exactly smoothed forecast hold power; 20-line router as new baseline | 1 | E-12, E-15 |
| H-4-3 | Myopic 24-48 h horizon, zero terminal (v1 B1 is 5 d) | true value of anticipation unknown; B1 already anticipative | 1 | E-04 |
| H-4-7 | Hindsight terminal with seasonal/constant correction (v1 E0 fallback) | E0 bias nearly uniform in absolute terms, seasonal; hindsight-trained gave +0.4 vs +0.6 pt | 1 | E-08 |
| H-4-10 | Raw / recalibrated climatological terminal vs learned V | clim terminal +2.8 %, V_theta +0.6 pt n.s.; single online layer may be enough | 1 | E-04, E-08, E-18 |
| H-4-19 | A* / Dijkstra forward search with weak bound | moot for cost (DP 0.5 s) but evaluators will ask; useful as independent check of DP optimum | 3 | E-12 |
| H-6-4 / H-3-7 | Isochrones / front propagation / fast marching (energy-stratified) | external credibility baseline; also tests whether forward label methods are competitive for a single ship | 2 | E-12 |
| H-4-20 | RL / learned policy (dismissed: opaque, sample-hungry) | environment is a free simulator; a distilled GBDT policy could be a cheap fallback (H-9-3) | 3 | E-12 |
| H-4-9 / H-4-1 | Single layer: long-horizon ENS DP with climatological terminal (no learned V) | H-4-1: matches 98 % of full stack in S4 | 1 | E-04, E-08, E-12 |
| H-4-31 / H-4-23 | Tack-state fine DP (D10) / 10 km-1 h fine zone vs envelope hold + refiner | never built; refiner gain may only compensate coarse DP | 2 | E-06, E-07, E-09 |
| H-4-5 / H-4-41 | Refiner with imposed waypoint vs value-field terminal (v1 B2 variant) | tests the 'interface by value' dogma cheaply | 2 | E-06 |
| H-6-6 | Two-branching scenario tree instead of two-stage trunk | two-stage is optimistic (H-4-14); tree might correct it | 2 | E-11 |
| H-4-13 (variant) | Per-member DP, then average VALUES (not routes) with no common trunk | v1's objection targets averaging routes, not values | 3 | E-11 |
| H-3-9 | Pure expectation (gamma=0) vs CVaR on real data with a safety metric | only gamma=0 run on ERA5 | 2 | E-11, E-17 |
| H-4-16 | Random / k-means / scalar-index scenario selection vs vector-EOF medoids | reduction is claimed non-critical (S2 H5); verify on ERA5 | 3 | E-11 |
| H-9-3 | Fallback greedy policy climbing climatological V without forecast | defines degraded-mode performance | 3 | E-12 |
| H-8-2 | Myopic baseline definition | B1 is not myopic: all long-term-structure gains are measured against a baseline that already anticipates 5 d | 2 | E-04 |

## 5. Proposed experiment list / Liste d'expériences proposées

**Common protocol.** *bench-6* = six 30 d windows of 2015 (1 Jan, 1 Mar, 1 May, 1 Jul, 1 Sep, 1 Nov) from the annual best offshore point (56.5N 21.6W) unless the factor says otherwise. Routers: **R0** = B0 best fixed point; **R1** = B1c_5d_REF (control forecast, 5 d DP, climatological terminal, refiner); **R2** = ENS_REF (20 members, 10 d, k=6, gamma 0, trunk 48 h, refiner); **R3** = Oracle_REF_H (bound). Metric = mean capacity factor over windows [CF points], paired differences vs R1 and gap to R3 [points]; >= 3 forecast seeds for every forecast-dependent factor; weekly-block bootstrap CI (E-23). Full persistent year (12 months) only for finalists. 'Confirm / refute' thresholds are indicative detectability levels: with bench-6 (n=6 paired, 3 seeds) differences below ~0.8 CF pt (~1 %) are noise.

| id | experiment | factors and levels | routers | metric | confirm / refute rule | hypotheses covered | cost |
|---|---|---|---|---|---|---|---|
| E-01 | Forecast error scale | scale s on displacement, amplitude and noise = {0 (perfect), 0.5, 1, 1.5, 2, 3}; 3 seeds | R1, R2 (R3 fixed) | CF(R1), CF(R2), gap R2-R1 vs s; EVPI(s) = R3 - CF(R1) | Confirm D3 if R2-R1 grows monotonically to >= +2 pt at s >= 2 and stays >= +1 pt at s = 1; refute if |R2-R1| < 0.5 pt for all s (ensemble useless). s -> 0 gives the achievable regret floor. | H-2-22, H-2-24, H-3-3, H-4-12, H-5-6, H-X-1 | medium |
| E-02 | Forecast-model structure (artefact hunt) | (a) flow-dependent spread on/off; (b) control-vs-mean RMSE ratio g = {1.0, 1.15, 1.38, 1.6}; (c) structure retention: for leads >= 5 d replace the displaced-truth by blend alpha = {0, 0.5, 1} with an analog field (other-month ERA5 of same season); (d) seasonal amplitude {-15, 0, +15, +30} %; (e) issue consistency {legacy, v2, stronger} | R1, R2 at 5 d and 10 d | R2-R1 gap and R1(10 d)-R1(5 d) gap vs each factor | If (c) with alpha=1 erases the ensemble gain and the 10 d gain, the S3/S4 horizon/ensemble results were artefacts of truth retention; if (a) restores a gain via adaptive k/gamma, spread-skill value is real but invisible today. | H-X-1, H-X-2, H-X-10, H-2-24, H-2-25, H-2-27, H-4-12 | medium |
| E-03 | Latency and cycle interval | ENS latency {0, 3, 6, 9, 12} h; control latency {0, 2, 4, 6} h; cycle interval {6, 12, 24} h | R1, R2 | CF loss per hour of latency | S4 integration check: -2 % at 6 h. Confirm linear ~ -0.3 pt/h; refute if <0.1 pt/h (cycle availability not critical). | H-5-7 | cheap |
| E-04 | Horizon x terminal ladder | DP horizon {1, 2, 3, 5, 7, 10, 15} d x terminal {0, clim x1, x2, x3, V_theta, oracle V from truth DP} x forecast {control, ensemble mean, scenarios} | DP+REF (R1 family), then ENS finalists | CF; paired difference vs 5 d/clim; optimum horizon per terminal | v1 D1: confirm if best config is 10-15 d with learned/oracle V_T and 15 d zero-terminal loses >= 1 pt vs 5 d; refute (no horizon effect) if curve flat within 0.5 pt beyond 3 d. Also yields value of anticipation (1-2 d vs 5 d). | H-2-23, H-4-1, H-4-2, H-4-3, H-4-10, H-8-2 | medium |
| E-05 | Replan period and hysteresis | replan {1, 3, 6, 12, 24} h; hysteresis threshold on route-family switch {0, 1, 3} % of 48 h energy | R1, R2 | CF, heading reversals/day, route-family switches/week | Confirm v1 E3 if CF loss < 0.5 pt up to 12 h (cheaper ops) or if hysteresis halves switches at no CF cost; refute if 24 h loses > 2 pt. | H-5-8, H-8-4 | medium |
| E-06 | Refiner design and interface | (a) window {0, 24, 48, 72} h, step {15, 30, 60} min; (b) terminal = {value field, DP waypoint at +48 h, none}; (c) refiner vs DP with 20 km / 1 h resolution (no refiner) | R1 | CF gain of refiner; gain with field vs waypoint | D9 confirmed if gain >= 1 % (already 3-7 %); 'interface by value' confirmed if field >= waypoint + 0.5 pt; if (c) closes the refiner gain, the refiner is a resolution fix, not a separate layer. | H-4-4, H-4-5, H-4-23, H-4-41 | medium |
| E-07 | Discretisation convergence | dx {20, 40, 60, 80} km; dt {1, 3, 6} h; stencil span {1, 2, 3}; midpoint vs 3-point arc quadrature; conformal conic vs LAEA grid; fixed truth and forecasts | R1 without refiner and with | CF; heading at +24 h; energy within 1 % | v1 6.12 criterion: converged if heading changes < 5 deg and energy < 1 % when halving dx and dt. Refute 'fractions of a percent' if 40 km differs by > 2 pt from 20 km. Gives the right resolution for S6. | H-1-4, H-4-21, H-4-22, H-4-24, H-6-3, H-X-4 | medium |
| E-08 | Value function ladder and robustness (v1 E2) | terminal = {0, clim, clim x k, hindsight, hindsight x seasonal factor, V_theta iter-1, V_theta iter-2, S2S oracle features (perfect weekly means at 10-25 d)}; noise on level {+-10, +-20 %} and on gradient (spatial smoothing / random fields); terminal horizon {5, 10, 15} d; 12 months x 3 seeds | R1 family | CF vs clim terminal; effect of level vs gradient noise | V_theta needed (v1 D2) only if >= +1 pt over clim and >= +0.5 pt over hindsight x factor, significantly (E-23); v1 E2 prediction confirmed if level noise +-20 % costs < 0.3 pt and gradient noise costs > 1 pt. S2S oracle gain < 1 % => drop S2S machinery. | H-3-6, H-4-1, H-4-7, H-4-8, H-4-9, H-4-10, H-4-25, H-5-3, H-5-4, H-2-28, H-8-4, H-X-13 | expensive |
| E-09 | Manoeuvre cost (WP3) | simulator charges tau_m {0, 2, 4, 6, 10} min x rho_m {0, 0.3, 0.6} on tacks/gybes/turns > 20 deg; router assumes nominal (4, 0.3) or zero (mismatch grid); leg length {15, 30, 45, 60} min; explicit tack-state DP (1 h) vs envelope hold (medium-expensive) | R0, R1, R2 | CF loss per router; B0-R1 gap; manoeuvres/day | Confirm v1 4-15 % hold loss if B0 loses >= 4 pt at (4 min, 0.3); routing gain vs B0 robust if gap stays > 30 %. Refute D10 tack-state need if envelope hold is within 0.5 pt of tack-state DP. | H-4-30, H-4-31, H-6-11, H-X-5, H-10-1 | medium |
| E-10 | Polar and wind-calibration errors | P scale {0.9, 1, 1.1}; truth wind bias {-1, 0, +1} kn and x{0.9, 0.95, 1.05}; TWA shift +-5 deg; tack asymmetry +-5 %; peak sharpness; cut-in {5, 7, 9} kn; VPP mask on/off; router sees nominal, truth perturbed (mismatch) and both perturbed | R0, R1, R2 | absolute CF, gap to R0, ranking stability (Kendall tau of routers) | Routing conclusions robust if ranking and gap R1-R0 stable (<5 % relative change); production claims fragile if +-1 kn bias moves summer CF > 5 pt. | H-2-15, H-2-26, H-7-2, H-X-8, H-1-2 | cheap |
| E-11 | Ensemble design | members N {5, 10, 20, 50}; k {1, 3, 6, 12, N}; reduction {vector-EOF medoid, random, k-means centroid, scalar index, all members}; central-field variants {control, ensemble mean, lead-blended}; gamma {0, 0.1, 0.3, 0.5}; trunk {12, 24, 48, 72, 120} h; 2-branch tree at D5; no-trunk per-member values | ENS without refiner (speed), finalists with refiner | CF vs R1; planned-vs-realised optimism; chattering | If ensemble-mean field >= scenarios (H-4-13) then scenarios add nothing beyond a better centre; v1 D4 confirmed if medoid > random by >= 0.5 pt; trunk < 48 h reduces optimism without CF loss => v1's 48 h choice refuted. | H-2-9, H-2-10, H-3-9, H-4-12, H-4-13, H-4-14, H-4-15, H-4-16, H-5-1, H-6-6 | medium |
| E-12 | Alternative routers and baselines | R-greedy: argmax of smoothed 48-72 h forecast hold power within 36 h reach; R-clim: monthly best point with slow drift; R-isochrone / forward label-setting; R-NLP-only multistart; R-single-layer: long-horizon DP with clim terminal and no learned V; R-myopic 24-48 h; R-fallback: climb climatological V without forecast; R-learned: GBDT policy cloned from R1 | bench-6 + paired vs R1 | CF gap to R1, wall time, per-month failures | D5 (DP) confirmed if every alternative is <= R1 - 1 pt or > 10x slower; if R-greedy is within 2 pt of R1 the value of the sophisticated stack must be re-argued; isochrone parity confirms 'DP = energy-stratified isochrones' claim. | H-3-7, H-4-19, H-4-20, H-6-4, H-8-2, H-8-3, H-9-3, H-4-1 | medium |
| E-13 | Ocean-weather phenomenology (WP2, data only) | ERA5 2015: translation speed of wind-maximum features by season; Eulerian and Lagrangian persistence of P > 2.4 MW; spatial decorrelation lengths; temporal spectra by band; calm-spell durations; reachability and value of mobility (oracle with speed cap {4, 8, 12, 16} kn and radius cap {0, 200, 500, 1000, inf} km); Jensen bias E[P]-P(E[W]) along tracks; wind difference at 5-20 km (native 0.25 deg) | Oracle_REF_H, data analysis | distributions and fractions vs v1 claims | Confirm 1:4-1:6 speed ratio and rendezvous logic if features move at 15-30 kn and persistence time of productive conditions < 2 d; refute 'cannot chase' if capped-speed oracle loses < 3 pt. | H-1-1, H-2-1, H-2-2, H-2-3, H-2-9, H-2-18, H-2-29, H-4-33 | medium |
| E-14 | Oracle quality and EVPI | Oracle look-ahead {5, 10, 15, 30 d, full year}; DP 3 h vs 1 h; with/without refiner; planned-vs-realised optimism by policy and season; E0 with refiner/ENS as the causal policy | R1, R2, R3 variants | EVPI = oracle(full) - best causal; optimism % | Refute v1's EVPI 15-40 % if full-horizon oracle gap to R2 stays < 15 %; if oracle(30 d) - oracle(15 d) > 1 pt, current regrets are underestimated. | H-2-10, H-3-3, H-4-6, H-4-14, H-8-6, H-X-7 | medium |
| E-15 | Start point, B0 and domain | start {annual best, 50N 15W (v1 point), Lorient, 10 random cells >= 300 km from box edge}; B0 variants {annual, monthly, cross-validated by month, with manoeuvre}; box truncation (distance to edges) | R0, R1 | CF per start; routing gain vs B0; share of time near box edge | Routing gain robust if CF(R1) spread across starts < 3 pt and gain vs B0 > 25 % for all B0 variants; best-point location tells whether v1 zone (48-52N 12-18W) is simply a worse region. | H-1-2, H-2-16, H-2-19, H-X-3, H-X-9 | cheap |
| E-16 | Fleet logistics proxies | legs from Lorient to a prescribed moving core track (400-850 NM) and back (outbound/inbound energy by month); lambda recomputed with measured g_out, g_in, g_core; persistent core with lambda {0, v1, recomputed} and d_max {400, 600, 900, none}; departure date shifts -2..+2 d; Lorient vs core wind correlation (port closure proxy); quay queue arithmetic | R1 core, leg DP | kWh/NM/h; CF cost of d_max; leg energy range by shift | Confirm recall field only if lambda(d)*100 NM is 0.5-3 % of core power and measured g_out >> 500 kW changes it by > x2; weather-phased departures confirmed if leg energy range from shifts is >= 5 %. | H-3-5, H-3-8, H-4-35, H-4-36, H-4-37, H-4-38, H-4-39, H-6-9, H-9-5 | medium |
| E-17 | Safety and risk exposure | hours/yr with TWS > 35, 40, 45 kn along each router's tracks (track-truth join); penalty ramp from 30 kn and hard ban at 45 kn; ENS-spread margin on/off; gamma sweep | R1, R2, R0, R3 | exposure histograms; CF cost of avoidance | If unconstrained routers spend > 2 % of time above 35 kn, S4 CF is overstated and a safety term is architecture-relevant; if avoidance costs < 1 pt it is cheap insurance. | H-2-14, H-2-31, H-3-9, H-9-1 | medium |
| E-18 | Multi-year ERA5 | regrid ERA5 for >= 10 more years (at least DJF and JJA) onto the 40 km grid; held-out climatology, B0 and V_theta by year; bench-6-like set per year | R0, R1, R2 | effect sizes with CI across years; interannual spread | Needed to detect effects of 1-3 %: confirm ensemble / V_theta / clim terminal only if sign consistent in >= 70 % of years and CI excludes 0; quantifies same-year leakage (H-X-3). | H-2-20, H-4-26, H-8-1, H-X-3, H-X-6, H-4-10 | expensive |
| E-19 | Resolution and time sampling of wind | truth native 0.25 deg vs 40 km; forecast steps degraded to 3 h/6 h with linear interpolation; synthetic turbulence intensity 8-12 % in truth; 20 km planning grid | R1, R2 | CF change; peak TWS reduction at mid-step | Confirm v1 5-15 % peak smoothing if mid-step TWS peak drops by that amount and CF loss > 0.5 pt; reveals how optimistic the smooth ERA5 truth is. | H-7-1, H-X-4 | medium |
| E-20 | Calibration against real forecasts | GEFS v12 reforecast (AWS) or ECMWF archive for >= 8 start dates of 2015 vs ERA5 on the 40 km grid: RMSE vs lead, ACC of anomalies, spread-skill, timing error of fronts, control-mean gap, pattern correlation at D5-D10; refit ForecastErrorParams | analysis, then rerun E-04/E-11 headline | fit residuals; ACC at D7-D10 | Model accepted if RMSE within 15 % and ACC at D5/D7/D10 within 0.1 of real; otherwise rerun E-01..E-04 with refit law. | H-2-22, H-2-25, H-2-23, H-X-1, H-X-2 | expensive |
| E-21 | Compute scaling and cost model | bench_dp arcs/s per core; ENS N = 51; 10 km/1 h fine zone at real size; policy-iteration cost with ENS+REF policy | benchmarks | arcs/s, s per cycle, core-hours per iteration | v1 budget claims confirmed if full cycle < 60 s on 16 cores at real sizes; policy iteration with ENS+REF > 5x v1 estimate flags a DIM issue. | H-1-3, H-4-18, H-5-2, H-6-2 | cheap |
| E-22 | Code and simulator integrity audit | automated no-leak test (forecast bitwise independent of future truth); 1 vs 2 worker bitwise tracks; clamped-step count in S4 runs; IPOPT fallback rate by wind regime; d_min {10, 20, 40} km; feasibility mask handling | all policies | violation counts; CF deltas | Any non-zero leak or > 0.1 % clamped energy invalidates the affected comparisons. | H-4-29, H-6-10, H-7-4, H-X-11, H-X-12 | cheap |
| E-23 | Statistical protocol | effective sample size from autocorrelation; weekly-block bootstrap; simulation-based power analysis for 1 %, 2 %, 3 % effects with n months/years/seeds; report kWh and CF points besides regret | all experiments | CI half-widths; required n | Decides how many months/years/seeds each question needs (v1: < 2-3 % not significant with 60 winters; ours is 1 year). | H-3-4, H-4-26, H-8-1, H-X-6, H-X-14 | cheap |
| E-24 | Drift, leeway, current | k_L {0, 0.02, 0.03, 0.05}; synthetic current {0, 0.3, 0.8} kn random direction; hold TWA bias {80, 85, 90, 95} deg; leg length | R0, R1 | CF loss; hold drift [NM/day] | Confirm 5-10 deg compensation if drift < 5 NM/day at k_L 0.03 for the best bias; refute 'cost almost nil' if the best bias loses > 3 % of hold power (peak at 95-110 deg). | H-2-12, H-4-32 | cheap |

### Priority and order / Ordre proposé

1. **Cheap, decisive, no new data:** E-13 (phenomenology), E-14 (oracle/EVPI), E-23 (statistics), E-22 (audit), E-15, E-10, E-03, E-24, E-21.
2. **Forecast-law and design-claim tests (the sensitivity campaign core):** E-01, E-02, E-04, E-09 (needs WP3), E-12, E-11 (without refiner first), then E-06, E-07, E-08, E-05.
3. **Start in the background now, finish last:** E-18 (multi-year ERA5 regrid) and E-20 (real reforecasts) because they gate the credibility of everything; E-16/E-17/E-19 as capacity allows.

### Mapping of open/contradicted high and medium items to experiments

| id | crit | status | experiments |
|---|---|---|---|
| H-1-1 | high | open | E-13 |
| H-1-3 | medium | open | E-21 |
| H-1-4 | medium | contradicted | E-06, E-07, E-11 |
| H-2-1 | medium | open | E-13 |
| H-2-2 | high | open | E-08, E-13 |
| H-2-3 | medium | open | E-13, E-16 |
| H-2-4 | high | contradicted | E-10, E-12 |
| H-2-5 | medium | contradicted | E-13 |
| H-2-6 | medium | contradicted | E-10, E-13 |
| H-2-9 | high | open | E-11, E-13 |
| H-2-10 | medium | open | E-14 |
| H-2-11 | medium | contradicted | (done / arithmetic) |
| H-2-12 | medium | open | E-24 |
| H-2-14 | medium | contradicted | E-17 |
| H-2-16 | medium | contradicted | E-15, E-18 |
| H-2-18 | medium | open | E-13, E-18 |
| H-2-22 | high | open | E-20 |
| H-2-23 | high | open | E-04 |
| H-2-24 | high | open | E-01, E-02 |
| H-2-29 | medium | open | E-13 |
| H-2-31 | medium | open | E-17 |
| H-3-3 | high | contradicted | E-01, E-14 |
| H-3-4 | medium | open | E-23 |
| H-3-5 | medium | open | E-16 |
| H-3-7 | medium | open | E-12 |
| H-3-9 | medium | contradicted | E-02, E-11, E-17 |
| H-4-1 | high | open | E-04, E-08, E-12 |
| H-4-2 | high | open | E-04 |
| H-4-3 | medium | open | E-04 |
| H-4-7 | high | contradicted | E-08 |
| H-4-8 | high | contradicted | E-08, E-18 |
| H-4-9 | high | open | E-08 |
| H-4-10 | high | contradicted | E-04, E-08, E-18 |
| H-4-12 | high | contradicted | E-01, E-02, E-11 |
| H-4-13 | high | open | E-11 |
| H-4-14 | high | contradicted | E-11, E-14 |
| H-4-15 | medium | open | E-11 |
| H-4-16 | medium | open | E-11 |
| H-4-19 | medium | open | E-12 |
| H-4-21 | medium | contradicted | E-07 |
| H-4-23 | medium | open | E-06, E-07 |
| H-4-24 | medium | open | E-07 |
| H-4-25 | medium | open | E-08 |
| H-4-26 | high | contradicted | E-18, E-23 |
| H-4-30 | high | open | E-09 |
| H-4-31 | medium | open | E-09 |
| H-4-35 | high | contradicted | E-16 |
| H-4-36 | medium | contradicted | E-16 |
| H-4-37 | medium | open | E-16 |
| H-4-39 | medium | open | E-16 |
| H-4-41 | medium | open | E-06 |
| H-5-1 | high | open | E-08, E-11, E-20 |
| H-5-2 | medium | contradicted | E-21 |
| H-5-3 | medium | open | E-08, E-23 |
| H-5-4 | medium | open | E-08 |
| H-5-6 | medium | open | E-01, E-11 |
| H-5-8 | medium | open | E-05 |
| H-6-3 | high | contradicted | E-07 |
| H-6-4 | medium | open | E-12 |
| H-6-6 | medium | open | E-11 |
| H-7-1 | medium | open | E-19 |
| H-8-1 | high | open | E-18, E-23 |
| H-8-2 | medium | contradicted | E-04, E-12 |
| H-8-3 | high | open | E-12 |
| H-8-4 | medium | open | E-05, E-06, E-08, E-11 |
| H-8-6 | high | contradicted | E-14 |
| H-9-1 | high | open | E-17 |
| H-9-3 | medium | open | E-12 |
| H-X-1 | high | open | E-02, E-04, E-11 |
| H-X-2 | medium | open | E-02, E-20 |
| H-X-3 | medium | open | E-18 |
| H-X-4 | medium | open | E-07, E-19 |
| H-X-5 | high | open | E-09, E-24 |
| H-X-6 | high | open | E-18, E-23 |
| H-X-7 | high | open | E-14 |
| H-X-8 | medium | open | E-10 |
| H-X-9 | medium | open | E-15 |
| H-X-10 | medium | open | E-02 |
| H-X-12 | medium | open | E-22 |
| H-X-13 | medium | open | E-08 |
| H-X-14 | medium | open | E-23 |

## 6. Our own possible errors / Nos propres erreurs possibles

Places where S0-S4 results could be artefacts of our implementation or test environment (register ids `H-X-*` and cross-references):

| item | what could be wrong | experiments |
|---|---|---|
| Perturbation forecast built from the truth (H-X-1, H-X-2, H-X-10) | Forecast = displaced/amplified/noised ERA5: keeps the true system structure at all leads (displacement 320 km at D10 vs systems ~1000 km); exchangeable member/truth assumption gives control RMSE x1.38 worse than the mean; spread has no flow dependence (H-2-25); timing errors at D4 are ~3 h vs 6-9 h in v1 (H-2-24). **Direction of bias:** probably favours long horizons and ensembles; but could equally under-state ensemble value if real spread-skill is strong. | E-01, E-02, E-20 |
| Same-year climatology, B0 point, V_theta (H-X-3, H-X-13) | 2015 climatology and B0 point are chosen with 2015 knowledge (neighbouring months correlated); LOMO with a 5 d buffer removes only same-month leakage. **Direction:** favours B0 (conservative for routing gain) and the climatological terminal (inflates +2.8 %). | E-18, E-15 |
| 40 km / 3 h grid; ERA5 smoothness (H-X-4, H-6-3) | ERA5 effective resolution ~100 km: mesoscale shifts, gusts and 12 h-2 d variance absent; DP discretisation = ~3 % of V and orientation bias ~6 % at K=21; refiner compensates part. **Direction:** truth easier than the real sea; DP-vs-refiner results scale-dependent. | E-07, E-19, E-13 |
| No manoeuvre losses, no current/leeway in the simulator (H-X-5, H-2-12) | S1-S4 charge no tack/gybe loss; B0 holds 86-97 % of the time with the envelope (f_avail only in the DP hold reward). **Direction:** unequal; real B0 likely worse (routing gain larger), routed ships lose on heading changes. | E-09, E-24 |
| Single year 2015, 12 autocorrelated months, one ENS seed (H-X-6, H-X-14) | Paired t with 4-11 dof; ENS seed 2 dropped; monthly seed noise up to 143 MWh; effects of 1-3 % (ENS, V_theta, clim terminal, CVaR) are below detectability by v1's own rule. **Direction:** unknown; risk of both false positives (+2.8 % terminal) and false negatives (ensemble). | E-23, E-18 |
| Approximate oracle (H-X-7, H-8-6) | Oracle_REF_H: 15 d look-ahead + refiner + clim terminal; 3 h DP beaten by refined policies by up to 3.9 %. **Direction:** regrets (8-12 %) are lower bounds of true regret; EVPI under-estimated. | E-14 |
| VPP-bug mask choice, <10 kn extrapolation, hole repair (H-X-8) | Mask (TWA>=135, U<=2.5 m/s) bounds are the orchestrator's choice; cut-in 7 kn and (TWS/10)^3 scaling are hypotheses; 9078 of 23709 nodes repaired. **Direction:** summer/low-wind CF (B0 0.35) most affected. | E-10 |
| Start point choice (H-X-9, H-2-16) | Annual best offshore point (56.5N 21.6W, 849 NM from Lorient, 8.5 deg below the 65N box limit; v1 expects 48-52N 12-18W); outside cells are land; B1c is pulled north in autumn. **Direction:** CF 0.80 is that of a ship placed in the globally best cell. | E-15 |
| No safety/survival term, BETA flat to 50 kn (H-9-1, H-2-14) | Storm cores are as valuable as 22 kn winds for the optimiser; exposure not measured. **Direction:** CF overstated (real operation would avoid cores). | E-17 |
| Forecast hourly vs real 3-6 h steps and no interpolation smoothing (H-7-1) | Real products interpolate between 3-6 h steps (peak TWS -5-15 %). **Direction:** optimistic. | E-19 |
| V_theta evaluation (H-X-13, H-4-9) | Targets from plain B1 (not the final policy), mean regression, 3 closed-loop months, one seed: CV R2 overstates routing benefit (within-release ranking equals hindsight's). | E-08 |
| Power model and provider (H-X-11, H-X-12) | FeasiblePowerModel evaluates infeasible refiner commands at a slower speed (optimistic, 4 steps once); provider._weather reachable (no shipped policy uses it); coast margin and d_min 20 km differ from v1's 5-10 NM. | E-22 |
| Our deviations from v1 that change what was tested (H-4-22, H-4-23, H-4-31, H-5-1) | LAEA instead of conformal Lambert; mixed-heading envelope instead of tack-state fine DP; no 10 km/1 h zone; refiner at 30 min instead; V_theta at 5 d with 12 features instead of 15 d with Z500/MJO/regimes; 20 members instead of 51 or 5. S0-S4 results are about OUR variant of the architecture, not v1's. | E-06, E-07, E-08, E-09 |

## 7. Notes on method and caveats / Méthode et limites

- Entries paraphrase the v1 note (confidential, client-owned); no long text copied. Section numbers refer to the v1 note.
- Evidence figures come from S0-S4 documents and from a few small computations on ERA5 2015 and the BETA polar (aggregates only; BETA data are never reproduced). BETA numbers are max-over-speed per TWS/TWA and are indicative.
- 'untestable-here' means no data/assets in this PoC (Z500, S2S products, other years, buoys, fleet/wake model, at-sea trials); a sensitivity study is still proposed where possible.
- Criticality = would an error change the architecture or the dimensioning? It is not an estimate of probability of error.
- The register is meant to be updated at WP5: each verdict adds `verdict`, `evidence_s5` (experiment id, numbers) and revised status.
