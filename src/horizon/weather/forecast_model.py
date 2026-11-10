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

Every random field is spatially Gaussian-correlated and AR(1) in lead time, so a member is a
coherent trajectory. Errors at lead 0 are small (analysis error ~1 m/s).

LIMITATIONS (honest statement): this is NOT a numerical weather prediction. A forecast issued at
``t`` is computed *from the truth* at the valid times (oracle perturbation); causality of the
information the policy sees is guaranteed only by the error statistics, not by the data flow.
Errors of forecasts issued at different times are independent (no forecast-to-forecast
consistency / jumpiness model). Error statistics are calibrated on hypothesised ECMWF ENS
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
           "TARGET_CONTROL_RMSE"]

_DAY = 86400.0

TARGET_CONTROL_RMSE = {0: 1.0, 1: 2.2, 2: 3.0, 3: 3.8, 4: 4.5, 5: 5.2, 6: 5.7, 7: 6.0,
                       8: 6.5, 9: 7.0, 10: 7.3}
"""Hypothesised control-forecast vector-wind RMSE [m/s] vs lead [days] (ballpark ECMWF ENS)."""

_LEAD_KNOTS_D = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 14.0)


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

    # ------------------------------------------------------------------ perturbations
    def _perturbation(self, w: np.ndarray, lead_s: np.ndarray, dt_s: float,
                      rng: np.random.Generator) -> np.ndarray:
        """One draw ``d = P(w) - w`` [m/s], float32 ``(T, ny, nx, 2)``, ``w`` the truth sequence."""
        p = self.params
        nt = lead_s.size
        ny, nx = self.grid.shape
        s_d = _interp_knots(lead_s, p.disp_km)[:, None, None] * 1e3 / np.sqrt(2.0)  # [m] per comp
        s_a = _interp_knots(lead_s, p.amp_frac)[:, None, None]
        s_n = _interp_knots(lead_s, p.noise_ms)[:, None, None, None]
        xi_d = _ar1(self._f_disp.draw(rng, (nt, 2)), np.exp(-dt_s / (p.disp_tau_h * 3600.0)))
        xi_a = _ar1(self._f_amp.draw(rng, (nt,)), np.exp(-dt_s / (p.amp_tau_h * 3600.0)))
        xi_n = _ar1(self._f_noise.draw(rng, (nt, 2)), np.exp(-dt_s / (p.noise_tau_h * 3600.0)))
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

    # ------------------------------------------------------------------ forecast
    def forecast(self, issue_s: float, horizon_s: float, n_members: int,
                 dt_s: float = 10800.0, seed_offset: int = 0) -> Ensemble:
        """Exchangeable ensemble forecast issued at ``issue_s``.

        Member ``k`` is ``c + d_k`` with ``c = truth - d_truth`` (see module docstring). The
        control (member 0) depends only on ``(seed, issue_s)``; members ``k >= 1`` also on
        ``seed_offset`` and ``k`` (not on ``n_members``).

        Parameters
        ----------
        issue_s : float  [s since epoch], in ``[0, duration_s]``.
        horizon_s : float  [s]; valid times ``issue_s + k * dt_s``, ``k = 0 .. horizon_s/dt_s``.
        n_members : int  (>= 1), equal weights.
        dt_s : float  [s].
        seed_offset : int  selects another set of members ``k >= 1`` for the same control.

        Returns
        -------
        Ensemble
            ``uv`` float32 ``(M, T, ny, nx, 2)`` true (east, north) wind [m/s].
        """
        if not 0 <= issue_s <= self.duration_s:
            raise ValueError("issue_s outside [0, duration_s]")
        iss = int(round(issue_s))
        nt = int(round(horizon_s / dt_s)) + 1
        lead = np.arange(nt) * dt_s
        t = issue_s + lead
        w = self._truth_at(t)
        rng_t = np.random.default_rng(np.random.SeedSequence([self.seed, 11, iss, 0, 0]))
        centre = w - self._perturbation(w, lead, dt_s, rng_t)
        uv = np.empty((n_members, nt) + self.grid.shape + (2,), np.float32)
        for k in range(n_members):
            off = 0 if k == 0 else int(seed_offset)
            rng = np.random.default_rng(np.random.SeedSequence([self.seed, 11, iss, 1 + off, k]))
            uv[k] = centre + self._perturbation(w, lead, dt_s, rng)
        return Ensemble(self.grid, self.epoch, float(issue_s), t, uv,
                        np.full(n_members, 1.0 / n_members))


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
        ens = weather.forecast(iss, horizon, n_members, dt_s=dt_s, seed_offset=seed_offset)
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
