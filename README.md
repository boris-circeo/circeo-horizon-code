# HORIZON — energy router for a fleet of wind-energy ships (PoC)

Proof of concept of the HORIZON routing architecture (CIRCEO design note DES-860, not included
in this repository): a learned policy-consistent value function (offline), an ensemble stochastic
dynamic programme on a spatio-temporal graph (online), and a continuous optimal-control refiner.

**Status:** Sprint 1 done — synthetic weather, DP core, closed-loop backtest, first regret figure. See docs/sprints/

## Layout

```
src/horizon/
  core/    units, wind conventions, kinematics
  geo/     projected planning grids, coastline / signed distance function
  polar/   power polar model and derived tables
tests/     unit and physical sanity tests
docs/      CONVENTIONS.md (binding), LICENSES.md, sprint reports
```

## Quick start

```bash
pip install -e ".[dev]"
pytest
```

All internal quantities use SI units (m/s, m, s) and kW/kWh; see `docs/CONVENTIONS.md`.

Proprietary — CIRCEO SAS. Third-party licences: `docs/LICENSES.md`.
