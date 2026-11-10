# S4 — forecast module upgrade (notes)

`weather.forecast_model` (diagnostics: `scripts/analyze_forecast_s4.py`; tests: `tests/test_forecast_model.py`).
All new behaviour is controlled by `ForecastErrorParams`; `ForecastErrorParams.legacy()` reproduces S3 bit-for-bit.
Defaults are the NEW behaviour (consistency, latency, seasonality ON; spread_factor = 1).

* **Consistency**: latent unit fields indexed by valid time = fresh innovation per issue (A) + 24 h-knot field (B) +
  96 h-knot field (C), variance-normalised linear interpolation in issue time; fractions vs lead are hypotheses
  (`mix_a`, `mix_b`). Same construction for the truth draw, so averaging past issues keeps an error floor.
* **Latency**: `forecast(issue_s=now)` -> latest 00/06/12/18 UTC cycle with analysis <= now - 6 h (ENS) / 4 h
  (`product="control"`); `ens.issue_s` = analysis, valid times from analysis to >= now + horizon. Analysis clamped to
  t = 0 at mission start (no earlier truth). `forecast_cycle(analysis, ...)` = no latency logic.
* **Seasonality** (HYPOTHESIS, 15 % on displacement/amplitude scales, peak 15 Jan; spec 2.8.4 is qualitative only).
* `spread_factor` kappa < 1: under-dispersion. `forecast_members` lazy generator; `ensemble_nbytes`.
* Caveat: `ForecastProvider` still passes `issue_s=now`; fine, latency is applied inside the weather object.
  Policies must use `ens.issue_s` for lead. Runtime ~1.5x the S3 model per member.
