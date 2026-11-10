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
| shapely | BSD-3 | OK | geometry |
| pyshp | MIT | OK | reading shapefiles |
| xarray / zarr / netCDF4 | Apache-2.0 / MIT / MIT | OK | data I/O (optional) |
| pytest, ruff | MIT | OK (dev only) | tests, lint |
| casadi (planned S2) | **LGPL-3** | OK, weak copyleft — report | NLP refiner |
| ipopt (planned S2) | EPL-2.0 | OK, weak copyleft — report | NLP solver (with MUMPS, CeCILL-C) |
| HSL MA27/MA57 | proprietary/academic | **EXCLUDED** | — |
| lightgbm (planned S3) | MIT | OK | value function |
| scikit-learn | BSD-3 | OK | PCA |
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
