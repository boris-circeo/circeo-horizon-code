"""Shared setup for the Sprint-5 ocean-weather analyses (ERA5 2015, 40 km grid)."""
import warnings
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/s5/weather"
OUT.mkdir(parents=True, exist_ok=True)
KN = 1852 / 3600
POLAR_DIR = "/home/claude/circeo-horizon-data/power-polar"
SEASONS = {"DJF": (12, 1, 2), "MAM": (3, 4, 5), "JJA": (6, 7, 8), "SON": (9, 10, 11)}
MD = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def setup():
    from horizon.geo.grid import Grid
    from horizon.geo.coast import build_basin_coast
    from horizon.weather.era5 import ERA5Archive, ERA5_BOX
    from horizon.polar.beta import load_beta_polar
    from horizon.polar.envelope import build_envelope
    from horizon.polar.climatology import hold_power_vs_tws
    g = Grid.from_bbox(*ERA5_BOX, 40e3)
    arc = ERA5Archive(ROOT / "data/cache/era5", g, year=2015)
    c0 = build_basin_coast(40e3, bbox=ERA5_BOX)
    land = (c0.sdf < 0)
    sea = ~land & ~arc.outside
    pol = load_beta_polar(POLAR_DIR)
    env = build_envelope(pol)
    tws, ph = hold_power_vs_tws(env)
    return g, arc, sea, land, env, tws, ph


def month_of_hour(arc):
    m = np.concatenate([np.full(h, i + 1) for i, h in enumerate(arc._hours)])
    return m


def season_masks(arc):
    m = month_of_hour(arc)
    return {s: np.isin(m, v) for s, v in SEASONS.items()}
