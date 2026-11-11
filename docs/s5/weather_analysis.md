# HORIZON S5 / WP2 - Ocean-weather analysis for a sail-propelled energy ship (ERA5 2015)

Confidential (client data). Scripts: `scripts/s5_weather/` (w0..w6, plot_*); raw results: `outputs/s5/weather/a1..a6.json`; figures: `docs/s5/fig/w_*.png`.

## 0. Data, definitions, method

* ERA5 10 m wind, year 2015, hourly, `Grid.from_bbox(-32, 5, 38, 65, 40e3)` (79 x 82 cells, ERA5 box 32W-5E / 38-65N), sea cells only (land / coast model and `outside` mask removed; 3,944 sea cells, 8 760 h). TWS in knots.
* **Hold power** `P_hold(TWS)`: the v=0 hold curve built from the BETA polar envelope (`hold_power_vs_tws`). Anchor values: 8 kn 40 kW, 10 kn 300 kW, 14 kn 830, 18 kn 1 770, 20 kn 2 320, 22 kn 2 390, 26 kn 2 500 kW (the hold curve is about 15-20 % below the free-sailing plateau of ~3 MW because a holding ship tacks near the wind). `CF_hold = P_hold / 3000 kW`. "Productive" = `P_hold > 2 MW` (TWS >= ~19 kn) or TWS 18-26 kn; "calm" = TWS < 10 kn (P_hold < 300 kW).
* Check against S4: a perfect-foresight DP that is forbidden to move (v=0) from the S4 start (56.49N, 21.6W) gives annual CF_hold 0.572 and monthly 0.784 / 0.691 / 0.702 / ... / 0.627, identical to the S4 B0 row (0.571; 0.784, 0.691, 0.701 ...). So CF_hold is a faithful proxy of what a held ship harvests in the S4 simulator, and the S4 start is the best fixed offshore point (best fixed cell in this analysis: 0.579).
* Spatial scale of the grid is 40 km; time step 1 h. Seasons DJF / MAM / JJA / SON. All numbers are for ONE year (see section 7).

Figures: `w_a1_annual_maps.png`, `w_a1_seasonal_maps.png`, `w_a1_hist_monthly.png` (section 1); `w_a2_runlengths.png` (2); `w_a3_spacetime.png` (3); `w_a4_mobility.png` (4); `w_a5_predictability.png` (5).

## 1. TWS distribution, hold power, capacity factor

| (basin mean over sea cells) | DJF | MAM | JJA | SON | year |
|---|---|---|---|---|---|
| mean TWS [kn] | 20.8 | 16.7 | 13.7 | 16.8 | 17.0 |
| calm < 10 kn [% time] | 12.5 | 20.9 | 29.3 | 20.3 | 20.8 |
| 10-14 kn | 11.6 | 18.1 | 24.2 | 17.6 | 17.9 |
| 14-18 kn | 14.9 | 19.8 | 22.2 | 19.5 | 19.1 |
| 18-26 kn | 32.0 | 28.8 | 21.3 | 30.0 | 28.0 |
| > 26 kn | 29.1 | 12.5 | 2.9 | 12.5 | 14.2 |
| P_hold > 2 MW [%] | 57.3 | 36.7 | 20.1 | 38.1 | 38.0 |
| mean P_hold [kW] | 1 753 | 1 337 | 979 | 1 362 | 1 356 |
| CF_hold | 0.584 | 0.446 | 0.326 | 0.454 | 0.452 |

* Annual TWS quantiles (5/10/25/50/75/90/95 %): 4 / 6 / 11 / 16 / 22 / 27 / 31 kn. Only 28 % of the time is in the 18-26 kn band, 14 % above 26 kn (free plateau energy, "wasted" above the knee), 21 % is calm.
* Basin monthly CF_hold from 0.59 (Jan) to 0.31 (Jul) and back to 0.60 (Dec): winter/summer ratio 1.9 (v1 says 2-3 for "available energy"; the plateau of the BETA polar compresses it). Pattern very similar to the monthly mean TWS (21.2 -> 13.3 kn).
* Spatial: annual cell CF_hold p10-p90 = 0.32-0.56 (962-1 671 kW); 40 % of cells above 0.5, none above 0.6 over the year (63 % of cells exceed 0.6 in DJF only; no cell exceeds 0.5 in JJA). Latitude bands: 35-40N 0.29, 40-45N 0.38, 45-50N 0.46, 50-55N 0.49, 55-60N 0.52, 60-65N 0.50. Zone 48-52N / 12-20W (v1 reference zone): mean TWS DJF 22.9, MAM 17.2, JJA 15.1, SON 18.1 kn, annual CF_hold 0.50.
* **The best cell of the year is at the western edge of the box** (57.7N, 31.4W, CF 0.579): the optimum is truncated by the 32W boundary (and the 65N one); S4's 56.5N/21.6W is within 0.007 of it. Maps of the north-western Atlantic outside the box are needed before claiming the optimum zone.

