"""HorizonConfig validation and factory (S5 external review)."""
import numpy as np
import pytest

from horizon.config import PRESETS, HorizonConfig, make_policy
from horizon.geo.coast import build_basin_coast
from horizon.polar import hold_power_curve, synthetic_polar


def test_defaults_are_production_b1c():
    c = HorizonConfig()
    assert (c.kind, c.horizon_days, c.refiner_h, c.terminal, c.max_span) == ("B1", 5.0, 48.0,
                                                                               "clim", 2)


@pytest.mark.parametrize("kw", [dict(kind="X"), dict(horizon_days=0.0), dict(refiner_h=1.0),
                                dict(terminal="foo"), dict(max_span=4), dict(d_min_km=-1.0),
                                dict(kind="ENS", members=5, k=6), dict(router_polar="x")])
def test_validation_rejects(kw):
    with pytest.raises(ValueError):
        HorizonConfig(**kw)


def test_unknown_override_and_preset():
    with pytest.raises(ValueError):
        HorizonConfig().with_(horizon_day=3)
    with pytest.raises(ValueError):
        HorizonConfig.preset("nope")
    assert set(PRESETS) == {"B1c_5d_REF", "B1m_5d_REF", "ENS_REF", "Oracle_REF_H"}


def test_factory_builds_each_kind():
    coast = build_basin_coast(40e3)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    clim = np.zeros(coast.grid.shape, np.float32)
    p = make_policy(HorizonConfig(), polar, hold, coast, clim)
    assert p.base.horizon_s == 5 * 86400 and p.base.terminal_clim_kw is clim
    p = make_policy(HorizonConfig(kind="ENS", horizon_days=10.0, terminal="zero", refiner_h=0),
                    polar, hold, coast)
    assert p.n_members == 20 and p.k == 6 and p.terminal_clim_kw is None
    p = make_policy(HorizonConfig.preset("B1m_5d_REF", refiner_h=24.0), polar, hold, coast, clim)
    assert p.n_members == 10 and p.inner.horizon_s == 24 * 3600
    with pytest.raises(ValueError):
        make_policy(HorizonConfig(), polar, hold, coast)  # clim missing
    with pytest.raises(ValueError):
        make_policy(HorizonConfig.preset("Oracle_REF_H"), polar, hold, coast, clim)


def test_s5_router_defaults_match_presets():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "s5"))
    import s5lib as L
    for name in ("B1c_5d_REF", "B1m_5d_REF", "ENS_REF", "Oracle_REF_H"):
        spec = L.normalise({"router": {"name": name}, "start": "2015-01-01"})
        got = L.router_config(name, L.full_router(spec), L.full_env(spec))
        assert got == PRESETS[name], name


def test_policy_counters_survive_checkpoint_state():
    """Bug (S5 review): fallback counters were lost on resume; they now travel in the state."""
    coast = build_basin_coast(40e3)
    polar = synthetic_polar()
    hold = hold_power_curve(polar)
    clim = np.zeros(coast.grid.shape, np.float32)
    p = make_policy(HorizonConfig(), polar, hold, coast, clim)
    p.n_dp_fallback, p.n_warm_start, p.base.n_hold_fallback = 3, 2, 1
    st = p.get_state()
    q = make_policy(HorizonConfig(), polar, hold, coast, clim)
    q.set_state(__import__("json").loads(__import__("json").dumps(st)))
    assert (q.n_dp_fallback, q.n_warm_start, q.base.n_hold_fallback) == (3, 2, 1)
    m = make_policy(HorizonConfig(mean_members=4), polar, hold, coast, clim)  # forwarded
    assert hasattr(m, "get_state") and m.n_refined == 0
