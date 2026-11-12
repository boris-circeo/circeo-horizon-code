# Dependency & data licence register

Policy (decided 2026-11-10): the end product is commercial and proprietary.
Permissive licences (MIT, BSD, Apache-2.0, PSF, ISC) are preferred. Weak copyleft (LGPL, EPL, MPL,
CeCILL-C) is acceptable when dynamically linked / used unmodified as a library and must be
reported. **GPL / AGPL are forbidden**; if no alternative exists, escalate for arbitration.

## Software

| Package | Licence | Status | Used for |
|---|---|---|---|
| numpy, scipy | BSD-3 | OK | arrays, distance transforms |
| numba | BSD-2 | OK | DP kernels |
| pyproj | MIT | OK | projections |
| mlflow | Apache-2.0 | OK (optional extra `tracking`) | experiment tracking (local SQLite store, `mlflow ui`) |
| shapely | BSD-3 | OK | geometry |
| pyshp | MIT | OK | reading shapefiles |
| xarray / zarr / netCDF4 | Apache-2.0 / MIT / MIT | OK | data I/O (optional) |
| cfgrib / eccodes (python bindings + ECMWF ecCodes library) | Apache-2.0 / Apache-2.0 | OK | reading ERA5 GRIB1 (optional, `data` extra; ingestion only) |
| pytest, ruff | MIT | OK (dev only) | tests, lint |
| casadi (planned S2) | **LGPL-3** | OK, weak copyleft — report | NLP refiner |
| ipopt (planned S2) | EPL-2.0 | OK, weak copyleft — report | NLP solver (with MUMPS, CeCILL-C) |
| HSL MA27/MA57 | proprietary/academic | **EXCLUDED** | — |
| lightgbm (S4, `value` extra) | MIT | OK | learned terminal value V_theta (`horizon.value`, optional) |
| scikit-learn | BSD-3 | OK | PCA; dependency of the LightGBM sklearn API |
| matplotlib | PSF-based (BSD-compatible) | OK | figures (`value` extra, analysis scripts only) |
| joblib | BSD-3 | OK | model (de)serialisation (`value` extra) |
| `eofs` | **GPL-3** | **EXCLUDED** | replaced by in-house weighted EOF |
| `kmedoids` (PyPI) | **GPL-3** | **EXCLUDED** | replaced by in-house PAM |
| ortools (planned) | Apache-2.0 | OK | CP-SAT scheduling |

## Data

| Dataset | Licence | Notes |
|---|---|---|
| Natural Earth (coastline/land) | Public domain | PoC coastline source |
| GSHHG | LGPL-3 | candidate production coastline (data, not linked code) |
| ERA5 | Copernicus licence | commercial use allowed with attribution |
| ECMWF open data | CC-BY-4.0 | attribution |
| GEFS v12 reforecast | US public domain (NOAA) | |
| CMEMS | Copernicus Marine licence | commercial use allowed, registration |

*Not legal advice — to be validated by CIRCEO's legal counsel before commercial use.*