Implications for routing. (i) The resource is large-scale and strongly seasonal; a ship must be in the 50-60N storm-track half of the basin in winter, summer is intrinsically poor (CF_hold 0.33 on average, 0.41 for the best fixed point). (ii) 14 % of time above 26 kn means the polar plateau (no derating in BETA) makes time/placement in very strong wind uncritical for energy but it is exactly where the survival question (H-9-1) lives and where ERA5 underestimates (section 7). (iii) 21 % calm and 18 % in the 10-14 kn "ramp" mean a fixed ship loses ~40 % of its time to near-zero production.

## 2. Persistence of productive conditions and calms at a fixed point

Run lengths per sea cell (hourly, 8 760 h; "gapfill3" = interruptions of <= 3 h bridged). All cells pooled (`a2.json`, `w_a2_runlengths.png`).

| episode type | episodes / cell-yr | median [h] | mean [h] | time-weighted median [h] | share of time in episodes >= 24 / 72 h |
|---|---|---|---|---|---|
| P_hold > 2 MW | 167 | 11 | 19.9 | 38 | 70 % / 22 % |
| P_hold > 2 MW (gaps <= 3 h bridged) | 125 | 17 | 27.1 | 48 | 78 % / 31 % |
| TWS 18-26 kn | 279 | 6 | 8.8 | 15 | 29 % / 1.6 % |
| calm < 10 kn | 142 | 7 | 12.8 | 24 | 51 % / 14 % |
| calm < 10 kn (bridged) | 120 | 9 | 15.5 | 29 | 58 % / 18 % |

* The 18-26 kn band specifically is short-lived (median 6 h, 7 % of episodes last >= 24 h) because wind crosses it on the way to > 26 kn; P_hold > 2 MW (>= ~19 kn, open-ended) lasts longer: median 11 h but long tail (p90 49 h, 4 % of episodes >= 72 h, which carry 22 % of the productive time). Seasonal means of productive episode length: DJF 26.6 h, MAM 18.3, JJA 13.8, SON 18.6 h (median 16 / 11 / 9 / 11 h).
* Gaps between productive episodes: median 11 h, mean 32 h, time-weighted median 92 h; 58 % of the unproductive time sits in gaps longer than 72 h. In JJA the mean gap is 56 h (p90 145 h) versus 19 h in DJF.
* Calms: median 7 h, mean 12.8 h; 14 % of calm time is in calms >= 72 h (episodes >= 72 h: 1.7 %). Between calms (return time) the median is 27 h, mean 48 h; DJF gaps between calms are long (mean 69 h).
* Waiting time from a non-productive hour to the next productive hour (all cells): median 36 h, mean 81 h, p90 191 h, p95 280 h, p99 619 h. By season median / p90: DJF 19 / 115 h, MAM 34 / 189, JJA 57 / 258, SON 32 / 146 h.
* Windows with zero productive hour at a fixed point: 38 % of 24 h windows, 20 % of 72 h windows, 7.9 % of 168 h windows (JJA: 58 % / 34 % / 15 %; DJF 20 % / 9 % / 3 %).

Implications. A fixed ship sees productive conditions typically for 0.5-1 day and then waits 1.5 days (median 36 h, 8 days at p95); a 72 h window has a 1-in-5 chance of containing none. This is the structural reason for the 57 % -> 88 % gap in S4: 5-day-scale "being elsewhere" is needed. The time scale of episodes (10-30 h) is shorter than the ship's 48 h "tactical" refiner horizon: refiner decisions must anticipate wind that may be gone within a day; only the long episodes (>= 72 h, 22 % of productive time, mainly DJF) are exploitable by a slow ship that arrives late.

## 3. Space-time structure and drift of productive systems

### 3.1 Autocorrelation (`a3a.json`, `w_a3_spacetime.png`)

