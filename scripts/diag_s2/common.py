import numpy as np

from horizon.geo.coast import build_basin_coast
from horizon.geo.grid import Grid
from horizon.polar import hold_power_curve, synthetic_polar
from horizon.polar.envelope import build_envelope
from horizon.sim import DirectPowerModel, EnvelopePowerModel

EPOCH = np.datetime64("2026-01-01T00:00:00", "s")
DAY = 86400.0
START = (-6.5, 47.0)
def setup():
    grid = Grid.from_bbox(-45, 5, 35, 65, 40e3)
    coast = build_basin_coast(40e3)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    pm = EnvelopePowerModel(build_envelope(polar), fallback=DirectPowerModel(polar, hold))
    return grid, coast, polar, hold, pm
