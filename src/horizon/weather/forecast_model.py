"""Realistic ERA5-based forecast-error model: an exchangeable "oracle-perturbation" ensemble.

Why (S2 diagnosis): the synthetic ensemble was uninformative because its errors were structurally
unlike NWP errors. Here the truth is real ERA5 and the *forecast* is built from the truth by a
statistical error model.

Exchangeable construction
-------------------------
Let ``d_t`` and ``d_1..d_M`` be i.i.d. random perturbations of the truth ``w`` (same lead-time
dependent law). The ensemble "centre" is ``c = w - d_t`` and the members are ``m_k = c + d_k``
(member 0 is the control, just one draw). Hence the truth ``w = c + d_t`` is statistically
indistinguishable from a member: control error variance ``2 sigma_d^2``, ensemble-mean error
variance ``sigma_d^2 (1 + 1/M)`` (the mean beats the control), spread/skill ratio ~1 and a flat
rank histogram (exact when the draws are i.i.d. given ``w``).

Perturbation ``d = P(w) - w`` (all HYPOTHESES, see :class:`ForecastErrorParams`), with ``P`` the
composition of

1. a smooth random **displacement** of the field (backward warp ``w(x + delta(x))``): phase errors
   of storms; rms ``delta`` ~40 km at D1 growing to ~250 km at D7 (calibrated to the RMSE
   targets; larger 400-600 km displacements overshoot them on this real-ERA5 field);
2. a smooth multiplicative **amplitude** modulation ``1 + a(lead) * xi_a(x)``;
3. additive spatially correlated **noise** (small scales) with lead-dependent amplitude.

Every random field is spatially Gaussian-correlated and AR(1) in valid time, so a member is a
coherent trajectory. Errors at lead 0 are small (analysis error ~1 m/s).

Sprint 4 additions (all switchable in :class:`ForecastErrorParams`; ``ForecastErrorParams.legacy()``
restores the Sprint-3 behaviour bit-for-bit)
--------------------------------------------------------------------------------------------------
* **Issue-to-issue consistency** (``issue_consistency``): the unit random fields of stream ``k``
  (the truth draw ``d_t`` or member ``k``) are indexed by VALID time and refreshed as the issue
  time advances. For issue time ``i`` and lead ``L`` the unit field is
  ``Z = sum_b sqrt(f_b(L)) * eta_b(i)`` over three levels ``b``: ``A`` fresh innovation of each
  issue, ``B`` latent field interpolated (and variance-normalised) between knots every
  ``knot_b_h`` (24 h), ``C`` idem every ``knot_c_h`` (96 h). The fractions ``f_b(L)`` (hypotheses)
  give a 6 h-later forecast of the same valid time an error correlation of ~0.7 (lead 0) to ~0.97
  (D7+), decaying with the issue separation. Because the same latent fields also enter the truth
  draw ``d_t`` (hence the centre ``c = w - d_t``), averaging past issues does NOT converge to
  the truth: a persistent error floor remains (:func:`issue_correlation` gives the analytic
  correlation).
* **Availability latency** (``use_latency``): a cycle with analysis time ``a`` (00/06/12/18 UTC)
  is only usable at ``a + latency`` (ENS 6 h, control/HRES 4 h, spec 6.3.4 / 7.5);
  ``forecast(issue_s=now)`` returns the latest available cycle, valid times starting at ``a``.
* **Seasonality of skill** (``season_amp``): displacement and amplitude scales are multiplied by
  ``1 + A cos(2 pi (doy - peak)/365.25)`` (A = 0.15, peak mid-January): HYPOTHESIS inspired by
  the qualitative statement of spec 2.8.4 (largest absolute wind errors in winter); the 15 %
  figure is not sourced.
* **Dispersion knob** (``spread_factor`` kappa): members are ``c + kappa d_k``; kappa < 1 gives an
  under-dispersive ensemble (spread/skill ~ kappa). Default 1 (exchangeable).
* Members are generated lazily one at a time (:meth:`ERA5ForecastWeather.forecast_members`).

LIMITATIONS (honest statement): this is NOT a numerical weather prediction. A forecast issued at
``t`` is computed *from the truth* at the valid times (oracle perturbation); causality of the
information the policy sees is guaranteed only by the error statistics, not by the data flow.
Error statistics are calibrated on hypothesised ECMWF ENS
10 m-wind figures, not fitted to real forecast archives. Displaced fields keep their vector
components (no rotation of vectors by the warp Jacobian).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

from horizon.geo.grid import Grid
from horizon.weather.era5 import ERA5Archive
from horizon.weather.fields import Ensemble, WindField

__all__ = ["ForecastErrorParams", "ERA5ForecastWeather", "forecast_skill", "rank_histogram",
           "TARGET_CONTROL_RMSE", "issue_correlation"]

_DAY = 86400.0

TARGET_CONTROL_RMSE = {0: 1.0, 1: 2.2, 2: 3.0, 3: 3.8, 4: 4.5, 5: 5.2, 6: 5.7, 7: 6.0,
                       8: 6.5, 9: 7.0, 10: 7.3}
"""Hypothesised control-forecast vector-wind RMSE [m/s] vs lead [days] (ballpark ECMWF ENS)."""

_LEAD_KNOTS_D = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 14.0)
_LAT_S = 3 * 3600.0   # valid-time lattice of the latent processes
_SHIFT = 1 << 31


def _mix_fractions(p: ForecastErrorParams, lead_s) -> tuple:
    fa = np.clip(_interp_knots(lead_s, p.mix_a), 0.0, 1.0)
    fb = np.clip(_interp_knots(lead_s, p.mix_b), 0.0, 1.0 - fa)
    return fa, fb, np.maximum(1.0 - fa - fb, 0.0)


def _knot_weights(t_s: float, spacing_s: float) -> tuple:
    """Variance-normalised linear interpolation weights ``((k0, w0), (k1, w1))`` at ``t_s``."""
    k0 = int(np.floor(t_s / spacing_s))
    s = t_s / spacing_s - k0
    n = np.hypot(1.0 - s, s)
    return (k0, (1.0 - s) / n), (k0 + 1, s / n)


def issue_correlation(params: ForecastErrorParams, issue1_s: float, issue2_s: float,
                      valid_s: float) -> float:
    """Correlation of the unit error fields of two issues for the same valid time and stream.

    Analytic (before the nonlinear warp). 1 for identical issues; 0 for independent ones.
    """
    p = params
    l1, l2 = valid_s - issue1_s, valid_s - issue2_s
    if issue1_s == issue2_s:
        return 1.0
    if not p.issue_consistency:
        return 0.0
    fa1, fb1, fc1 = (float(x) for x in _mix_fractions(p, l1))
    fa2, fb2, fc2 = (float(x) for x in _mix_fractions(p, l2))
    r = 0.0
    for f1, f2, sp in ((fb1, fb2, p.knot_b_h * 3600.0), (fc1, fc2, p.knot_c_h * 3600.0)):
        w1, w2 = dict(_knot_weights(issue1_s, sp)), dict(_knot_weights(issue2_s, sp))
        r += np.sqrt(f1 * f2) * sum(w1[k] * w2.get(k, 0.0) for k in w1)
    return float(r)


@dataclass(frozen=True)
class ForecastErrorParams:
    """Parameters of the perturbation law. ALL VALUES ARE HYPOTHESES (calibrated, see tests).

    The three amplitude tuples are given at lead ``_LEAD_KNOTS_D`` = 0, 1, 2, 3, 4, 5, 7, 10, 14 d
    and interpolated linearly (constant beyond 14 d).

    Attributes
    ----------
    disp_km : tuple  rms magnitude of the displacement vector [km] (~40 km at D1, 250 km at D7 in
        the calibrated defaults).
    amp_frac : tuple  std of the multiplicative amplitude modulation [-].
    noise_ms : tuple  std of each additive noise component [m/s].
    disp_len_km, amp_len_km, noise_len_km : float
        Spatial correlation lengths (Gaussian covariance ``exp(-r^2 / 2 L^2)``) [km].
    disp_tau_h, amp_tau_h, noise_tau_h : float
        AR(1) correlation times along the forecast [h].
    """

    disp_km: tuple = (0.0, 42.0, 66.0, 103.0, 141.0, 172.0, 250.0, 320.0, 360.0)
    amp_frac: tuple = (0.01, 0.032, 0.042, 0.056, 0.07, 0.08, 0.095, 0.11, 0.13)
    noise_ms: tuple = (0.5, 0.72, 0.75, 0.8, 0.85, 0.86, 0.89, 0.92, 0.95)
    disp_len_km: float = 800.0
    amp_len_km: float = 1000.0
    noise_len_km: float = 200.0
    disp_tau_h: float = 48.0
    amp_tau_h: float = 48.0
    noise_tau_h: float = 18.0
    # --- Sprint 4 (hypotheses) ---
    issue_consistency: bool = True
    mix_a: tuple = (0.45, 0.22, 0.12, 0.08, 0.06, 0.05, 0.04, 0.03, 0.03)
    """Fraction of error variance that is a fresh innovation of each issue, vs lead (knots)."""
    mix_b: tuple = (0.35, 0.40, 0.38, 0.34, 0.30, 0.28, 0.25, 0.22, 0.20)
    """Fraction carried by the 24 h-knot latent field (the rest, 1 - a - b, by the 96 h one)."""
    knot_b_h: float = 24.0
    knot_c_h: float = 96.0
    season_amp: float = 0.15
    season_peak_doy: float = 15.0
    spread_factor: float = 1.0
    use_latency: bool = True
    latency_ens_h: float = 6.0
    latency_ctrl_h: float = 4.0
    cycle_h: float = 6.0
    # --- Sprint 5 experiment knobs (defaults = Sprint-4 behaviour bit-for-bit) ---
    error_scale: float = 1.0
    """Multiplier of ALL perturbation amplitudes (displacement, amplitude modulation, noise).
    0 = perfect forecast (every member is the truth)."""
    perfect: bool = False
    """Perfect-forecast mode: every member (and the control) equals the truth, whatever the other
    parameters; equivalent to ``error_scale = 0`` but short-circuits the random fields."""

    disp_scale: float = 1.0
    amp_scale: float = 1.0
    noise_scale: float = 1.0
    """Per-component multipliers (E-02 structure experiments: displacement-only /
    amplitude+noise-only errors at matched RMSE; calibrate with ``analyze``-style skill runs)."""
    analog_scale: float = 1.0
    """Extra multiplier of the analog blend ``b`` (calibrated to the default model's RMSE)."""
    structure: str = "default"
    """``"default"``: displaced-truth errors (keeps the true storm structure at every lead).
    ``"analog"``: structure-DESTROYING errors ``d = b(lead) (A - w)`` with ``A`` the truth of the
    same valid time shifted by a random 5-25 d (piecewise constant over 4 d, so issue-to-issue
    consistent); ``b`` is set so that the control RMSE matches ``error_scale *
    TARGET_CONTROL_RMSE`` (the calibration target of the default model): same RMSE, no phase
    information about the real fronts."""

    @property
    def is_perfect(self) -> bool:
        return bool(self.perfect) or self.error_scale == 0.0

    @classmethod
    def with_knobs(cls, error_scale: float = 1.0, latency_h: float | None = None,
                   consistency: bool | None = None, spread_factor: float | None = None,
                   season_amp: float | None = None, perfect: bool = False,
                   base: "ForecastErrorParams | None" = None) -> "ForecastErrorParams":
        """Clean experiment interface: ``base`` (default params) with the knobs applied.

        ``latency_h``: availability latency of the ENS cycle [h] (the control latency is
        ``max(latency_h - 2, 0)``); 0 = a cycle is usable at its analysis time. ``consistency``:
        issue-to-issue consistency on / off. ``spread_factor`` kappa < 1 under-, > 1 over-
        dispersive. ``season_amp``: seasonal skill modulation (0 = none). ``None`` keeps the
        base value.
        """
        from dataclasses import replace
        b = base or cls()
        kw: dict = {"error_scale": float(error_scale), "perfect": bool(perfect)}
        if latency_h is not None:
            kw.update(use_latency=True, latency_ens_h=float(latency_h),
                      latency_ctrl_h=max(float(latency_h) - 2.0, 0.0))
        if consistency is not None:
            kw["issue_consistency"] = bool(consistency)
        if spread_factor is not None:
            kw["spread_factor"] = float(spread_factor)
        if season_amp is not None:
            kw["season_amp"] = float(season_amp)
        return replace(b, **kw)

    @classmethod
    def legacy(cls, **kw) -> "ForecastErrorParams":
        """Sprint-3 behaviour: independent errors per issue, no latency, no seasonality."""
        return cls(issue_consistency=False, use_latency=False, season_amp=0.0, **kw)


def _interp_knots(lead_s, vals) -> np.ndarray:
    return np.interp(np.asarray(lead_s, float) / _DAY, _LEAD_KNOTS_D, vals)


class _SmoothNoise:
    """Unit-variance spatially correlated Gaussian fields on a grid (FFT-filtered white noise)."""

    def __init__(self, grid: Grid, length_km: float):
        ny, nx = grid.shape
        ky = np.fft.fftfreq(ny, grid.dx)[:, None]
        kx = np.fft.rfftfreq(nx, grid.dx)[None, :]
        kxf = np.fft.fftfreq(nx, grid.dx)[None, :]
        c = (np.pi * length_km * 1e3) ** 2
        self.filt = np.exp(-c * (kx**2 + ky**2))
        full = np.exp(-c * (kxf**2 + ky**2))
        self.shape = grid.shape
        self.norm = 1.0 / float(np.sqrt(np.mean(full**2)))

    def draw(self, rng: np.random.Generator, lead_shape: tuple) -> np.ndarray:
        w = rng.standard_normal(lead_shape + self.shape)
        return self.filter(w)

    def filter(self, w: np.ndarray) -> np.ndarray:
        """Spatially correlate white fields ``(..., ny, nx)`` (unit variance kept)."""
        f = np.fft.irfft2(np.fft.rfft2(w) * self.filt, s=self.shape)
        return f * self.norm


def _ar1(x: np.ndarray, a: float) -> np.ndarray:
    """In-place stationary AR(1) filter along axis 0 of unit-variance white-in-time fields."""
    s = np.sqrt(1.0 - a * a)
    for k in range(1, x.shape[0]):
        x[k] = a * x[k - 1] + s * x[k]
    return x


class ERA5ForecastWeather:
    """Real ERA5 truth + exchangeable synthetic-error ensemble forecasts (SyntheticWeather API).

    Drop-in replacement of :class:`~horizon.weather.synthetic.SyntheticWeather` for the simulator
    and policies (``truth``, ``forecast``, ``grid``, ``epoch``, ``duration_s``).

    Parameters
    ----------
    archive : ERA5Archive
        Source of the hourly truth (on ``grid``).
    grid : Grid, optional
        Must equal ``archive.grid`` (kept for API symmetry).
    epoch : numpy.datetime64
        UTC instant of mission time ``t = 0``.
    duration_s : float  [s]
        Mission length. ``issue_s`` must lie in ``[0, duration_s]``.
    params : ForecastErrorParams, optional
    seed : int
        Master seed; output is a deterministic function of ``(seed, issue_s, seed_offset)``.

    Notes
    -----
    Times beyond the last ERA5 hour (31 Dec 23 UTC) are filled by wrapping to 1 Jan (climatology
    style, discontinuous at the seam): a warning is issued and
    :attr:`n_wrapped_requests` is incremented.
    """

    def __init__(self, archive: ERA5Archive, grid: Grid | None, epoch, duration_s: float,
                 params: ForecastErrorParams | None = None, seed: int = 0):
        if grid is not None and grid != archive.grid:
            raise ValueError("grid must equal archive.grid")
        self.archive = archive
        self.grid = archive.grid
        self.epoch = np.datetime64(epoch, "s")
        self.duration_s = float(duration_s)
        self.params = params or ForecastErrorParams()
        self.seed = int(seed)
        self.n_wrapped_requests = 0
        p = self.params
        self._f_disp = _SmoothNoise(self.grid, p.disp_len_km)
        self._f_amp = _SmoothNoise(self.grid, p.amp_len_km)
        self._f_noise = _SmoothNoise(self.grid, p.noise_len_km)
        ny, nx = self.grid.shape
        self._J, self._I = np.meshgrid(np.arange(ny, dtype=np.float64),
                                       np.arange(nx, dtype=np.float64), indexing="ij")

    # ------------------------------------------------------------------ truth
    def _truth_at(self, t_s: np.ndarray) -> np.ndarray:
        end_s = (self.archive.end - self.epoch) / np.timedelta64(1, "s")
        fill = "error"
        if np.max(t_s) > end_s or np.min(t_s) < (self.archive.start - self.epoch) / np.timedelta64(
                1, "s"):
            fill = "wrap"
            self.n_wrapped_requests += 1
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.archive.fields_at(t_s, self.epoch, fill=fill)

    def truth(self, dt_s: float = 3600.0, start_s: float = 0.0,
              end_s: float | None = None) -> WindField:
        """ERA5 truth on ``[start_s, end_s]`` (default ``[0, duration_s]``) every ``dt_s``.

        Returns
        -------
        WindField
            float32 ``(T, ny, nx, 2)`` true (east, north) wind [m/s], ``epoch = self.epoch``.
        """
        end_s = self.duration_s if end_s is None else end_s
        t = np.arange(start_s, end_s + 0.5 * dt_s, dt_s)
        return WindField(self.grid, self.epoch, t, np.ascontiguousarray(self._truth_at(t)))

    # ------------------------------------------------------------------ seasonality
    def _season(self, valid_s: np.ndarray) -> np.ndarray:
        """Skill-scale factor ``1 + A cos(2 pi (doy - peak) / 365.25)`` at the valid times."""
        p = self.params
        if p.season_amp == 0.0:
            return np.ones(np.shape(valid_s))
        ab = self.epoch + np.round(np.asarray(valid_s, float)).astype("timedelta64[s]")
        y0 = ab.astype("datetime64[Y]").astype("datetime64[s]")
        doy = (ab - y0) / np.timedelta64(1, "s") / _DAY
        return 1.0 + p.season_amp * np.cos(2 * np.pi * (doy - p.season_peak_doy) / 365.25)

    # ------------------------------------------------------------------ cycles / latency
    def analysis_time(self, now_s: float, product: str = "ens") -> float:
        """Analysis time [s] of the latest cycle available at ``now_s`` (``product``: 'ens' or
        'control'). Cycles are 00/06/12/18 UTC (``cycle_h``); available at analysis + latency
        (``latency_ens_h`` / ``latency_ctrl_h``). Clamped to 0: cycles before the mission start
        are treated as available at ``t = 0`` (the archive holds no earlier truth). Without
        ``use_latency`` returns ``now_s`` (Sprint-3 behaviour)."""
        p = self.params
        if not p.use_latency:
            return float(now_s)
        lat = (p.latency_ens_h if product == "ens" else p.latency_ctrl_h) * 3600.0
        cyc = p.cycle_h * 3600.0
        phase = (self.epoch - self.epoch.astype("datetime64[D]")) / np.timedelta64(1, "s")
        a = np.floor((now_s + phase - lat) / cyc + 1e-9) * cyc - phase
        return float(max(a, 0.0))

    # ------------------------------------------------------------------ latent unit fields
    def _white_series(self, stream: tuple, level: int, knot: int, start_idx: int,
                      n: int) -> np.ndarray:
        """AR(1)-in-valid-time white-in-space series ``(n, 5, ny, nx)`` float32 (unit variance)
        of one latent knot; channels: displacement (2), amplitude (1), noise (2). Prefix of the
        series is independent of ``n``."""
        rng = np.random.default_rng(np.random.SeedSequence(
            [self.seed, 21, stream[0], stream[1], level, knot + _SHIFT]))
        x = rng.standard_normal((n, 5) + self.grid.shape, dtype=np.float32)
        p = self.params
        for sl, tau in ((slice(0, 2), p.disp_tau_h), (slice(2, 3), p.amp_tau_h),
                        (slice(3, 5), p.noise_tau_h)):
            a = float(np.exp(-_LAT_S / (tau * 3600.0)))
            sg = np.float32(np.sqrt(1.0 - a * a))
            a = np.float32(a)
            y = x[:, sl]
            for k in range(1, n):
                y[k] = a * y[k - 1] + sg * y[k]
        return x

    def _unit_fields(self, stream: tuple, issue_s: float, valid_s: np.ndarray):
        """Unit spatially correlated fields ``(xi_d (T,2), xi_a (T,), xi_n (T,2))`` of one stream
        for the forecast issued at ``issue_s`` (consistent across issues, see module doc)."""
        p = self.params
        q = valid_s / _LAT_S
        lo = np.floor(q).astype(int)
        fr = (q - lo).astype(np.float32)[:, None, None, None]
        nt = valid_s.size
        fa, fb, fc = _mix_fractions(p, valid_s - issue_s)
        iss = int(round(issue_s))
        z = np.zeros((nt, 5) + self.grid.shape, np.float32)

        def add(series, start, frac_w):
            j = lo - start
            seg = series[j] * (1 - fr) + series[np.minimum(j + 1, series.shape[0] - 1)] * fr
            z[...] += seg * frac_w.astype(np.float32)[:, None, None, None]

        hi = int(np.ceil(q.max()))
        start = int(np.floor(q.min()))
        add(self._white_series(stream, 0, iss, start, hi - start + 1), start, np.sqrt(fa))
        for lev, f, sp in ((1, fb, p.knot_b_h * 3600.0), (2, fc, p.knot_c_h * 3600.0)):
            for k, wk in _knot_weights(issue_s, sp):
                if wk < 1e-9:
                    continue
                st = int(np.floor((k * sp - sp) / _LAT_S))
                st = min(st, start)
                ser = self._white_series(stream, lev, k, st, hi - st + 1)
                add(ser, st, np.sqrt(f) * wk)
        xd = self._f_disp.filter(z[:, 0:2])
        xa = self._f_amp.filter(z[:, 2])
        xn = self._f_noise.filter(z[:, 3:5])
        return xd, xa, xn

    # ------------------------------------------------------------------ perturbations
    def _warp(self, w, lead_s, xi_d, xi_a, xi_n, season=None) -> np.ndarray:
        p = self.params
        nt = lead_s.size
        ny, nx = self.grid.shape
        sc = 1.0 if season is None else season[:, None, None]
        es = p.error_scale
        s_d = (_interp_knots(lead_s, p.disp_km)[:, None, None] * 1e3 / np.sqrt(2.0) * sc * es
               * p.disp_scale)
        s_a = _interp_knots(lead_s, p.amp_frac)[:, None, None] * sc * es * p.amp_scale
        s_n = _interp_knots(lead_s, p.noise_ms)[:, None, None, None] * es * p.noise_scale
        # backward warp with bilinear sampling of the truth (components kept true east/north)
        fi = np.clip(self._I[None] + s_d * xi_d[:, 0] / self.grid.dx, 0.0, nx - 1.0)
        fj = np.clip(self._J[None] + s_d * xi_d[:, 1] / self.grid.dx, 0.0, ny - 1.0)
        i0 = np.minimum(np.floor(fi).astype(np.intp), nx - 2)
        j0 = np.minimum(np.floor(fj).astype(np.intp), ny - 2)
        wi = (fi - i0)[..., None].astype(np.float32)
        wj = (fj - j0)[..., None].astype(np.float32)
        tt = np.arange(nt)[:, None, None]
        warped = ((1 - wj) * ((1 - wi) * w[tt, j0, i0] + wi * w[tt, j0, i0 + 1])
                  + wj * ((1 - wi) * w[tt, j0 + 1, i0] + wi * w[tt, j0 + 1, i0 + 1]))
        amp = np.maximum(1.0 + s_a * xi_a, 0.2)[..., None].astype(np.float32)
        d = warped * amp + (s_n * np.moveaxis(xi_n, 1, -1)).astype(np.float32) - w
        return d.astype(np.float32)

    def _perturbation(self, w: np.ndarray, lead_s: np.ndarray, dt_s: float,
                      rng: np.random.Generator, season=None) -> np.ndarray:
        """Legacy (independent-issue) draw ``d = P(w) - w`` [m/s], float32 ``(T, ny, nx, 2)``."""
        p = self.params
        nt = lead_s.size
        xi_d = _ar1(self._f_disp.draw(rng, (nt, 2)), np.exp(-dt_s / (p.disp_tau_h * 3600.0)))
        xi_a = _ar1(self._f_amp.draw(rng, (nt,)), np.exp(-dt_s / (p.amp_tau_h * 3600.0)))
        xi_n = _ar1(self._f_noise.draw(rng, (nt, 2)), np.exp(-dt_s / (p.noise_tau_h * 3600.0)))
        return self._warp(w, lead_s, xi_d, xi_a, xi_n, season)

    def _analog_draw(self, w, lead, t, analysis_s, stream) -> np.ndarray:
        """Structure-destroying perturbation (see ``ForecastErrorParams.structure``)."""
        p = self.params
        blk = int(np.floor(analysis_s / (96 * 3600.0)))
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, 77, stream[0], stream[1],
                                                            blk + _SHIFT]))
        shift = rng.uniform(5.0, 25.0) * _DAY * (1 if rng.random() < 0.5 else -1)
        lo = (self.archive.start - self.epoch) / np.timedelta64(1, "s")
        hi = (self.archive.end - self.epoch) / np.timedelta64(1, "s")
        if t.max() + shift > hi or t.min() + shift < lo:
            shift = -shift
        if t.max() + shift > hi or t.min() + shift < lo:
            shift = 0.0 if t.max() + 15 * _DAY > hi else shift
            shift = np.clip(shift, lo - t.min(), hi - t.max())
        a = self._truth_at(t + shift)
        diff = a - w
        rms = np.sqrt(np.maximum((diff.astype(np.float64) ** 2).sum(-1).mean(axis=(1, 2)), 1e-9))
        tgt = np.interp(lead / _DAY, list(TARGET_CONTROL_RMSE), list(TARGET_CONTROL_RMSE.values()))
        # control error = b (A_k - A_t), rms ~ b * rms(A - w)
        b = np.clip(tgt * p.error_scale * p.analog_scale / rms, 0.0, 1.0)
        return (b[:, None, None, None] * diff).astype(np.float32)

    def _draw(self, w, lead, t, dt_s, analysis_s, stream, season) -> np.ndarray:
        if self.params.structure == "analog":
            return self._analog_draw(w, lead, t, analysis_s, stream)
        if self.params.issue_consistency:
            xi = self._unit_fields(stream, analysis_s, t)
            return self._warp(w, lead, *xi, season=season)
        iss = int(round(analysis_s))
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, 11, iss, *stream]))
        return self._perturbation(w, lead, dt_s, rng, season)

    # ------------------------------------------------------------------ forecast
    def forecast_members(self, analysis_s: float, horizon_s: float, n_members: int,
                         dt_s: float = 10800.0, seed_offset: int = 0):
        """Lazy generator for the cycle with analysis time ``analysis_s`` (no latency logic).

        Returns ``(times_s, members)`` where ``members`` yields float32 ``(T, ny, nx, 2)`` arrays
        for ``k = 0 .. n_members-1`` (member 0 = control), one at a time (peak memory independent
        of ``n_members``). Valid times ``analysis_s + j dt_s``.
        """
        nt = int(round(horizon_s / dt_s)) + 1
        lead = np.arange(nt) * dt_s
        t = analysis_s + lead
        w = self._truth_at(t)
        if self.params.is_perfect:  # perfect-forecast mode: every member is the truth
            def gen_perfect():
                for _ in range(n_members):
                    yield np.array(w, dtype=np.float32)
            return t, gen_perfect()
        season = self._season(t) if self.params.season_amp else None
        kap = self.params.spread_factor
        centre = w - self._draw(w, lead, t, dt_s, analysis_s, (0, 0), season)

        def gen():
            for k in range(n_members):
                off = 0 if k == 0 else int(seed_offset)
                d = self._draw(w, lead, t, dt_s, analysis_s, (1 + off, k), season)
                yield (centre + (d if kap == 1.0 else np.float32(kap) * d)).astype(np.float32)

        return t, gen()

    def forecast_cycle(self, analysis_s: float, horizon_s: float, n_members: int,
                       dt_s: float = 10800.0, seed_offset: int = 0) -> Ensemble:
        """Ensemble of the cycle with analysis time ``analysis_s`` (valid times from it)."""
        if not 0 <= analysis_s <= self.duration_s:
            raise ValueError("issue_s outside [0, duration_s]")
        t, gen = self.forecast_members(analysis_s, horizon_s, n_members, dt_s, seed_offset)
        uv = np.empty((n_members, t.size) + self.grid.shape + (2,), np.float32)
        for k, m in enumerate(gen):
            uv[k] = m
        return Ensemble(self.grid, self.epoch, float(analysis_s), t, uv,
                        np.full(n_members, 1.0 / n_members))

    def forecast(self, issue_s: float, horizon_s: float, n_members: int,
                 dt_s: float = 10800.0, seed_offset: int = 0, product: str = "ens") -> Ensemble:
        """Exchangeable ensemble forecast available at time ``issue_s`` (= "now").

        With ``params.use_latency`` the LATEST cycle usable at ``now = issue_s`` is returned
        (analysis time ``a <= now - latency``, :meth:`analysis_time`): ``ens.issue_s = a`` and the
        valid times start at ``a`` and extend to at least ``now + horizon_s`` (the policy's lead
        is ``now - a``). Without it, ``a = issue_s`` (Sprint-3 behaviour).

        Member ``k`` is ``c + kappa d_k`` with ``c = truth - d_truth`` (see module docstring). The
        control (member 0) depends only on ``(seed, a)``; members ``k >= 1`` also on
        ``seed_offset`` and ``k`` (not on ``n_members``). ``product='control'`` returns the
        single-member HRES-like control of the same cycle family with the shorter control
        latency (identical to member 0 of the ENS of that cycle).

        Parameters
        ----------
        issue_s : float  [s since epoch], in ``[0, duration_s]``.
        horizon_s : float  [s]  horizon from ``now``.
        n_members : int  (>= 1), equal weights (ignored for ``product='control'``).
        dt_s : float  [s].
        seed_offset : int  selects another set of members ``k >= 1`` for the same control.

        Returns
        -------
        Ensemble
            ``uv`` float32 ``(M, T, ny, nx, 2)`` true (east, north) wind [m/s].
        """
        if not 0 <= issue_s <= self.duration_s:
            raise ValueError("issue_s outside [0, duration_s]")
        a = self.analysis_time(issue_s, product)
        n = 1 if product == "control" else n_members
        return self.forecast_cycle(a, horizon_s + (issue_s - a), n, dt_s, seed_offset)

    def ensemble_nbytes(self, n_members: int, horizon_s: float, dt_s: float = 10800.0) -> int:
        """Size of the returned ``uv`` array [bytes]."""
        nt = int(round(horizon_s / dt_s)) + 1
        return n_members * nt * self.grid.ny * self.grid.nx * 2 * 4