* Temporal, one fixed point (mean over cells, anomalies from the monthly climatology): TWS anomaly e-folding 17 h (integral time 16.6 h; median cell 16.6 h); wind-vector anomaly e-folding 22 h. ACF of TWS anomaly at 6 / 12 / 24 / 48 / 72 h = 0.76 / 0.51 / 0.25 / 0.10 / 0.04, below 0 after 96 h. Vector ACF at 24 h: DJF 0.27, MAM 0.34, JJA 0.35, SON 0.40 (longer memory in SON/JJA at 24 h, but in JJA it collapses by 72 h: 0.015). The binary indicator "P_hold > 2 MW" has e-folding 16.8 h but a heavy tail: ACF 0.28 at 24 h, 0.19 at 48 h, 0.12 at 120 h, 0.09 at 240 h (this tail is the seasonal cycle, not weather memory).
* Spatial (wind-vector anomaly): e-folding length 625 km mean (552-710 km by azimuth), half-correlation distance 404-522 km. Anisotropy is weak: 584 km east-west vs 666 km north-south for the vector field (14 % elongated north-south; component u is elongated east-west, 784 vs 558 km, v north-south, 816 vs 474 km, as expected for a non-divergent flow). TWS anomaly is nearly isotropic: e-folding 450 km (404-500 km), half-correlation 294-356 km.
* Consequence: with a ~450-650 km correlation length and a 17-22 h correlation time, the "field" has roughly 1 independent cell per 700 km square and renews every ~1 day.

### 3.2 Translation speed of patterns (lagged cross-correlation) (`a3b.json`)

TWS anomaly fields at t and t + dt (dt = 3 h and 6 h, tiles of 400 km blocks of 800 km, search +/-12 cells), best shift with sub-cell interpolation, quality-filtered (peak correlation > 0.5; 99.5 % of blocks kept; mean peak correlation 0.94 versus 0.88 at zero shift). Speeds in knots (dt = 3 h; dt = 6 h within 1-2 kn on medians):

| blocks | median | mean | p10-p90 | < 7.8 kn (ship 4 m/s) | < 15.6 kn (ship 8 m/s) | > 20 kn | > 30 kn | % eastward |
|---|---|---|---|---|---|---|---|---|
| all | 13.6 | 16.9 | 2.3-36.1 | 31 % | 56 % | 33 % | 16 % | 83 |
| productive (mean TWS >= 16 kn) | 18.7 | 21.1 | 3.0-41.4 | 21 % | 42 % | 47 % | 24 % | 87 |
| strong (>= 20 kn) | 22.1 | 23.8 | 3.0-45.2 | 18 % | 34 % | 55 % | 31 % | 89 |
| weak (< 12 kn) | 7.3 | 9.8 | 1.6-21.2 | 53 % | 81 % | 12 % | 4 % | 76 |
| DJF productive | 23.2 | 25.1 | 3.9-47.0 | 16 % | 32 % | 58 % | 34 % | 88 |
| JJA productive | 13.2 | 14.7 | 2.7-28.7 | 30 % | 60 % | 27 % | 8 % | 84 |

Mean velocity (all blocks) +11.1 kn east, +2.3 kn north (productive blocks +14.3 / +3.7). So: productive winter systems move at 20-35 kn (median 23 kn, interquartile 12.5-35 kn), consistent with v1; but the distribution is broad (about a third slower than 15.6 kn), summer systems move at 13 kn, and weak-wind patterns are slow (7 kn). The ratio of system speed to the ship's productive speed (3-4 m/s = 6-8 kn) is ~2.4 for the median productive block and ~3 in DJF (mean 2.7 / 3.2), not 4-6 as v1 states for a 3-9 kn ship, and ~1.2-1.5 versus the ship's absolute maximum (8 m/s = 15.6 kn). Velocities are pattern velocities of a 800 km anomaly (mix of advection and wave propagation) and cannot be measured above ~43 kn at dt = 6 h.

### 3.3 Lagrangian vs Eulerian persistence; patch sizes (`a3c.json`)

Probability that a cell productive now (P_hold > 2 MW) is productive tau hours later, (a) at the same place, (b) at the place displaced by the local pattern velocity (a ship following the system exactly), (c) following but with speed capped at 7.8 or 15.6 kn. Unconditional probability is 0.378.

| tau [h] | stay (Eulerian) | follow <= 7.8 kn | follow <= 15.6 kn | full system velocity |
|---|---|---|---|---|
| 6 | 0.795 | 0.812 | 0.820 | 0.821 |
| 12 | 0.682 | 0.698 | 0.703 | 0.691 |
| 24 | 0.570 | 0.564 | 0.546 | 0.497 |
| 48 | 0.516 | 0.476 | 0.428 | 0.393 |

