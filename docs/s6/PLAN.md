# Sprint 6 — Real weather: multi-year history and real forecast quality

Client brief (2026-11-12/14): S5 showed that forecast error is the bottleneck (perfect forecast
85.0 % vs 79.8 % at the nominal emulated error, −7–8 pt per nominal unit; intensity-type errors cost
far more than displacement-type ones). S6 is dedicated to (a) the multi-year weather history:
structures, variability, offline estimators of the terminal value; (b) the detailed quality of real
weather forecasts, from at least two sources, to compare and to combine. Validate every download
pipeline before any long-period launch; update the statistics as coherent periods become available,
then extend the period to confirm the results over several seasons and years.

## Data (public repositories, see circeo-meteo `docs/MODUS_OPERANDI_fr.md`)

| Source | Use | Period |
|---|---|---|
| ERA5 (wind 0.25°, waves 0.5°, SST) | truth, climatology, terminal value | 1995–2025 |
| Copernicus Marine (GLORYS12, analysis-forecast) | currents, sea temperature | 1995–2025 / daily |
| GEFSv12 reforecast (0.5°, 5–11 members) | 20 years of homogeneous ensemble errors | 2000–2019 |
| GEFS operational (0.5°, 31 members; control 0.25°) | second ensemble source | 2023–2025 |
| GFS-Wave (0.5°) | second wave forecast | 03/2021–2025 |
| ECMWF open data: HRES 0.25°, ENS 0.5° (51 m.), AIFS 0.25°, waves 0.5° | best forecasts | 01/2023– (AIFS 02/2024–) |
| WeatherBench2 HRES 2016–2022 | longer deterministic ECMWF history | pending licence decision |

## Work packages

| WP | Content | Output |
|---|---|---|
| WP1 | Download pipelines: availability probes over each whole period, one validated month per source (timing, size, content, ERA5 comparison), then bulk extraction with content checks gating every upload | circeo-meteo `meteo/probe.py`, `meteo/check.py`; Releases |
| WP2 | Forecast scores vs ERA5 from the archived files, every product and month, kept up to date automatically (daily) — including the router view (40 km planning grid, sea cells of 32W–5E, 38–65N) | circeo-meteo `meteo/scores.py`; Release `scores-v1` |
| WP3 | Real forecasts vs the S5 emulator: equivalent error scale per product, error structure (bias / amplitude / phase decomposition of wind speed), month-matched; implied capacity factor through the S5 sensitivity curve | `scripts/s6/fc_vs_emulator.py`, `scripts/s6/compare_emulator.py`, `docs/s6/fc_vs_emulator.md` |
| WP4 | Router replay on real archived forecasts (adapter with the real availability latency, ERA5 2023–2025 truth): capacity factor with HRES first (reference), then AIFS, then ENS; same protocol as the S5 validation | CF per product, paired vs the emulator |
| WP5 | Ensemble construction experiments E-S6-1..4 (below) | `docs/s6/ensembles.md` |
| WP6 | Multi-year weather history (1995–2025): structures, inter-annual and seasonal variability, offline terminal-value estimators | `docs/s6/history.md` |
| WP8 | Extended routing zone (20–75 N, 80 W–15 E, the archive box): planning grid, coast mask, climatology / terminal value, start point(s); HORIZON v2 replay on the extended zone with real forecasts, paired against the S5 zone | CF S5 zone vs extended zone |
| WP7 | Emulator recalibration on real errors (size per lead, structure, bias), if WP3/WP4 show it matters | `ForecastErrorParams` v3 |

## Order of the two evaluations (client decision, 2026-11-14)

Two effects are measured **separately**, each on the S5 routing zone first:
1. **Step 1 — forecast source** (WP3, WP4, WP5): from the emulator to real forecasts (HRES, AIFS,
   ENS), then calibrated forecasts and combinations (E-S6-1..4), on the S5 zone (32 W–5 E,
   38–65 N, 40 km, S5 start point).
2. **Step 2 — routing zone** (WP8): extend the zone with the best forecast source of step 1,
   paired against the S5 zone on the same windows.

Neither step waits for the full archive: each starts as soon as a few coherent periods exist
(all the products of the comparison plus ERA5 truth on the same windows, consecutive months for
30-day replays) and is extended as the downloads progress.

## WP5 — Ensemble construction experiments

Question: is it worth building our own ensemble from several forecast sources, accounting for the
strengths and weaknesses of each? Expected a priori: most of the gain comes from calibration (speed
bias by lead and region, spread matched to the real error), which targets the intensity-type errors
S5 found costly; mixing two physical models brings little when one dominates; a physical + AI
mixture (less correlated errors) is the most promising combination.

| Id | Ensemble | Training (calibration / weights) |
|---|---|---|
| E-S6-1 | ECMWF ENS alone (reference) | none |
| E-S6-2 | ECMWF ENS calibrated: speed bias per lead and region, spread scaling per lead | past period only (rolling or leave-period-out) |
| E-S6-3 | ECMWF ENS + GEFS ENS, members weighted by past performance (e.g. BMA / CRPS-optimal weights) | past period only |
| E-S6-4 | ECMWF ENS + AIFS (AIFS single and, if available in the open archive, AIFS ENS) | past period only |

Protocol
1. **Start as soon as enough coherent data exist**: common initialisation dates for all the
   products of an experiment, at least 3 months, a separate training period strictly earlier than
   the test period (no look-ahead), the availability latency of each source respected (a member is
   usable only after its real publication time).
2. **Cheap screening first**: router-view scores of each ensemble (CRPS of wind speed, ensemble-mean
   RMSE, spread/skill ratio, speed bias, bias / amplitude / phase decomposition, reliability of
   P(TWS in the productive band)), by lead 0–5 d.
3. **Router replay** only for the best variants (WP4 machinery), paired against E-S6-1.
4. **Extend and robustify**: re-run on every new coherent period (automatic score update), report
   per season and per year; a result is retained only if its sign holds over at least two years
   and in winter and summer; confidence intervals by block bootstrap over inits (weekly blocks).
5. Track every run (MLflow, WP8 of S5) with code version, data versions (Release assets and their
   manifests) and the training / test periods.

Status (2026-11-14): data for E-S6-1/2 available for 2023-01 → 2023-06 (ENS) and growing; GEFS ENS
2023–2025 complete; AIFS 02/2024 → 02/2025. ENS 2024–2025 downloads in progress (bottleneck, ≈ 3 days).
