# HORIZON — Conventions (binding contract for all modules)

Convention bugs are the #1 failure mode of routing projects (spec DES-860 §7.1.2).
Every module MUST follow this file. Any deviation is a bug.

## 1. Units (internal)

| Quantity | Internal unit | Notes |
|---|---|---|
| Speeds (wind, ship, current) | **m/s** | knots only at I/O boundaries and in human-readable reports |
| Distances | **m** (projected), NM only in reports | |
| Time | **s** (durations), `numpy.datetime64[s]` UTC (instants) | Everything UTC. No local time anywhere. |
| Power | **kW** | sanity range for net power: [-500, 3000] kW |
| Energy | **kWh** | |
| Angles in public APIs and tables | **degrees** | radians allowed inside numerical kernels only |
| Arrays | `float32` for fields/tables, `float64` for scalar maths and accumulators | |

Conversion constants live in `horizon.core.units` only. `KNOT = 1852/3600 m/s` exactly.

## 2. Wind vector

* Wind is always stored as Cartesian components **(u, v) in m/s, "toward" (oceanographic/ERA5 sense)**:
  `u` = eastward component of air motion, `v` = northward component.
  This is exactly what ERA5 `u10`/`v10` contain.
* Meteorological direction (`wdir_from`) = direction the wind **comes from**, degrees clockwise from
  true north. Conversion functions exist only in `horizon.core.wind`. Nowhere else.
* Wind fields are interpolated **in (u, v) components**, never in (speed, direction).

## 3. Headings and TWA

* Heading `psi`: true course over ground, degrees clockwise from true north, in [0, 360).
  Ship velocity unit vector = `(sin psi, cos psi)` in (east, north).
* **TWA** (true wind angle) ∈ [0°, 180°]: angle between the ship heading and the direction the wind
  **comes from**. TWA = 0° → head to wind (close-hauled side, negative-power zone);
  TWA = 90° → beam reach (optimum); TWA = 180° → dead downwind.

  `TWA = arccos( -(W · ê_psi) / |W| )`  with W the "toward" wind vector.

  **Spec erratum (DES-860 §2.2.6):** the spec writes `TWA = arccos(W·U / |W||U|)` with W in the
  "toward" convention, which yields 0° for downwind — a 180° error. This code uses the formula above.
* Tack (amure) sign: `tack = +1` starboard (wind from the starboard/right side), `-1` port.
  Signed TWA ∈ (-180, 180]: positive = wind from starboard.
* Polar is tabulated on the half-plane [0, 180] assuming port/starboard symmetry (to be confirmed
  by naval architect, spec §7.5.3). APIs accept signed TWA and take `abs()` until told otherwise.

## 4. Space

* Geographic coordinates: (lat, lon) degrees WGS84, lon ∈ [-180, 180).
* Planning grids are **regular grids in a projected CRS** (default: Lambert Azimuthal Equal-Area
  centred on the basin), never lat-lon grids (spec §4.7.2). See `horizon.geo.grid.Grid`.
* Array layout: fields are `(T, Ny, Nx, 2)` float32 C-contiguous, time first; index `[j, i]` = (y, x).
* Projected axes: x eastward, y northward, metres. Grid-north ≠ true north away from the centre:
  any heading conversion must use `Grid.grid_convergence` (or pyproj) — do not assume equality.

## 5. Kinematics

Ground velocity: `x_dot = U (sin psi, cos psi) + c(x, t) + k_L |W| sin(TWA) n_lee`
where `n_lee` is the unit normal pointing to leeward (perpendicular to the heading, on the side
away from the wind), i.e. leeway = `k_L` x the cross-heading wind component. `k_L` (leeway
coefficient) default 0.03, configurable.

**Deliberate deviation from the spec's literal formula** (`k_L |W| n_lee`, magnitude independent
of TWA): the literal form is discontinuous when the wind is along the heading. The `sin(TWA)`
form is C^1, zero head/downwind, identical on a beam reach, and required by the gradient-based NLP.

## 6. Ship and power polar

The ship is sail-propelled (two Flettner rotors, auxiliary electric propeller) and carries a wind
turbine. The polar `P[TWS, TWA, U]` is **net** electrical power [kW]: turbine gross output minus
propulsion consumption (Flettner rotors + auxiliary propeller). Net power can therefore be negative
(close-hauled, high ship speed). Client statement, 2026-11-10.

## 7. Code style

* Python ≥ 3.11, English everywhere (code, comments, docstrings, commit messages).
* NumPy-style docstrings with units in every parameter description, e.g. `tws : float  [m/s]`.
* Every public function has a unit test. Physical sanity assertions in tests (power ranges, etc.).
* Hot loops: Numba `@njit(cache=True)`; no Python callbacks inside kernels.
* Reproducibility: any randomness takes an explicit `numpy.random.Generator` or seed.
* Spec references in docstrings as `(DES-860 §x.y)`. Never copy spec text into the repository:
  the spec is CONFIDENTIAL and is not part of the repo.