* Following the system helps by 1.5-2.5 points for 6-12 h, and is **worse** than staying beyond ~18 h (-7 points at 24 h and -12 points at 48 h for a full-system follower, which at 48 h is hardly better than the 0.38 climatological chance). DJF: stay 0.69 / 0.67 at 24 / 48 h versus 0.61 / 0.56 for following. JJA: stay 0.355 / 0.239, following 0.315 / 0.17 (at 24 h JJA staying = climatology + 0.0).
* Interpretation: "productive wind" is not a conserved object that is carried along; individual depressions deepen, fill and are replaced by the next member of the storm track, so a place inside the productive regime stays productive more often than the moving patch does. Patch geometry: P_hold > 2 MW connected areas (>= 20 cells, n = 2 226): equivalent diameter median 530 km (p25-p75 313-1 030 km, p90 1 700 km; domain-truncated), patch speed median 11 kn, 41 % slower than 7.8 kn and 62 % slower than 15.6 kn; passage time of a patch over a fixed point 35 h median (p25-p75 18-89 h).

Implications. (i) v1's claim "systems outrun the ship so it can only be on their path, never chase them" is **supported** as regards speed and **refined**: the question is not chasing, because even a perfect chaser loses to a stationary ship beyond 18 h. (ii) The value of mobility must be sought in the spatial gradient across a 450-650 km scale (section 4), not in surfing a feature. (iii) A rendezvous with a patch that moves 20 kn and is 500 km wide lasts ~1 day for a fixed ship; a ship moving across the track at 4 m/s crosses it. (iv) Forecast horizons of interest are the passage time (1-3 days), not the ~1 week that v1 proposes for the strategic value field.

## 4. Reachability and value of mobility

### 4.1 Reachable better wind (`a4a.json`, `w_a4_mobility.png` right)

Static reach (sea-path distance <= v T, 8-neighbour stencil on the sea graph). `local` = mean CF_hold at the ship's own cell, `now-best` = best P_hold now inside the reach (snapshot), `persistence` = relocate to the now-best cell and read the CF_hold over the next window of length T, `foresight` = relocate to the cell with the best future-window mean (perfect forecast of the realised weather; an upper bound biased up by taking a maximum over 12-3 000 cells).

| speed, T | reach [km] / cells | local now | best now (snapshot) | stay, next window | relocate by persistence | relocate with foresight | gain foresight when stay < 0.4 |
|---|---|---|---|---|---|---|---|
| 4 m/s, 6 h | 86 / 12 | 0.452 | 0.545 | 0.449 | 0.485 | 0.534 | +0.12 |
| 4 m/s, 24 h | 346 / 187 | 0.451 | 0.727 | 0.451 | 0.490 | 0.674 | +0.34 |
| 4 m/s, 72 h | 1 037 / 1 263 | 0.449 | 0.840 | 0.450 | 0.494 | 0.746 | +0.46 |
| 8 m/s, 6 h | 173 / 55 | 0.452 | 0.632 | 0.449 | 0.527 | 0.618 | +0.26 |
| 8 m/s, 24 h | 691 / 651 | 0.451 | 0.814 | 0.451 | 0.519 | 0.769 | +0.52 |
| 8 m/s, 72 h | 2 074 / 3 058 | 0.449 | 0.859 | 0.450 | 0.504 | 0.791 | +0.53 |

* At 24 h a 4 m/s ship can reach (346 km, roughly one correlation length) a cell with instantaneous CF 0.73 versus 0.45 for the local cell; at 8 m/s 0.81. But what you would find there by going to the currently best cell is mostly gone by the next window: persistence relocation realises only +3 to +7 points (0.49 at 4 m/s / 24 h; 0.52 at 8 m/s / 24 h), essentially independent of T. Foresight realises +22 points (4 m/s, 24 h) to +32 points (8 m/s, 24 h) and saturates after 24-72 h. Summer is lowest in absolute level (foresight 0.58-0.66 at 4 m/s) but the gain is similar (+0.26-0.34).
* 54 % of the time a fixed ship's next-window CF is below 0.5; when it is below 0.4, relocating with foresight gains 0.34 (4 m/s / 24 h), persistence 0.12.

### 4.2 Perfect-foresight DP on the hold-power field (`a4b.json`, `a4c.json`)

Dynamic programming on 3-hourly mean CF_hold fields, ship moves within a disc of radius v dt (cells of 40 km), no manoeuvre or transit cost, free to move over all sea cells, start 56.49N / 21.6W:

