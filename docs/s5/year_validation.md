# HORIZON v2 — year-long validation (2015-01-01 + 350 d, persistent ship)

Campaign `scripts/s5/campaign_year.yaml`; S5 environment (manoeuvre losses, synthetic forecasts, d_min 20 km); terminal climatology in-sample for every router (a year-long window cannot leave its own months out; the leak is ±0.1 pt on 30-day windows, see v2_validation.md).

| Router | Seed | CF [%] | Energy [MWh] | h > 35 kn | h > 45 kn | Manoeuvres/day | Refiner not converged | CPU [min] |
|---|---|---|---|---|---|---|---|---|
| B0 poste fixe | 0 | 56.8 | 14324 | 472 | 14.0 | 0.00 | n/a | 0 |
| v1 (B1c) | 1 | 78.5 | 19785 | 387 | 13.0 | 2.46 | 196 / 1400 | 60 |
| HORIZON v2 | 1 | 78.7 | 19827 | 268 | 13.5 | 2.72 | 1 / 1400 | 27 |
| HORIZON v2 | 2 | 79.7 | 20080 | 334 | 5.2 | 2.53 | 0 / 1400 | 27 |
| Oracle | 0 | 87.4 | 22027 | 394 | 9.8 | 2.21 | n/a | 61 |

Paired differences over the 35 ten-day segments [CF points]:

| Comparison | Mean | SE | Segments won |
|---|---|---|---|
| v2 − v1 (seed 1) | +0.17 | 0.93 | 19/35 |
| v2 seed 2 − seed 1 | +1.00 | 1.02 | 18/35 |
| v2 − B0 | +21.84 | 2.06 | 35/35 |
| Oracle − v2 | +8.73 | 1.05 | 35/35 |
| Oracle − v1 | +8.90 | 0.95 | 35/35 |