# ---------------------------------------------------------------------------------- verification
def forecast_skill(weather: ERA5ForecastWeather, issue_s, n_members: int = 20,
                   max_lead_days: int = 10, mask: np.ndarray | None = None,
                   dt_s: float = 6 * 3600.0, seed_offset: int = 0) -> dict:
    """Verification statistics of the forecasts issued at ``issue_s`` against the truth.

    Parameters
    ----------
    weather : ERA5ForecastWeather
    issue_s : sequence of float  [s since epoch]
    n_members : int
    max_lead_days : int
    mask : ndarray bool (ny, nx), optional  Cells to score (e.g. sea); default all.
    dt_s : float  [s]  Must divide one day.

    Returns
    -------
    dict
        ``lead_days`` (D+1,), ``control_rmse``, ``mean_rmse``, ``spread`` [m/s] (vector wind:
        sqrt of the mean squared (u, v) error; spread = sqrt(mean unbiased member variance of
        u plus v)), ``n_members``, and ``ranks_u`` / ``ranks_v`` int arrays ``(D+1, n_samples)``
        of the truth rank in ``[0, M]`` among members (subsampled cells).
    """
    per_day = int(round(_DAY / dt_s))
    horizon = max_lead_days * _DAY
    mask = np.ones(weather.grid.shape, bool) if mask is None else mask
    se_c = np.zeros(max_lead_days + 1)
    se_m = np.zeros(max_lead_days + 1)
    var = np.zeros(max_lead_days + 1)
    ranks = {0: [], 1: []}
    jj, ii = np.nonzero(mask)
    sub = np.arange(0, jj.size, 7)
    for iss in issue_s:
        ens = weather.forecast_cycle(iss, horizon, n_members, dt_s=dt_s, seed_offset=seed_offset)
        w = weather._truth_at(ens.times_s)
        sel = np.arange(0, ens.times_s.size, per_day)
        u = ens.uv[:, sel][:, :, jj, ii]           # (M, D+1, n, 2)
        tr = w[sel][:, jj, ii]                     # (D+1, n, 2)
        se_c += ((u[0] - tr) ** 2).sum(-1).mean(-1)
        se_m += ((u.mean(0) - tr) ** 2).sum(-1).mean(-1)
        var += u.var(0, ddof=1).sum(-1).mean(-1)
        for c in (0, 1):
            ranks[c].append((u[..., c][:, :, sub] < tr[..., c][None, :, sub]).sum(0))
    n = len(issue_s)
    return {
        "lead_days": np.arange(max_lead_days + 1),
        "control_rmse": np.sqrt(se_c / n), "mean_rmse": np.sqrt(se_m / n),
        "spread": np.sqrt(var / n),
        "ranks_u": np.concatenate(ranks[0], axis=1), "ranks_v": np.concatenate(ranks[1], axis=1),
        "n_members": n_members,
    }


def rank_histogram(ranks: np.ndarray, n_members: int) -> np.ndarray:
    """Relative frequency of each truth rank ``0..M`` (``M + 1`` bins), flat = ``1/(M+1)``."""
    h = np.bincount(np.asarray(ranks).ravel(), minlength=n_members + 1).astype(float)
    return h / h.sum()
