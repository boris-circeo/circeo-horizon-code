# Milestones

Git tags cannot be pushed from the development environment (proxy policy), so sprint milestones
are recorded here as commit ids on `main`. To create the tags locally:
`git tag <name> <commit> && git push origin --tags`.

| Milestone | Commit | Content |
|---|---|---|
| s1 | a180ea6 | Closed-loop causal simulator, baselines B0/B1, hindsight oracle, synthetic weather, DP kernel |
| s2 | 0d9ad35 | Ensemble reduction (EOF + PAM), stochastic DP, refiner variants, web inspector, S2 review |
| s3 | b24c413 | ERA5 ingestion and backtest, real BETA polar, macro arcs, Oracle_REF, S3 review |
| s4 | ab14496 | Forecast model v2, year-long persistent runs, Lorient departures, V_theta, S4 review |
| inspector-4.7.1 | 9268aff | Inspector v4.7.1 (Apple / Safari / mobile robustness, lite build) |
| s5-campaign | 54aadcb | Code state of the 398-case S5 sensitivity campaign (src unchanged since 8d57542) |
| s5-review | a4a97ae | External review merged (HorizonConfig, speed-ups, fixes) |
| s5-tracking | 3f14346 | MLflow experiment tracking (code/data versions, params, metrics) |
| horizon-v2 | 2254722 | HORIZON_V2 router (3 d DP, leak-free terminal, 24 h deterministic refiner) |
| s5 | (this commit's successor: see `git log`) | S5 deliverables: sensitivity, verdicts, v2 + year validation, doc v2, inspector v4.8 |