| ship speed v [m/s] | 0 | 4 | 6 | 8 | 12 | 16 | 24 | 32 |
|---|---|---|---|---|---|---|---|---|
| annual CF_hold of oracle | 0.572 | 0.791 | 0.807 | 0.820 | 0.834 | 0.840 | 0.848 | 0.853 |
| JJA / DJF at the same speeds | 0.41 / 0.70 | 0.72 / 0.85 | 0.75 / 0.86 | 0.76 / 0.86 | 0.79 / 0.87 | 0.80 / 0.87 | 0.81 / 0.87 | 0.82 / 0.88 |

(v = 2 m/s moves 0.54 cell per step and cannot leave its cell on this lattice: it reproduces v = 0; this is a resolution artefact.) Starting anywhere gives 0.78 (4 m/s) / 0.81 (8 m/s) on average: **with perfect foresight and mobility the starting position no longer matters** (best fixed point 0.579 versus mean fixed cell 0.452).

Share of the S4 oracle advantage over the best fixed point (oracle 0.880, B0 0.571, gap 0.309 CF) that is explained by reaching better wind (hold-power oracle minus fixed point, same point):

| scope | CF_hold oracle | gain vs fixed | share of S4 gap |
|---|---|---|---|
| v = 4 m/s, unlimited range | 0.791 | +0.219 | **71 %** |
| v = 8 m/s | 0.820 | +0.248 | **80 %** |
| v = 16 m/s | 0.840 | +0.268 | 87 % |
| v = 8 m/s confined to R = 80 km of the start | 0.640 | +0.068 | 22 % |
| 160 km | 0.686 | +0.114 | 37 % |
| 320 km | 0.742 | +0.170 | 55 % |
| 640 km | 0.793 | +0.221 | 72 % |
| 1 280 km | 0.818 | +0.246 | 80 % |
| v = 4 m/s, R = 160 / 320 / 640 km | 0.671 / 0.720 / 0.765 | +0.099 / +0.148 / +0.194 | 32 / 48 / 63 % |

The remaining 20-29 % of the gap (0.06-0.09 CF) is what a hold-power oracle cannot see: production while sailing at 6-9 kn in the best TWA (the free-sailing polar is above the hold curve), the 3 h versus 1 h resolution, and the 15 d look-ahead approximation of Oracle_REF_H.

Does the oracle chase systems? Along the optimal path the ship moves in 94 % of the steps (mean speed 7.2 kn when moving at the 4 m/s setting, 12.6 at 8 m/s) but only 28-36 % of its steps are within 45 degrees of the local pattern velocity, 44 % are directed against it (cos angle +0.08-0.12 on average); the mean velocity component along the system is only +0.6 kn (4 m/s) to +1.2 kn (8 m/s) versus pattern speeds of 17 kn. The oracle zig-zags within the productive zone, it does not ride systems.

Implications. (i) Mobility is worth about +0.22 to +0.25 CF (+38 to +43 % of B0), of which half is obtained within ~300 km and three-quarters within ~650 km, i.e. the gain scales with the ~500-650 km correlation length; the extra from 4 -> 8 m/s is +0.03 only (+3 points, 10 % of the gap), so a high top speed is not what matters, being able to move ~7 kn continuously and *knowing where* is. (ii) The gap is explained to the extent of 70-80 % by *being at a better place at the right time*: the information needed is the realised weather within 300-700 km over 1-3 days, so forecast value is concentrated at 1-3 days (see section 5). (iii) Pure persistence ("go where it is windy now") recovers only 15-20 % of the foresight gain at 24-72 h (+0.04 vs +0.22 at 4 m/s): simple heuristics (H-8-3) based on current or smoothed analysis wind lose most of the value; they need a forecast. (iv) The best-fixed-point baseline B0 in S4 is hindsight-optimal over the year (selection bias, see section 6), so the true benefit of mobility with a non-hindsight site selection is slightly larger than 0.309.

## 5. Predictability proxy (forecast model v2) (`a5.json`, `w_a5_predictability.png`)

Method: 39 issue times (every 9 days from 6 Jan), `ERA5ForecastWeather.forecast_cycle` with 20 members, 6-hourly leads to 10 days; event "P_hold > 2 MW at sea cell x at lead L"; probabilistic forecast = member fraction. Brier skill score (BSS) versus (a) annual climatology frequency, (b) monthly climatology; compared with calibrated persistence (probability of being productive at t+L given productive/non-productive at t, pooled). ACC = anomaly correlation of TWS (vs monthly mean).

