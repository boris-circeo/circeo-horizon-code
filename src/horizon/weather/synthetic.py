"""Synthetic North-Atlantic winter surface-wind generator (truth + causal ensemble forecasts).

Real meteorological data are not available in Sprint 1, so closed-loop backtests use this
generator both as *truth* and as *forecast source* (DES-860 §2.1, §2.4, §2.5, §2.8).

Model (every number is a HYPOTHESIS, see :class:`SyntheticParams`):

* background westerly jet + weak trade easterlies, shifted/strengthened by an NAO-like regime
  index (AR(1), ~10 d correlation) (DES-860 §2.4.2);
* a Poisson population of cyclones born in the western basin, moving ENE with a jittered track,
  3-6 d life cycle, cyclonic (counter-clockwise) vortex with inward spiral and a
  translation-speed asymmetry (stronger on the equatorward/right flank) (DES-860 §2.4.1);
* spatially and temporally correlated small-scale noise.

The *truth* is the realisation of a fixed list of :class:`Storm` tracks + regime path + noise.
A *forecast* re-renders the same storms with per-storm, per-member errors (timing, cross-track
position, intensity, size) whose standard deviation grows with lead time, a regime index that
relaxes to climatology, and random storms for cyclogenesis that is not yet predictable
(DES-860 §2.8). Member errors are drawn so that the truth is statistically exchangeable with a
member: control error ``eps_c`` (truth -> control) and member perturbation ``eps_m`` (control ->
member) have equal variance, giving a spread-skill ratio close to 1.

Wind components are stored as true (east, north) "toward" components, per docs/CONVENTIONS.md.
Storm dynamics are computed in the grid plane and rotated to true east/north with the local
projection rotation angle.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from horizon.core.units import kn_to_ms
from horizon.geo.grid import Grid
from horizon.weather.fields import Ensemble, WindField

__all__ = ["SyntheticParams", "Storm", "SyntheticWeather", "skill_vs_truth"]

_DAY = 86400.0
_NODE_S = 10800.0  # spacing of stored storm-track nodes [s]


@dataclass(frozen=True)
class SyntheticParams:
    """Tunable parameters of the synthetic wind generator. ALL VALUES ARE HYPOTHESES.

    Speeds [m/s], lengths [km] unless stated, angles [deg], times [s] or [days] as named.
    Error tuples ``(a0, a1, p, amax)`` define ``sigma(lead) = amax*tanh((a0 + a1*lead_d**p)/amax)``
    with ``lead_d`` the lead time in days.
    """

    # --- background flow (true frame)
    jet_u_ms: float = 13.0             # peak westerly of the background jet [m/s]
    jet_lat_deg: float = 49.0          # mean jet latitude [deg N]
    jet_halfwidth_deg: float = 11.0    # Gaussian e-folding half-width of the jet [deg lat]
    trade_u_ms: float = -3.0           # peak easterly of the trade belt [m/s]
    trade_lat_deg: float = 30.0        # trade belt centre latitude [deg N]
    trade_halfwidth_deg: float = 7.0   # [deg lat]
    # --- regime index (NAO-like, AR(1))
    nao_tau_days: float = 10.0         # correlation time [days]
    nao_jet_shift_deg: float = 3.0     # jet latitude shift per unit index [deg lat]
    nao_jet_strength: float = 0.2      # fractional jet strengthening per unit index
    nao_genesis_shift_deg: float = 2.0  # genesis latitude shift per unit index [deg lat]
    # --- cyclones
    genesis_rate_per_day: float = 1.0 / 2.5  # Poisson rate of cyclogenesis [1/day]
    genesis_lon_range: tuple = (-62.0, -42.0)  # [deg E]
    genesis_lat_mean: float = 41.0     # [deg N]
    genesis_lat_sd: float = 3.0        # [deg]
    speed_range_ms: tuple = (kn_to_ms(20.0), kn_to_ms(35.0))  # translation speed [m/s]
    heading_deg: float = 65.0          # mean heading, ENE [deg true]
    heading_sd_deg: float = 10.0       # genesis heading spread / OU stationary sd [deg]
    speed_jitter_ms: float = 2.0       # OU stationary sd of speed [m/s]
    track_tau_days: float = 1.5        # OU correlation of track jitter [days]
    life_range_days: tuple = (3.0, 6.0)
    radius_range_km: tuple = (500.0, 1000.0)  # outer radius [km]
    peak_range_ms: tuple = (kn_to_ms(18.0), kn_to_ms(32.0))  # tangential peak [m/s]
    rm_over_radius: float = 0.4        # radius of maximum wind / outer radius [-]
    life_peak_frac: float = 0.4        # life fraction at maximum intensity [-]
    asym_frac: float = 0.4             # fraction of translation velocity added (asymmetry) [-]
    inflow_deg: float = 20.0           # inward spiral angle [deg]
    gust_knee_ms: float = 25.0         # speeds above this are softly compressed [m/s]
    gust_cap_ms: float = 12.0          # max excess over the knee (tanh) [m/s]
    # --- small-scale noise
    noise_sigma_ms: float = 1.5        # per-component std [m/s]
    noise_length_km: float = 120.0     # spatial correlation length [km]
    noise_tau_h: float = 10.0          # temporal correlation [h]
    # --- forecast errors (std of the control error at a given lead; members add equal std)
    err_time_h: tuple = (0.3, 0.6, 1.3, 48.0)      # timing [h]
    err_cross_km: tuple = (10.0, 18.0, 1.0, 900.0)  # cross-track position [km]
    err_log_intensity: tuple = (0.03, 0.035, 0.9, 0.5)  # std of log(intensity) [-]
    err_log_radius: tuple = (0.02, 0.02, 0.9, 0.3)     # std of log(radius) [-]
    member_error_scale: float = 1.0    # std of member perturbation / std of control error [-]
    genesis_foresight_days: float = 3.0  # storms born later than issue+this are not in control [d]
    pad_days: float = 16.0             # truth/regime/noise are defined this long after duration [d]


@dataclass(frozen=True)
class Storm:
    """One cyclone: parameters and track nodes (grid frame).

    Attributes
    ----------
    t0_s, life_s : float
        Genesis time [s since epoch] and life time [s].
    peak_ms : float
        Peak tangential wind [m/s]. ``radius_m`` : outer radius [m].
    xy : ndarray (n, 2)
        Centre positions [m, grid frame] at ages ``k * 10800`` s.
    vel : ndarray (n, 2)
        Translation velocity [m/s, grid frame] at the same nodes.
    """

    t0_s: float
    life_s: float
    peak_ms: float
    radius_m: float
    xy: np.ndarray
    vel: np.ndarray


def _sigma(lead_s, spec) -> np.ndarray:
    a0, a1, p, amax = spec
    d = np.maximum(np.asarray(lead_s, float), 0.0) / _DAY
    return amax * np.tanh((a0 + a1 * d**p) / amax)


def _intensity(frac, peak_frac):
    """Life-cycle shape in [0, 1]: zero at 0 and 1, maximum at ``peak_frac``."""
    s = np.clip(frac, 0.0, 1.0) ** (np.log(0.5) / np.log(peak_frac))
    return np.sin(np.pi * s) ** 1.2


class SyntheticWeather:
    """Deterministic synthetic wind truth and causal ensemble forecasts.

    Parameters
    ----------
    grid : Grid
        Planning grid (any size; 40 km basin grid is the design case).
    epoch : numpy.datetime64
        UTC instant of ``t = 0``.
    duration_s : float
        Length of the truth [s]. Forecast issue times must lie in ``[0, duration_s]``.
    params : SyntheticParams, optional
    seed : int
        Master seed. Same seed gives bitwise-identical output.

    Attributes
    ----------
    storms : list[Storm]
        The truth cyclone population (genesis from ``-life_max`` to ``duration + pad``).
    """

    def __init__(self, grid: Grid, epoch, duration_s: float,
                 params: SyntheticParams | None = None, seed: int = 0):
        self.grid = grid
        self.epoch = np.datetime64(epoch, "s")
        self.duration_s = float(duration_s)
        self.params = params or SyntheticParams()
        self.seed = int(seed)
        p = self.params
        lon, lat = grid.lonlat_mesh()
        self._lat = lat.astype(np.float32)
        e_east, _ = grid.local_basis(lon, lat)
        self._theta = np.arctan2(e_east[..., 1], e_east[..., 0])  # grid angle of true east [rad]
        self._X, self._Y = (a.astype(np.float32) for a in grid.xy_mesh())
        self._span_end = self.duration_s + p.pad_days * _DAY
        self._tmin = -p.life_range_days[1] * _DAY
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, 1]))
        # regime index on an hourly axis covering [tmin, span_end]; AR(1), unit variance
        self._nao_t = np.arange(self._tmin, self._span_end + 3600.0, 3600.0)
        a = np.exp(-3600.0 / (p.nao_tau_days * _DAY))
        x = np.empty(self._nao_t.size)
        x[0] = rng.standard_normal()
        w = rng.standard_normal(x.size)
        for k in range(1, x.size):
            x[k] = a * x[k - 1] + np.sqrt(1 - a * a) * w[k]
        self._nao = x
        self.storms = self._draw_storms(rng, self._tmin, self._span_end, self._nao_at)
        self._noise_cache: np.ndarray | None = None
        self._spec, self._spec_scale = self._noise_filter()

    # ------------------------------------------------------------------ helpers
    def _nao_at(self, t_s):
        return np.interp(t_s, self._nao_t, self._nao)

    def _theta_at(self, x, y):
        j, i = self.grid.index_of(x, y)
        return self._theta[np.clip(j, 0, self.grid.ny - 1), np.clip(i, 0, self.grid.nx - 1)]

    def _draw_storms(self, rng, t_lo, t_hi, nao_fn) -> list[Storm]:
        """Poisson cyclogenesis on ``(t_lo, t_hi]`` with tracks integrated in the grid plane."""
        p = self.params
        n = rng.poisson(p.genesis_rate_per_day * max(t_hi - t_lo, 0.0) / _DAY)
        t0 = np.sort(rng.uniform(t_lo, max(t_hi, t_lo), n))
        nao0 = nao_fn(t0)
        lon = rng.uniform(*p.genesis_lon_range, n)
        lat = (p.genesis_lat_mean + p.nao_genesis_shift_deg * nao0
               + p.genesis_lat_sd * rng.standard_normal(n))
        gx, gy = self.grid.to_xy(lon, np.clip(lat, 30.0, 62.0))
        life = rng.uniform(*p.life_range_days, n) * _DAY
        peak = rng.uniform(*p.peak_range_ms, n)
        rad = rng.uniform(*p.radius_range_km, n) * 1e3
        spd0 = rng.uniform(*p.speed_range_ms, n)
        hdg0 = p.heading_deg + p.heading_sd_deg * rng.standard_normal(n)
        tau = p.track_tau_days * _DAY
        storms = []
        for k in range(n):
            m = int(np.ceil(life[k] / _NODE_S)) + 2
            xi = rng.standard_normal((m, 2))
            pos = np.array([gx[k], gy[k]], float)
            h, s = hdg0[k], spd0[k]
            xy = np.empty((m, 2))
            vel = np.empty((m, 2))
            c = np.sqrt(2 * _NODE_S / tau)
            for q in range(m):
                th = self._theta_at(pos[0], pos[1])
                u, v = s * np.sin(np.radians(h)), s * np.cos(np.radians(h))
                vel[q] = (u * np.cos(th) - v * np.sin(th), u * np.sin(th) + v * np.cos(th))
                xy[q] = pos
                pos = pos + vel[q] * _NODE_S
                h += -(h - p.heading_deg) * _NODE_S / tau + p.heading_sd_deg * c * xi[q, 0]
                s += (-(s - spd0[k]) * _NODE_S / tau + p.speed_jitter_ms * c * xi[q, 1])
                s = max(s, 4.0)
            storms.append(Storm(float(t0[k]), float(life[k]), float(peak[k]), float(rad[k]),
                                xy, vel))
        return storms

    def _background(self, t_s, nao_t) -> np.ndarray:
        """Background jet + trades in true frame, ``(nt, ny, nx, 2)`` float32 [m/s]."""
        p = self.params
        nao = np.asarray(nao_t, float)[:, None, None]
        lat = self._lat[None]
        jet = (p.jet_u_ms * (1 + p.nao_jet_strength * nao)
               * np.exp(-(((lat - p.jet_lat_deg - p.nao_jet_shift_deg * nao)
                           / p.jet_halfwidth_deg) ** 2)))
        trade = p.trade_u_ms * np.exp(-(((lat - p.trade_lat_deg) / p.trade_halfwidth_deg) ** 2))
        out = np.zeros((len(t_s),) + self.grid.shape + (2,), np.float32)
        out[..., 0] = jet + trade
        return out

    def _render_storms(self, storms, t_s, eps=None, issue_s=0.0) -> np.ndarray:
        """Storm winds in the *grid* frame, ``(nt, ny, nx, 2)`` float32 [m/s].

        ``eps`` (n_storms, 4) are standardised error draws (time, cross-track, log-intensity,
        log-radius), scaled by the lead-dependent sigmas; ``None`` renders the truth.
        """
        p = self.params
        t_s = np.asarray(t_s, float)
        out = np.zeros((t_s.size,) + self.grid.shape + (2,), np.float32)
        lead = np.maximum(t_s - issue_s, 0.0)
        ca, sa = np.cos(np.radians(p.inflow_deg)), np.sin(np.radians(p.inflow_deg))
        for k, s in enumerate(storms):
            if eps is None:
                shift = np.zeros_like(t_s)
            else:
                shift = _sigma(lead, p.err_time_h) * 3600.0 * eps[k, 0]
            age = t_s - s.t0_s - shift
            idx = np.nonzero((age > 0) & (age < s.life_s))[0]
            if idx.size == 0:
                continue
            a = age[idx]
            nodes = np.arange(s.xy.shape[0])
            f = a / _NODE_S
            px, py = np.interp(f, nodes, s.xy[:, 0]), np.interp(f, nodes, s.xy[:, 1])
            vx, vy = np.interp(f, nodes, s.vel[:, 0]), np.interp(f, nodes, s.vel[:, 1])
            life_fac = _intensity(a / s.life_s, p.life_peak_frac)
            rm = p.rm_over_radius * s.radius_m * np.ones(idx.size)
            amp = s.peak_ms * life_fac
            if eps is not None:
                ld = lead[idx]
                off = _sigma(ld, p.err_cross_km) * 1e3 * eps[k, 1]
                nv = np.maximum(np.hypot(vx, vy), 1e-6)
                px, py = px - vy / nv * off, py + vx / nv * off
                amp = amp * np.exp(_sigma(ld, p.err_log_intensity) * eps[k, 2])
                rm = rm * np.exp(_sigma(ld, p.err_log_radius) * eps[k, 3])
            dx = self._X[None] - px[:, None, None].astype(np.float32)
            dy = self._Y[None] - py[:, None, None].astype(np.float32)
            r = np.maximum(np.hypot(dx, dy), 1.0)
            sr = r / rm[:, None, None].astype(np.float32)
            g = sr * np.exp(0.5 * (1 - sr * sr))
            v_t = amp[:, None, None].astype(np.float32) * g
            asym = (p.asym_frac * life_fac)[:, None, None].astype(np.float32) * g
            out[idx, ..., 0] += (v_t * (-ca * dy - sa * dx) / r
                                 + asym * vx[:, None, None].astype(np.float32))
            out[idx, ..., 1] += (v_t * (ca * dx - sa * dy) / r
                                 + asym * vy[:, None, None].astype(np.float32))
        return out

    def _to_true(self, uv_grid: np.ndarray) -> np.ndarray:
        """Rotate grid-frame vectors to true (east, north) components."""
        c, s = np.cos(self._theta).astype(np.float32), np.sin(self._theta).astype(np.float32)
        a, b = uv_grid[..., 0], uv_grid[..., 1]
        out = np.empty_like(uv_grid)
        out[..., 0] = a * c + b * s
        out[..., 1] = -a * s + b * c
        return out

    def _limit(self, uv: np.ndarray) -> np.ndarray:
        """Soft-compress speeds above the knee (surface drag) so extremes stay physical."""
        k, c = self.params.gust_knee_ms, self.params.gust_cap_ms
        spd = np.hypot(uv[..., 0], uv[..., 1])
        new = np.where(spd > k, k + c * np.tanh((spd - k) / c), spd)
        return uv * (new / np.maximum(spd, 1e-6))[..., None].astype(np.float32)

    # ------------------------------------------------------------------ noise
    def _noise_filter(self):
        ny, nx = self.grid.shape
        ky = np.fft.fftfreq(ny, self.grid.dx)[:, None]
        kx = np.fft.rfftfreq(nx, self.grid.dx)[None, :]
        len_m = self.params.noise_length_km * 1e3
        spec = np.exp(-0.5 * (2 * np.pi * len_m) ** 2 * (kx**2 + ky**2) / 2.0)
        kxf = np.fft.fftfreq(nx, self.grid.dx)[None, :]
        full = np.exp(-0.5 * (2 * np.pi * len_m) ** 2 * (kxf**2 + ky**2) / 2.0)
        return spec, float(np.sqrt(np.mean(full**2)))

    def _white_filtered(self, rng, shape_lead: tuple) -> np.ndarray:
        """Unit-variance spatially correlated noise, shape ``shape_lead + (ny, nx)`` float32."""
        w = rng.standard_normal(shape_lead + self.grid.shape)
        f = np.fft.irfft2(np.fft.rfft2(w) * self._spec, s=self.grid.shape)
        return (f / self._spec_scale).astype(np.float32)

    def _truth_noise(self) -> np.ndarray:
        """Hourly truth noise on ``[0, span_end]``, ``(nt, ny, nx, 2)`` float32 [m/s]."""
        if self._noise_cache is None:
            p = self.params
            rng = np.random.default_rng(np.random.SeedSequence([self.seed, 2]))
            nt = int(self._span_end // 3600) + 1
            a = np.exp(-3600.0 / (p.noise_tau_h * 3600.0))
            out = np.empty((nt,) + self.grid.shape + (2,), np.float32)
            prev = self._white_filtered(rng, (2,))
            for c0 in range(0, nt, 128):
                n = min(128, nt - c0)
                w = self._white_filtered(rng, (n, 2))
                for k in range(n):
                    prev = a * prev + np.sqrt(1 - a * a) * w[k]
                    out[c0 + k] = np.moveaxis(prev, 0, -1) * p.noise_sigma_ms
            self._noise_cache = out
        return self._noise_cache

    # ------------------------------------------------------------------ public API
    def storm_centres(self, t_s: float) -> np.ndarray:
        """Grid-frame centres ``(n_active, 2)`` [m] of the truth storms alive at ``t_s`` [s]."""
        out = []
        for s in self.storms:
            age = t_s - s.t0_s
            if 0 < age < s.life_s:
                f = age / _NODE_S
                n = np.arange(s.xy.shape[0])
                out.append((np.interp(f, n, s.xy[:, 0]), np.interp(f, n, s.xy[:, 1])))
        return np.array(out).reshape(-1, 2)

    def truth(self, dt_s: float = 3600.0, start_s: float = 0.0,
              end_s: float | None = None) -> WindField:
        """Truth wind field on ``[start_s, end_s]`` (default the full duration) every ``dt_s``.

        Parameters
        ----------
        dt_s : float  [s]; should be a multiple of 3600 s (noise is stored hourly).
        start_s, end_s : float  [s since epoch], within ``[0, duration + pad]``.

        Returns
        -------
        WindField
            ``uv`` float32 ``(T, ny, nx, 2)`` true (east, north) wind [m/s].
        """
        end_s = self.duration_s if end_s is None else end_s
        if start_s < 0 or end_s > self._span_end:
            raise ValueError("requested span outside [0, duration + pad]")
        t = np.arange(start_s, end_s + 0.5 * dt_s, dt_s)
        noise = self._truth_noise()
        ik = np.clip(np.rint(t / 3600.0).astype(int), 0, noise.shape[0] - 1)
        uv = self._to_true(self._render_storms(self.storms, t))
        uv += self._background(t, self._nao_at(t))
        uv += noise[ik]
        return WindField(self.grid, self.epoch, t, np.ascontiguousarray(self._limit(uv)))

    def forecast(self, issue_s: float, horizon_s: float, n_members: int,
                 dt_s: float = 10800.0, seed_offset: int = 0) -> Ensemble:
        """Causal ensemble forecast issued at ``issue_s``.

        Uses only information at ``issue_s``: the truth storms alive (or about to form within
        ``genesis_foresight_days``) with lead-dependent errors, the regime index and noise at
        ``issue_s``. Later cyclogenesis only appears, randomly, in members ``>= 1``. Member 0 is
        the control: truth storms with the deterministic ("analysis + model") error
        ``eps_c(seed, issue_s)``, regime index relaxed to climatology, no random storms.

        Parameters
        ----------
        issue_s : float  [s since epoch], in ``[0, duration]``.
        horizon_s : float  [s]; valid times are ``issue_s + k*dt_s``, ``k = 0..horizon_s/dt_s``.
        n_members : int  number of members (>= 1), equal weights.
        dt_s : float  [s]; multiple of 3600 s.
        seed_offset : int  selects another member realisation for the same control.

        Returns
        -------
        Ensemble
            ``uv`` float32 ``(M, T, ny, nx, 2)`` true (east, north) wind [m/s].
        """
        p = self.params
        if not 0 <= issue_s <= self.duration_s or issue_s + horizon_s > self._span_end:
            raise ValueError("issue_s / horizon_s outside the generated span")
        iss = int(round(issue_s))
        t = issue_s + np.arange(int(round(horizon_s / dt_s)) + 1) * dt_s
        lead = t - issue_s
        nt = t.size
        ss = np.random.SeedSequence([self.seed, 3, iss])
        rng_c = np.random.default_rng(ss.spawn(1)[0])
        ns = len(self.storms)
        eps_c = rng_c.standard_normal((ns, 4))
        keep = [k for k, s in enumerate(self.storms)
                if s.t0_s <= issue_s + p.genesis_foresight_days * _DAY
                and s.t0_s + s.life_s > issue_s]
        n0 = float(self._nao_at(issue_s))
        a_k = np.exp(-lead / (p.nao_tau_days * _DAY))
        noise0 = self._truth_noise()[int(np.clip(round(issue_s / 3600.0), 0,
                                                 self._truth_noise().shape[0] - 1))]
        a_n = np.exp(-dt_s / (p.noise_tau_h * 3600.0))
        decay = a_n ** np.arange(nt)
        ens = np.empty((n_members, nt) + self.grid.shape + (2,), np.float32)
        rng_m = np.random.default_rng(np.random.SeedSequence([self.seed, 4, iss, int(seed_offset)]))
        a_nao = np.exp(-dt_s / (p.nao_tau_days * _DAY))
        base = [self.storms[k] for k in keep]
        for m in range(n_members):
            if m == 0:
                eps = eps_c[keep]
                storms = base
                nao_path = n0 * a_k
                noise = noise0[None] * decay[:, None, None, None]
            else:
                z = rng_m.standard_normal((ns, 4))
                eps = (eps_c + p.member_error_scale * z)[keep]
                nao_path = np.empty(nt)
                nao_path[0] = n0
                w = rng_m.standard_normal(nt)
                for k in range(1, nt):
                    nao_path[k] = a_nao * nao_path[k - 1] + np.sqrt(1 - a_nao**2) * w[k]
                # unpredicted cyclogenesis: random storms, unperturbed (they are scenario draws)
                extra = self._draw_storms(rng_m, issue_s + p.genesis_foresight_days * _DAY,
                                          issue_s + horizon_s,
                                          lambda tt, path=nao_path: np.interp(tt, t, path))
                storms = base + extra
                eps = np.vstack([eps, np.zeros((len(extra), 4))])
                w2 = self._white_filtered(rng_m, (nt, 2))
                noise = np.empty((nt,) + self.grid.shape + (2,), np.float32)
                prev = noise0
                for k in range(nt):
                    if k:
                        prev = a_n * prev + np.sqrt(1 - a_n**2) * p.noise_sigma_ms * np.moveaxis(
                            w2[k], 0, -1)
                    noise[k] = prev
            uv = self._to_true(self._render_storms(storms, t, eps, issue_s))
            uv += self._background(t, nao_path)
            uv += noise
            ens[m] = self._limit(uv)
        weights = np.full(n_members, 1.0 / n_members)
        return Ensemble(self.grid, self.epoch, float(issue_s), t, ens, weights)


def skill_vs_truth(ens: Ensemble, truth: WindField) -> dict[str, np.ndarray]:
    """Vector-wind verification of an ensemble against the truth on matching valid times.

    Returns a dict of arrays over lead time with ``lead_s`` [s], ``rmse_control`` and
    ``rmse_mean`` (RMSE of control / ensemble mean, ``sqrt(mean(du^2 + dv^2))`` over cells
    [m/s]) and ``spread`` (``sqrt(mean over cells of var_u + var_v)`` over members, ddof=1
    [m/s]). ``truth`` must contain all valid times of ``ens`` (hourly or matching step).
    """
    k0 = int(round((ens.times_s[0] - truth.times_s[0]) / truth.dt_s))
    step = int(round((ens.times_s[1] - ens.times_s[0]) / truth.dt_s)) if ens.times_s.size > 1 else 1
    tr = truth.uv[k0:k0 + step * ens.times_s.size:step]
    ctrl = np.sqrt(np.mean(np.sum((ens.uv[0] - tr) ** 2, -1), axis=(1, 2)))
    mean = ens.uv.mean(axis=0)
    rm = np.sqrt(np.mean(np.sum((mean - tr) ** 2, -1), axis=(1, 2)))
    sp = np.sqrt(np.mean(ens.uv.var(axis=0, ddof=1).sum(-1), axis=(1, 2)))
    return {"lead_s": ens.times_s - ens.issue_s, "rmse_control": ctrl, "rmse_mean": rm,
            "spread": sp}
