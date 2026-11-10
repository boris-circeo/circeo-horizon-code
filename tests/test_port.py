"""S4 harbour-exit corridor: d_min ramps from ~1 km at the port to 20 km at 40 km (consistent in
DP, refiner and simulator through the relaxed SDF)."""

import numpy as np
import pytest

from horizon.geo.coast import SDF_TOL_M, CoastModel, port_corridor, signed_distance
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import (
    DeterministicMPCPolicy,
    DirectPowerModel,
    EnvelopePowerModel,
    OraclePolicy,
    run_mission,
)
from horizon.sim.policies_refine import RefinedMPCPolicy
from horizon.weather.fields import Ensemble, WindField

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
H = 3600.0
D_MIN = 20e3


@pytest.fixture(scope="module")
def polar():
    return synthetic_polar()


@pytest.fixture(scope="module")
def hold(polar):
    return hold_power_curve(polar)


@pytest.fixture(scope="module")
def pm(polar, hold):
    return EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))


@pytest.fixture(scope="module")
def world():
    g = Grid.from_bbox(-12, 4, 38, 54, 40e3)
    X, Y = g.xy_mesh()
    x0, y0 = g.to_xy(-4.0, 46.0)
    i_land = int(np.ceil((x0 + 140e3 - g.x0) / g.dx))  # first land column
    xc = g.x0 + (i_land - 0.5) * g.dx  # coastline, midway between the last sea and first land node
    land = X > xc
    coast = CoastModel(g, signed_distance(g, land))
    port = tuple(float(v) for v in g.to_lonlat(xc - 2e3, y0 + 20e3))  # 2 km off the coastline
    # wind hot spot 80-160 km offshore: leaving the port pays
    d = (xc - X) / 1e3
    speed = 4.0 + 9.0 * np.exp(-((d - 120.0) / 45.0) ** 2)
    t = np.arange(0, 8 * 24 * H + 1, 3 * H)
    uv = np.zeros((t.size,) + g.shape + (2,), np.float32)
    uv[..., 1] = -speed  # blowing south: beam reach for a ship going west/east
    uv[..., 0] = -0.3 * speed
    return g, coast, WindField(g, EPOCH, t, uv), port, xc


class FixedWeather:
    def __init__(self, truth):
        self.truth_wf, self.grid = truth, truth.grid

    def forecast(self, issue_s, horizon_s, n_members, dt_s=10800.0, seed_offset=0):
        from horizon.dp.solver import resample_wind
        t = issue_s + dt_s * np.arange(int(round(horizon_s / dt_s)) + 1)
        return Ensemble(self.grid, EPOCH, issue_s, t, resample_wind(self.truth_wf, t)[None],
                        np.ones(1))


def test_corridor_field(world):
    g, coast, _, port, _ = world
    cc = port_corridor(coast, *port, d_min=D_MIN, d_port=1e3, ramp_m=40e3)
    px, py = g.to_xy(*port)
    d_eff = lambda x, y: D_MIN - (cc.sdf_at(x, y) - coast.sdf_at(x, y))  # noqa: E731
    assert float(d_eff(px, py)) == pytest.approx(1e3, abs=1.0)  # ~1 km at the port
    assert float(cc.sdf_at(px, py)) >= D_MIN - SDF_TOL_M  # the port itself is feasible
    for ang in np.radians([90.0, 180.0]):  # ramp up with distance, nominal beyond ~ramp + 1.5 dx
        d = [float(d_eff(px + r * np.cos(ang), py + r * np.sin(ang)))
             for r in (0.0, 10e3, 20e3, 30e3, 40e3, 60e3, 80e3)]
        assert all(b >= a - 1.0 for a, b in zip(d[:-1], d[1:], strict=True))
        assert d[-1] == pytest.approx(D_MIN, abs=1.0) and d[0] < 2e3
    assert np.allclose(cc.true_sdf, coast.sdf, atol=1e-2)
    assert np.all(cc.relax >= 0)
    far = np.hypot(*(np.array(g.xy_mesh()) - np.array([px, py])[:, None, None])) > 40e3 + 1.5 * g.dx
    assert np.all(cc.relax[far] == 0)
    with pytest.raises(ValueError):  # a port on land
        port_corridor(coast, *g.to_lonlat(px + 300e3, py))


def test_without_corridor_start_in_port_violates_nominal_margin(world, polar, hold, pm):
    g, coast, truth, port, _ = world
    pol = DeterministicMPCPolicy(polar, hold, coast, horizon_days=2.0)
    res = run_mission(pol, FixedWeather(truth), truth, port, 2 * 24 * H, pm, coast)
    assert coast.sdf_at(res.x[0], res.y[0]) < D_MIN - 10e3  # starts inside the nominal margin
    assert res.coast_violations > 0  # (a violation of the nominal 20 km at the start)
    assert res.guard_interventions == 0  # the guard lets a ship in the margin sail OUT of it


@pytest.mark.parametrize("name", ["DP", "REF", "ORACLE"])
def test_departure_from_port(name, world, polar, hold, pm):
    g, coast, truth, port, xc = world
    cc = port_corridor(coast, *port, d_min=D_MIN, d_port=1e3, ramp_m=40e3)
    dur = 3 * 24 * H
    if name == "DP":
        pol = DeterministicMPCPolicy(polar, hold, cc, horizon_days=2.0)
    elif name == "REF":
        pol = RefinedMPCPolicy(DeterministicMPCPolicy(polar, hold, cc, horizon_days=2.0))
    else:
        pol = OraclePolicy(truth, polar, hold, cc, dur)
    res = run_mission(pol, FixedWeather(truth), truth, port, dur, pm, cc)
    assert res.coast_violations == 0  # ramped constraint respected at every step
    assert res.guard_interventions == 0
    assert res.min_margin_m >= -SDF_TOL_M
    true = coast.sdf_at(res.x, res.y)
    assert true[0] < 5e3  # starts in the harbour (1.6 km of clearance...)
    assert true.max() > 80e3  # ... and reaches the open sea
    assert np.all(true > 0.0)  # never on land
    # clearance along the exit ramps up with distance from the port
    px, py = g.to_xy(*port)
    r = np.hypot(res.x - px, res.y - py)
    req = 1e3 + 19e3 * np.minimum(r / (40e3 + 1.5 * g.dx), 1.0)  # effective (grid) ramp
    assert np.all(true >= req - 1.0)
    assert res.energy_kwh[-1] > 0.0