| lead | 0 | 24 h | 48 h | 72 h | 96 h | 120 h | 168 h | 240 h |
|---|---|---|---|---|---|---|---|---|
| BSS forecast vs annual clim | 0.88 | 0.76 | 0.69 | 0.63 | 0.54 | 0.46 | 0.39 | 0.24 |
| BSS forecast vs monthly clim | 0.86 | 0.73 | 0.65 | 0.59 | 0.46 | 0.35 | 0.29 | 0.18 |
| BSS calibrated persistence | 1.00 | 0.02 | -0.03 | -0.05 | -0.05 | -0.02 | -0.02 | -0.05 |
| ACC TWS: control / ensemble mean | 0.98 / 0.99 | 0.91 / 0.95 | 0.84 / 0.91 | 0.79 / 0.85 | 0.67 / 0.77 | 0.64 / 0.73 | 0.50 / 0.62 | 0.48 / 0.58 |
| ACC persistence | 1.00 | 0.23 | 0.07 | 0.05 | -0.07 | 0.04 | -0.07 | -0.06 |
| RMSE TWS control / ens. mean / persistence [kn] | 1.4 / 1.0 / 0 | 3.2 / 2.3 / 8.4 | 4.1 / 3.0 / 9.3 | 5.2 / 4.1 / 9.7 | 6.6 / 5.1 / 10.0 | 7.1 / 5.5 / 9.5 | 9.3 / 7.1 / 9.8 | 9.8 / 7.6 / 10.0 |

* Persistence of the event loses all skill relative to climatology after 24 h (BSS 0.02), matching the 17-22 h decorrelation times of section 3.1 (ACF 0.25 at 24 h); the forecast model keeps BSS >= 0.46 (annual clim) to day 5 and 0.24 at day 10. ACC of the control falls below 0.6 at 144 h, of the ensemble mean at 180 h. Hit rate of "p > 0.5": 0.93 (24 h), 0.89 (72 h), 0.84 (120 h), 0.77 (240 h), against 0.63-0.65 for always forecasting the climatological mode. Daily-mean event skill 0.86 / 0.77 / 0.72 / 0.64 / 0.61 / 0.58 / 0.48 / 0.48 / 0.44 / 0.40 for days 0-9. By season the day-10 BSS is 0.28 (DJF), 0.19 (MAM), 0.15 (JJA), 0.35 (SON); the model's skill is weakly seasonal by construction (displacement amplitude +/-15 %).
* Skill versus the geophysical time scales: the forecast stays skilful for 5-10 days, i.e. 5-10 times longer than the 17-22 h e-folding time and 3-5 times longer than the ~1-3 day passage time of patches (3.3). Relative to the decorrelation scale a forecast is thus useful far beyond what a naive persistence extrapolation gives; the real question is how much of the forecast skill is credible.
* **This result is a property of the perturbation model, not an independent measurement.** The forecast is the truth displaced (rms 40 km D1 -> ~250 km D7), amplitude-modulated and noised: it always contains the true storm structure (H-X-1), the error law is calibrated to hypothesised ECMWF ENS 10 m RMSE targets (2-3 m/s at D2 etc., H-2-22) and not fitted to real forecasts. The model therefore reproduces by construction v1's "useful horizon D5-6 deterministic / D8-10 probabilistic" (ACC 0.6 at D6 / D7.5) and cannot refute or support it (H-2-23 stays open; it is "consistent with v1 by construction"). In reality there is no skill at D8-10 in individual systems; a better proxy of real skill is the BSS at 3-5 days (0.5-0.6) and the ensemble mean's gain over the control (RMSE factor 1.3-1.4, exchangeable-model artefact, H-X-2).

Implications. (i) The only horizon where the policy has a clear informational advantage over climatology+persistence is 1-5 days; beyond day ~5 the model (and in reality all the more) is near the climatology, which supports a climatological terminal value after 5 d (S4: +2.8 %). (ii) The optimal decision information (best cell within 300-700 km for the next 1-3 days) is within the credible forecast range, so the physical value of mobility (section 4) can be captured with forecasts of 24-72 h; the value of D5-10 ensembles is expected to be small, in agreement with S4 (+1.2 %). (iii) Real forecast archives (GEFS/ENS reforecasts) are needed to calibrate the skill curve before concluding anything about horizons.

## 6. Sampling noise / single-year limitations (`a6.json`)

