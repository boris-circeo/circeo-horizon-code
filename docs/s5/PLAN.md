# Sprint 5 — Consolidation: understand, challenge, refine (HORIZON v2)

Client brief (2026-11-11): no new router complexity (that is S6). Instrument and run code, test
scenarios and inspector to understand ocean weather, the problem, and the capabilities/limits of the
routing approaches; identify what matters and its sensitivity — especially to forecast quality and
to the quality of the ERA5-based forecast simulation. Methodically review every hypothesis/postulate of
the v1 design note (DES-860 rev A) and challenge each a-priori conclusion. Be paranoid about
assumptions, errors, biases, limitations — in the v1 note AND in our own results. Produce HORIZON v2
(refined algorithm + test environment), an external critical review (refactor, bugs, CF on a target
scenario, tuning simplicity/robustness, compute speed), push code to
github.com/boris-circeo/circeo-horizon-code, and a v2 description document (same production chain as
v1: markdown → pandoc → HTML/CSS+KaTeX → Chromium → PDF) whose generation code lives in this repo.

## Work packages

| WP | Content | Output |
|---|---|---|
| WP1 | Hypothesis register: every assumption / quantitative claim / design conclusion of v1, with the test that can confirm or refute it | `docs/s5/hypotheses.yaml`, `docs/s5/hypotheses.md` |
| WP2 | Ocean-weather phenomenology on ERA5 2015: distributions, persistence of productive conditions (Eulerian & Lagrangian), space/time decorrelation, system translation speeds vs ship speed, calms, seasonality, reachability, value of mobility | `docs/s5/weather_analysis.md`, figures |
| WP3 | Test-environment realism: manoeuvre (tack/gybe/heading-change) production losses charged by the simulator; forecast-model knobs (error scale, latency, consistency, dispersion); polar model error | code + tests |
| WP4 | Sensitivity campaign (long, resumable, supervised): forecast quality, latency, horizon, replan period, refiner, terminal value, manoeuvre cost, polar error, d_min, ensemble knobs, grid | `outputs/s5/`, `docs/s5/sensitivity.md` |
| WP5 | Verdict per hypothesis (confirmed / refuted / nuanced / untestable) with evidence | register updated |
| WP6 | HORIZON v2: refined algorithm & defaults from WP1-5; external critical reviewer (refactor, bugs, performance, tuning, speed) | code, benchmark |
| WP7 | v2 document (FR, CIRCEO chain) with REX and typical results; inspector "Sensitivity" view | `docdev/` generator, PDF |
| WP8 | Experiment tracking (client request, 2026-11-12): every simulated case recorded with code version (git commit, dirty flag), weather/polar data version (data-repo commit + content fingerprints), full parameters and results; free, local and private store; retro-import of the 398 S5 cases | MLflow (SQLite) `outputs/tracking/`, `src/horizon/tracking.py`, `docs/TRACKING.md` |

## Target scenario ("bench-6")
Six 30-day windows of 2015 starting 1 Jan, 1 Mar, 1 May, 1 Jul, 1 Sep, 1 Nov, from the annual best
offshore point; metric = mean capacity factor [%] over windows, paired comparisons, gap to
Oracle_REF_H in points. Final v2 validation on the full persistent year.

## Autonomy
Long runs are resumable (one result file per run, monthly checkpoints). A supervisor script relaunches
missing/killed workers; scheduled check-ins in this session relaunch it after VM restarts and report
progress (~1 h during the first 6 h, then ~3 h).
