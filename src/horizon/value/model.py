"""Learned policy-consistent terminal value V_theta and its evaluation on the planning grid."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from horizon.value.features import FEATURE_NAMES, feature_matrix, forecast_feature_fields

__all__ = ["ValueModel", "ValueTerminal", "fit_value_model"]


@dataclass
class ValueModel:
    """Gradient-boosted regressor of the energy-to-go [kWh] over ``horizon_s`` (LightGBM).

    Attributes
    ----------
    booster : lightgbm.LGBMRegressor. features : tuple of names. horizon_s : float [s].
    meta : dict  Free text / provenance (target kind, held-out month, n_train, ...).
    """

    booster: object
    features: tuple = FEATURE_NAMES
    horizon_s: float = 5 * 86400.0
    meta: dict = field(default_factory=dict)

    def predict(self, X) -> np.ndarray:
        return np.asarray(self.booster.predict(np.asarray(X, np.float32)), float)

    def save(self, path) -> None:
        import joblib
        joblib.dump({"booster": self.booster, "features": self.features,
                     "horizon_s": self.horizon_s, "meta": self.meta}, path)

    @classmethod
    def load(cls, path) -> ValueModel:
        import joblib
        d = joblib.load(path)
        return cls(d["booster"], tuple(d["features"]), d["horizon_s"], d["meta"])


def fit_value_model(X, y, horizon_s: float = 5 * 86400.0, quantile: float | None = None,
                    params: dict | None = None, meta: dict | None = None,
                    sample_weight=None) -> ValueModel:
    """Fit a LightGBM regressor (mean, or ``quantile`` if given) on ``X, y [kWh]``."""
    import lightgbm as lgb

    p = {"n_estimators": 300, "learning_rate": 0.04, "num_leaves": 15, "min_child_samples": 25,
         "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "reg_lambda": 1.0,
         "n_jobs": 1, "verbose": -1, "random_state": 0}
    if quantile is not None:
        p.update(objective="quantile", alpha=float(quantile))
    p.update(params or {})
    m = lgb.LGBMRegressor(**p)
    m.fit(np.asarray(X, np.float32), np.asarray(y, float), sample_weight=sample_weight)
    return ValueModel(m, FEATURE_NAMES, horizon_s, dict(meta or {}, quantile=quantile,
                                                       n_train=int(len(y))))


class ValueTerminal:
    """DP terminal-value provider: ``V_theta`` evaluated on the whole grid at ``tau = t + n dt``.

    Called by :class:`horizon.value.policy.TerminalFnMPCPolicy` at every replan. It requests the
    control forecast issued at the replan time over ``[t, tau + H_T]`` (the same call as used to
    build the training features, issue ``tau - H_T``), computes the forecast features for
    ``[tau, tau + H_T]`` and predicts the value of every cell.

    Parameters
    ----------
    model : ValueModel. grid : Grid. clim_kw, sdf : (Ny, Nx) [kW], [m]. epoch : datetime64.
    tws_ax, p_ax : hold power curve. fc_dt_s : float  Forecast step used for the features (6 h).
    clip_kwh : (lo, hi)  Clip of the predicted value.
    """

    def __init__(self, model: ValueModel, grid, clim_kw, sdf, epoch, tws_ax, p_ax,
                 fc_dt_s: float = 6 * 3600.0, clip_kwh=(0.0, 4.0e5)):
        self.model, self.grid, self.clim, self.sdf = model, grid, clim_kw, sdf
        self.epoch, self.tws_ax, self.p_ax = epoch, tws_ax, p_ax
        self.fc_dt_s, self.clip = fc_dt_s, clip_kwh
        self.n_calls = 0
        X_, Y_ = grid.xy_mesh()
        self._x, self._y = X_.ravel(), Y_.ravel()

    def field(self, tau_s: float, times_s, uv) -> np.ndarray:
        """Terminal field [kWh] (Ny, Nx) for decision time ``tau_s`` given the forecast
        ``(times_s, uv (T, Ny, Nx, 2))`` issued ``H_T`` earlier."""
        h = self.model.horizon_s
        fc = forecast_feature_fields(times_s, uv, tau_s, tau_s + h, self.tws_ax, self.p_ax)
        X = feature_matrix(self.grid, self._x, self._y, tau_s, self.epoch, self.clim, self.sdf, fc)
        v = np.clip(self.model.predict(X), *self.clip)
        return v.reshape(self.grid.shape).astype(np.float32)

    def __call__(self, t_s: float, tau_s: float, provider) -> np.ndarray:
        h = self.model.horizon_s
        left = float(provider.mission_end_s) - tau_s  # mission time left after the DP window
        if left <= 0:
            return np.zeros(self.grid.shape, np.float32)
        ens = provider.forecast(issue_s=t_s, horizon_s=(tau_s - t_s) + h, n_members=1,
                                dt_s=self.fc_dt_s)
        self.n_calls += 1
        return (self.field(tau_s, ens.times_s, ens.uv[0]) * min(1.0, left / h)).astype(np.float32)
