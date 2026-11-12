# Experiment tracking

Every simulated case (S5 campaign onwards) is recorded as one **MLflow** run (Apache-2.0, free,
self-hosted). The store is local and private: results are derived from confidential client data
(ERA5 extraction, BETA polars), so nothing is sent to a cloud service.

## What is recorded

| Kind | Keys | Meaning |
|---|---|---|
| Code version (tags) | `code.commit`, `code.branch`, `code.dirty` | git SHA of this repo; `True` if `src/` or `scripts/` had uncommitted changes when the case ran. `code.source=retro-import` marks cases recorded after the fact. |
| Data version (tags) | `data.commit`, `data.era5_sha`, `data.era5_kind`, `data.era5_files`, `data.polar_sha`, `data.year` | git SHA of the private data repo; SHA-256 fingerprints (16 hex) of the ERA5 GRIB files and BETA polar CSVs actually read. Two runs with the same fingerprints used byte-identical inputs. |
| Case (tags) | `case_id`, `router`, `window`, `router_ovr`, `env_ovr`, `campaign`, `sprint` | identity and the overrides that define the variant |
| Parameters | `router.*`, `env.*`, `window.start`, `window.days`, `seed` | full configuration with defaults expanded (not only the overrides) |
| Metrics | `cf_pct`, `energy_mwh`, `hold_share`, `distance_km`, `manoeuvres_per_day`, `storm35_h`, `storm45_h`, `min_coast_margin_km`, `coast_violations`, `guard_interventions`, `wall_s`, `cpu_s`, `peak_rss_mb`, ... | results of the case; `segment_cf_pct` is a per-10-day series |

## Where it lives

* Store: `outputs/tracking/mlflow.db` (SQLite, ~8 MB for 400 runs) and `outputs/tracking/artifacts/`.
  `outputs/` is git-ignored on purpose (confidential).
* Override with `HORIZON_MLFLOW_URI` (any MLflow URI, e.g. a self-hosted MLflow server);
  disable with `HORIZON_TRACKING=0`. Install with `pip install -e .[tracking]`.
* Recording is automatic in `scripts/s5/s5lib.run_case` (best effort: a tracking failure is logged
  and never fails a simulation). Each result JSON also carries the same `versions` block.
* Retro-import of finished cases: `python3 scripts/tracking/import_s5.py` (idempotent).

## Browsing and querying

```bash
mlflow ui --backend-store-uri sqlite:///outputs/tracking/mlflow.db   # http://127.0.0.1:5000
```

In the UI: filter e.g. `params."router.name" = 'B1c_5d_REF' and params."env.error_scale" = '2.0'`,
select runs, *Compare* for parallel-coordinates / scatter plots. From Python:

```python
import mlflow
mlflow.set_tracking_uri("sqlite:///outputs/tracking/mlflow.db")
df = mlflow.search_runs(experiment_names=["S5-sensitivity"], max_results=10000)
df.groupby("params.env.error_scale")["metrics.cf_pct"].mean()
```

## Sharing the store

The SQLite file is a single portable file. Recommended: keep it next to the data, in the private
data repository (or a dedicated private repo), committed after each campaign; artifact paths are
absolute, so log artifacts only when needed. For a shared live server later, `mlflow server` with
a PostgreSQL backend keeps the same client code (set `HORIZON_MLFLOW_URI`).

## Why MLflow

Free, permissive licence, no account, works offline with one file, mature UI for run comparison,
plain SQL underneath. Weights & Biases (used before) stores everything in its cloud on the free
tier; Neptune / Comet are cloud-first; Aim is comparable but smaller; DVC is data versioning
rather than run tracking.
