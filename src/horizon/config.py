"""Single typed configuration of a HORIZON router and the factory that builds it.

Replaces the copy-pasted ``build`` / ``make_policy`` / ``build_router`` of the S3 / S4 / S5 scripts.
Defaults are the S4/S5 production values (``B1c_5d_REF``); every field is validated at
construction so that a mistyped override fails loudly instead of silently running another router.

Only the fields marked KEY change results materially (S5 review, tuning table): ``kind``,
``horizon_days``, ``refiner_h``, ``terminal``, ``members``/``k`` (ENS). The remaining fields are
fixed at their defaults in production.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

__all__ = ["HorizonConfig", "PRESETS", "make_policy"]

KINDS = ("B1", "ENS", "ORACLE_H")


@dataclass(frozen=True)
class HorizonConfig:
    """Router configuration (defaults = production ``B1c_5d_REF``).

    Attributes
    ----------
    kind : {"B1", "ENS", "ORACLE_H"}  KEY. Deterministic DP on the control / reduced-ensemble
        two-stage DP / hindsight DP on the truth (not causal).
    horizon_days : float [d]  KEY. DP horizon (B1 5, ENS 10, ORACLE_H 15).
    replan_h : float [h]  Replan period (multiple of the simulation step; 6).
    refiner_h : float [h]  KEY. Continuous refiner horizon (48); 0 disables the refiner.
    terminal : {"clim", "zero"}  KEY. DP terminal value (climatological hold power / none).
    terminal_days : float [d]  Time scale of the climatological terminal value (5).
    max_span : int  DP macro-arc span (2; 1 = plain ring, 3 = +3 % energy at ~2x cost).
    d_min_km : float [km]  Coast clearance (20).
    members, k, gamma, alpha : ENS only. Ensemble size (20), scenarios (6), CVaR weight (0 =
        risk neutral) and tail mass (0.2).
    mean_members, blend_h : int, float [h]  ``mean_members > 0`` runs the router on the mean of
        that many members (B1m; ``blend_h > 0``: control up to that lead).
    router_polar : {"nominal", "truth"}  Polar believed by the router.
    storm_kn : float [kn]  > 0 adds a steep penalty above this wind speed in the router polar.
    """

    kind: str = "B1"
    horizon_days: float = 5.0
    replan_h: float = 6.0
    refiner_h: float = 48.0
    terminal: str = "clim"
    terminal_days: float = 5.0
    max_span: int = 2
    d_min_km: float = 20.0
    members: int = 20
    k: int = 6
    gamma: float = 0.0
    alpha: float = 0.2
    mean_members: int = 0
    blend_h: float = 0.0
    router_polar: str = "nominal"
    storm_kn: float = 0.0

    def __post_init__(self):
        def bad(msg):
            raise ValueError(f"HorizonConfig: {msg}")
        if self.kind not in KINDS:
            bad(f"kind {self.kind!r} not in {KINDS}")
        if not 0.5 <= self.horizon_days <= 30:
            bad("horizon_days must be in [0.5, 30]")
        if self.replan_h <= 0 or self.replan_h > 48:
            bad("replan_h must be in (0, 48]")
        if self.refiner_h < 0 or (0 < self.refiner_h < 3):
            bad("refiner_h must be 0 (off) or >= 3")
        if self.terminal not in ("clim", "zero"):
            bad("terminal must be 'clim' or 'zero'")
        if self.max_span not in (1, 2, 3):
            bad("max_span must be 1, 2 or 3")
        if not 0 < self.d_min_km < 200:
            bad("d_min_km must be in (0, 200)")
        if self.kind == "ENS":
            if not 2 <= self.members <= 51 or not 2 <= self.k <= self.members:
                bad("ENS needs 2 <= k <= members <= 51")
            if not 0 <= self.gamma <= 1 or not 0 < self.alpha <= 1:
                bad("gamma in [0, 1], alpha in (0, 1]")
        if self.mean_members < 0 or self.blend_h < 0:
            bad("mean_members and blend_h must be >= 0")
        if self.router_polar not in ("nominal", "truth"):
            bad("router_polar must be 'nominal' or 'truth'")
        if self.storm_kn < 0:
            bad("storm_kn must be >= 0")

    def with_(self, **kw) -> HorizonConfig:
        """Copy with overrides (unknown names raise ``ValueError``)."""
        names = {f.name for f in fields(self)}
        bad = set(kw) - names
        if bad:
            raise ValueError(f"HorizonConfig: unknown fields {sorted(bad)}")
        return replace(self, **kw)

    @classmethod
    def preset(cls, name: str, **overrides) -> HorizonConfig:
        """Named router of the S4/S5 campaigns (``PRESETS``) with overrides."""
        if name not in PRESETS:
            raise ValueError(f"unknown router preset {name!r}; known: {sorted(PRESETS)}")
        return PRESETS[name].with_(**overrides)


PRESETS = {
    "B1c_5d_REF": HorizonConfig(),
    "B1m_5d_REF": HorizonConfig(mean_members=10),
    "ENS_REF": HorizonConfig(kind="ENS", horizon_days=10.0),
    "Oracle_REF_H": HorizonConfig(kind="ORACLE_H", horizon_days=15.0),
}


def make_policy(cfg: HorizonConfig, polar, hold, coast, clim_kw=None, weather=None):
    """Build the (refined) routing policy of ``cfg``.

    Parameters
    ----------
    cfg : HorizonConfig
    polar, hold, coast : router polar table, hold curve, coast model (after any
        ``router_polar`` / ``storm_kn`` transformation done by the caller).
    clim_kw : ndarray (Ny, Nx) [kW], optional  Climatological hold power (required if
        ``cfg.terminal == "clim"``).
    weather : source with ``truth(...)``  Required for ``ORACLE_H`` only.
    """
    from horizon.sim.policies import DeterministicMPCPolicy
    from horizon.sim.policies_ens import EnsembleMPCPolicy
    from horizon.sim.policies_refine import OracleHorizonRefinedPolicy, RefinedMPCPolicy

    if cfg.terminal == "clim" and clim_kw is None:
        raise ValueError("terminal='clim' needs clim_kw")
    clim = clim_kw if cfg.terminal == "clim" else None
    dmin = cfg.d_min_km * 1e3
    refkw = {} if cfg.refiner_h == 48.0 else {"horizon_h": cfg.refiner_h}
    if cfg.kind == "ORACLE_H":
        if weather is None:
            raise ValueError("ORACLE_H needs weather")
        return OracleHorizonRefinedPolicy(weather, polar, hold, coast,
                                          horizon_days=cfg.horizon_days, terminal_clim_kw=clim,
                                          terminal_days=cfg.terminal_days, d_min_m=dmin, **refkw)
    if cfg.kind == "B1":
        base = DeterministicMPCPolicy(polar, hold, coast, horizon_days=cfg.horizon_days,
                                      d_min_m=dmin, terminal_clim_kw=clim,
                                      terminal_days=cfg.terminal_days, max_span=cfg.max_span)
    else:
        base = EnsembleMPCPolicy(polar, hold, coast, horizon_days=cfg.horizon_days,
                                 n_members=cfg.members, k=cfg.k, gamma=cfg.gamma,
                                 alpha=cfg.alpha, d_min_m=dmin, terminal_clim_kw=clim,
                                 terminal_days=cfg.terminal_days, max_span=cfg.max_span)
    pol = base if cfg.refiner_h <= 0 else RefinedMPCPolicy(base, **refkw)
    if cfg.mean_members > 0:
        from horizon.sim.policies_simple import ForecastTransformPolicy
        pol = ForecastTransformPolicy(pol, cfg.mean_members,
                                      cfg.blend_h if cfg.blend_h > 0 else None)
    return pol