* Monthly CF_hold at the best-fixed S4 start: 0.78 (Jan), 0.35 (Jul), 0.63 (Dec); month-to-month standard deviation 0.13 raw, 0.055 after removing a two-harmonic seasonal cycle (basin cell median: raw 0.126, residual 0.058; range of basin-mean monthly CF 0.31-0.60).
* 30 day windows: residual std 0.052 (cell median), 0.056 at the S4 start; mean of six 30 d windows has standard error ~0.021 CF if independent (v1 / S4's 3-6 window comparisons therefore cannot resolve differences below ~2-4 points, in line with H-4-26).
* Annual CF_hold: moving-block bootstrap (7 d blocks, stratified by month) standard error 0.015 at the S4 start, 0.016 median per cell (p90 0.020), 0.006 for the basin mean. Effective independent synoptic samples about 65 per season (92 d x 24 / (2 x 17 h)); so a seasonal mean is determined to about +/-0.02-0.03 CF by sampling alone, but the interannual variation (NAO phase, blocking regimes) is not sampled at all.
* Spatial pattern stability inside the year: Spearman rank correlation of cell CF between DJF and JJA 0.79, between Jan-Jun and Jul-Dec 0.87, odd versus even months 0.89. Best-fixed-point selection bias: the cell that is best in the even months realises 0.521 in the odd months, whereas the cell that is best in the odd months reaches 0.605 in those same months, so selecting the best cell with the same data costs 0.08 (half-year samples) of in-sample optimism; with the full year the optimism of B0 (and of its "best offshore point" status, S4) is probably 0.02-0.04, i.e. the hold baseline for a non-clairvoyant operator is lower than 0.571 and the routing advantage (S4: +0.31) is slightly understated.
* Single year: every statement on return periods, episode statistics (many cells x ~167 episodes, but strongly correlated in space and across the year), advection speeds (~60 000 block-times, strongly correlated) and skill is conditional on 2015. The interannual spread of CF_hold in ERA5 over 45 years is not available in the cache and should be run before final numbers are used for design (spatial pattern, particularly the western optimum).

## 7. Paranoid caveats

1. **Resolution and smoothing (40 km, hourly).** The ERA5 native grid is ~31 km (effective resolution ~3-4 grid steps), bilinearly resampled to 40 km. Spatial scales below ~150 km (fronts, convective gusts, polar lows) are absent; wind speeds are grid-box means, so the hold power evaluated on them lacks the sub-grid variance. For a convex power curve (below the knee) this underestimates production (Jensen, +19 % at 14 kn, -15 % at 20 kn for sd 4 kn, H-2-9); above the knee (>= 22 kn) it overestimates a bit. Net effect on CF_hold is of the order of +/- 0.02 but of unknown sign. The 40 km grid also truncates the shortest persistence: 3 h/40 km fronts cannot be seen; episode counts for short durations are therefore biased low, but hourly sampling of a 1 h-smoothed field also biases episodes long.
2. **ERA5 10 m wind biases.** ERA5 underestimates strong ocean winds (v1 claims 5-10 %, to be checked against ASCAT/buoys; not testable here). Sensitivity from the hold curve (all wind scaled, `sea_series.npz`): TWS x0.95 / 1.05 / 1.10 gives basin CF_hold 0.422 / 0.480 / 0.507 (versus 0.452) and S4-point CF 0.546 / 0.596 / 0.618 (versus 0.572); P_hold > 2 MW share 33.8 / 42.0 / 45.8 % (38.0 %) and calm share 22.9 / 18.9 / 17.2 % (20.8 %). So a 5 % wind bias moves CF_hold by +/- 0.03 and the productive share by +/- 4 points; the mobility value (+0.22-0.25) is relatively insensitive, because it is a difference. Underestimated extremes mean the > 26 kn share (14 %) is a lower bound: the survival question is more serious than ERA5 suggests.
3. **Single year (2015).** See section 6. All maps, return times, advection speeds and hindsight-selected sites could differ in another year; relative conclusions (spatial scales, mobility share, Lagrangian < Eulerian) are expected to be more robust than absolute levels (CF, seasons).
4. **Hold-power model assumptions.** CF_hold uses the v=0 hold curve from the BETA envelope: instantaneous (1 h) wind, no waves/current, no manoeuvre cost (tack/gybe losses 4-15 %, H-4-30), no polar noise, no derating above 50 kn. The 3 MW plateau is not reached by the hold curve (2.5 MW at 26 kn), so "productive" defined as P_hold > 2 MW is not the same as the free-sailing 22 kn threshold: it is reached at TWS ~19 kn. The oracle DPs charge no energy for movement (movement is free and the ship produces hold power while moving), unlimited sea range, 3 h steps, a Chebyshev-like disc of radius v dt on a 40 km lattice (radius 1.08 cells at 4 m/s: coarse; 2 m/s non-resolvable), coast model reduced to the sea mask (no coastal margin) and no port constraints; "reachable" is a straight-line reach, not a routed path. Mobility gains are therefore upper bounds on what a real ship can capture (manoeuvre cost, travel-induced upwind legs; at 4 m/s the ship's production in 90-150 deg TWA is however better than at hold, which partly compensates).
5. **Advection estimates.** Pattern velocities are estimated by cross-correlation of TWS anomalies in 800 km blocks, not by tracking individual cyclones: they smooth over several features, mix advection with growth/decay and are limited to +/-12 cells per lag (43 kn at 6 h). Lagrangian follow-the-system tests use this local velocity, with errors that penalise the follower; a tracked-object analysis could give a more favourable result at 12-24 h (but the Eulerian staying probability would remain a strong baseline).
6. **Perturbation forecast model.** Section 5 skill is a property of the model (true structure at all leads, hypothesised error law, exchangeability) and over-optimistic at D5-10; it cannot be used to validate v1's horizons. Real forecasts are expected to lose individual systems at D7-8; their skill may also have a different seasonal structure (v1: best large-scale skill in winter, relative skill worst in summer). The ensemble is exchangeable by construction (mean beats control by x1.35 in RMSE).
7. **Selection bias** in hindsight-best fixed points (S4's 56.5N/21.6W; the best cell here at the box edge) and in "foresight" maxima over many cells (4.1): both inflate the apparent value of mobility relative to a causal policy; S4's closed-loop routing (CF 0.80 vs oracle 0.88) is the causal measure.
8. **Box truncation.** The ERA5 box (32W-5E, 38-65N) cuts the productive storm-track area (best cell at the western boundary); mobility gains involving long-range travel (> 1 000 km) are partly limited by the box edges; v1's zone (45W-5E) is larger.

## 8. Verdict on v1 claims (weather items)

| v1 item | verdict | evidence |
|---|---|---|
| H-1-1 / H-2-1: depressions translate at 20-35 kn, 4-6x faster than the ship, so the ship can only be on their path, never chase | **Supported in kind, over-stated in factor** | median pattern speed 18.7 kn (productive), 23 kn in DJF, 13 kn in JJA; 33 % of all patterns > 20 kn; ratio to 4 m/s ship ~2.4x (DJF ~3x), to 8 m/s ~1.2-1.5x; and following a system for >= 18 h is worse than staying (0.50 vs 0.57 at 24 h; 0.39 vs 0.52 at 48 h) |
| H-2-3-type "harvest while drifting east" (mobility along the wind) | **Refuted for the oracle** | oracle path is not aligned with system motion (cos 0.1; 44 % against) |
| H-2-17: reference-zone mean wind (DJF 20-24, MAM 16-20, JJA 11-15, SON 16-22 kn) | **Supported** (JJA 15.1 slightly above) | 22.9 / 17.2 / 15.1 / 18.1 kn |
| H-2-18: seasonal modulation of available energy 2-3x | **Qualified** | CF_hold winter/summer 1.8-1.9 (mean hold power 1 753 vs 979 kW) |
| H-2-16: harvesting zone 42-55N / 10-35W | **Refuted/qualified** | best cells at 55-60N and the box's western edge, CF 0.52 vs 0.46 at 45-50N |
| H-2-23: useful horizon D5-6 deterministic / D8-10 probabilistic | **Untestable / consistent by construction** | proxy built on the same assumption |
| H-2-22 / H-2-24: timing errors +/-6-12 h at D2-5 destroy a rendezvous | **Not tested directly; plausible** | passage time of a patch 35 h median (18-89 h): timing errors of 6-12 h are 15-30 % of it |
| H-2-26: ERA5 underestimates strong winds 5-10 % | **Untestable here; quantified impact** | +5 % wind = +0.03 CF, +4 pts productive share |
| H-1-2: routing must beat the best fixed point by a wide margin | **Supported** (in the environment) | mobility with foresight +0.22-0.25 CF (+38-43 %) from hold power alone; 71-80 % of the S4 oracle advantage |
| "ship must remain in the productive zone; persistence of regimes of 6-12 d" (H-2-20) | **Not supported by Eulerian persistence at 40 km** | productive episodes median 11 h; 4 % of episodes >= 72 h; spatial / temporal e-folding 450-650 km / 17-22 h; long memory only in the 0.1-0.2 tail of the indicator ACF (seasonal) |

Other results of this analysis for the register: (a) the value of mobility is concentrated within the first 300-650 km (50-70 % of the gain), (b) persistence-based relocation recovers 15-20 % of the foresight gain at 24-72 h, (c) the CF_hold DP reproduces the S4 B0 monthly numbers (validation of both), (d) a 2015 single-year estimate of the optimum zone is truncated by the box.
