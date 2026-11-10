## How to use this tool {#use}
This page compares routing strategies ("routers") run on the same simulated winters. Everything is computed offline; nothing here is a forecast.
- **Overview** answers "who harvests more?": table of policies x seeds, mean and spread, and a paired A-vs-B comparison.
- **Explorer** answers "where and when does a router lose?": pick a seed, move the time cursor, read the map and the synchronised curves.
- Small **i** icons and dotted terms explain themselves on hover; the grey line under each panel title says how to read it.
- Chips under the policy bar flag points of attention computed from the data. Click one to land here.
- Keys in the Explorer: left / right arrows step one hour (shift: one day), space plays.

## The problem in one page {#problem}
A wind-powered ship produces electricity while it sails or holds position in a favourable wind. Power depends on the true wind speed ([[TWS]]) and the angle at which it meets the course ([[TWA]]): the sweet spot is a beam wind between 18 and 26 kn at 75-105 degrees (the [[productive band]]). Too little wind gives nothing; above {{polar.derate_kn}} kn the output is derated and above {{polar.cutout_kn}} kn the machine shuts down for survival.
A router chooses where to go every {{replan_h}} h knowing only forecasts, whose errors grow with lead time. Its score is the energy J harvested over {{duration_d}} days. The **hindsight oracle** knows the true wind in advance and gives the upper bound; the gap to it is the [[regret]]. Improving a router means closing that gap, and the Explorer shows where it opens.

## Routers explained {#routers}
Each router is one policy: at every replan it receives a causal forecast and returns a plan (destinations every {{plan_dt_h}} h). The simulator executes the plan and measures energy on the TRUE wind.

### B0 - hold at the best fixed point {#r-B0}
Sails straight to one location chosen from training winters (other seeds than the evaluation ones) and station-keeps there for the whole mission. No forecast is used. It measures what a smart static choice is worth. Weakness: it cannot dodge storms nor chase wind; in the synthetic climate its point is near the French coast, which is a synthetic artefact (see Limitations).

### B0_spec - hold at the indicative zone {#r-B0_spec}
Same as B0 but at a fixed point (50N 15W) inspired by the specification's indicative operating zone. Useful as a "naive client plan" reference. Expect it to be the worst policy in the synthetic climate.

### B1 - deterministic receding-horizon DP (5 d, 15 d) {#r-B1}
Every replan it takes the control forecast (one single member), solves a dynamic programme ([[DP]]) on the grid over its horizon and follows the first part of the optimal path ([[MPC]]). The horizon end has no value ([[terminal value]] = 0), so it may end the horizon in a poor place. It trusts the forecast fully, including its long lead times: this is where the Jensen-type trap sits (an uncertain wind is not equal to its mean wind). Expect a longer horizon to help only while forecasts are skilful; here 15 d is on average worse than 5 d.

### Oracle - hindsight optimum {#r-Oracle}
One DP on the true wind over the whole mission, executed open loop. Not causal: it is the benchmark, never a competitor. Its own discretisation ({{plan_dt_h}} h, {{stencil_arcs}}-arc stencil) makes the regret about 2 points optimistic.

### ENS - ensemble stochastic DP with CVaR {#r-ENS}
Draws an ensemble of forecasts, reduces it to a few representative scenarios ([[medoid]]s found on principal modes of variability) and solves a two-stage DP: a 48 h common trunk that cannot anticipate which scenario will happen ([[non-anticipativity]]), then one branch per scenario. The objective blends the mean with a tail measure ([[CVaR]]) to avoid plans that are good on average but terrible in a storm. Expected edge over B1: larger when the spread of the ensemble is large (uncertain storms) and smaller in calm, predictable weeks. Panel "Replan diagnostics" shows scenario weights, explained variance and value statistics.

### REF - continuous refiner {#r-REF}
Takes a DP plan and polishes its first 48 h with a continuous optimiser (IPOPT through CasADi) at 30 min resolution, using the DP value at the end of that window as [[terminal value]]. It aims at removing the staircase tracks and the orientation dependence of the grid DP. Expected gain: modest but systematic; if it falls back to the base plan the track looks identical.

### Other routers {#r-generic}
A policy with an unknown name is shown with its exported parameters only. Name it with a known prefix (B0, B1, ENS, REF) to get its description here.

## Capability matrix {#matrix}
| Router | Uses forecast | Ensemble | Risk measure | Horizon | Terminal value | Refiner | Causal |
|---|---|---|---|---|---|---|---|
| B0 / B0_spec | no | no | - | - | - | no | yes |
| B1_5d / B1_15d | control member | no | none (mean) | 5 d / 15 d | zero | no | yes |
| ENS | ensemble, reduced | yes | CVaR | 15 d (48 h trunk) | zero | no | yes |
| REF | as its base DP | as base | as base | 48 h refined | DP value at t+48 h | yes (NLP) | yes |
| Oracle | truth | - | - | whole mission | - | no | NO |

## Hypotheses in force {#hyp}
Every number below is a hypothesis to be replaced with real data; conclusions are about relative behaviour, not absolute energy.
- **Polar**: {{polar.kind}}. Beam-reach optimum near {{polar.twa_opt_deg}} degrees, cap {{polar.cap_kw}} kW, derating from {{polar.derate_kn}} kn, cut-out at {{polar.cutout_kn}} kn.
- **Weather**: {{weather}} North-Atlantic winter (jet, travelling cyclones, regime index, noise). Forecast errors grow with lead; truth and forecasts come from the same generator.
- **Space and time**: {{grid_km}} km grid, {{plan_dt_h}} h DP step, replan every {{replan_h}} h, missions of {{duration_d}} d starting at {{start}}, no return-to-port constraint, 20 km coast clearance.
- **Simplifications**: no leeway or current in the graph search, no forecast availability latency, hourly truth.
- **Statistics**: {{n_seeds}} seeds (one seed = one winter). The spread between seeds is large.

## What good looks like {#expect}
- Every causal router should sit between B0_spec (worst) and Oracle (best); regret of a good one is in the low tens of percent or below.
- A router should keep its ship in the productive band longer than a static one: compare "Productive band" columns.
- The gap-to-oracle curve should grow slowly and steadily; steep steps point to a few bad decisions worth studying.
- Ensemble routers should win mostly on seeds with strong storm spread; if they do not, look at the scenario weights.
- Plan optimism (planned minus realised energy) close to zero means the router believes a forecast that comes true.

## Known limitations {#limits}
- Tracks are staircase-like: the DP moves along {{stencil_arcs}} possible directions, about 6 % energy dependence on orientation.
- Regret is about 2 points optimistic (oracle sees the truth every 3 h only).
- Synthetic climatology bias: storms intensify eastward, so the best fixed point is near the French coast rather than the open ocean.
- Few seeds: {{n_seeds}} winters are indicative, not statistically conclusive.
- TWA is undefined while holding; hold time counts as in the TWA band for the productive share.
- Cells within 20 km of the coast are forbidden for the optimiser; a harbour-exit corridor is not modelled.

## What to look at first {#path}
1. Overview: read the summary and the chips; note the regret ranking.
2. Paired comparison: choose the two routers you care about, look at wins and the mean difference.
3. Open the seed where they differ most (click a value in the per-seed table).
4. In the gap-to-oracle chart find where the curve rises fastest; use "Biggest losses" to jump there.
5. On the map, check the wind band and storm centres at that time: was the router in the wrong place, or the forecast wrong?
6. Compare the plan (dashed) with the actual track, and read the plan optimism and replan diagnostics.

## Changelog {#changelog}
- **S0** - grid, units and wind conventions, synthetic polar, coast signed-distance asset.
- **S1** - synthetic weather with causal forecasts, DP kernel, power envelope, closed-loop simulator, B0 / B1 / oracle, first regret figure.
- **S2 (in progress)** - ensemble reduction and CVaR two-stage DP, continuous refiner, this inspector.
