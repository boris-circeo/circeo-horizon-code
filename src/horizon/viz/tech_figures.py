# ruff: noqa: E501
"""Technical figures of the inspector Guide, computed from REAL data and the REAL code.

Every figure is produced at build time by running the actual library (polar loader, velocity-space
envelope, macro-arc stencil, backward DP, forecast-error model, value model ...) on the client
data (BETA polar, ERA5 2015) and on the inspector export (tracks, fleet energy).  The result is a
list of dictionaries ``{id, title_fr, title_en, svg, caption_fr, caption_en, body_fr, body_en}``
that :func:`horizon.viz.inspector.build_html` embeds under the data key ``tech_figures``.  The
figures are client-internal (they contain client-derived numbers): they live in the inspector
HTML, never in the repository.

Public entry point: :func:`build_tech_figures`.  Each figure is independent and guarded: when its
inputs (polar, ERA5 cache, run segments, value models ...) are missing it is skipped.

Conventions: wind speeds in kn on figures about the polar (the unit of the specification) and in
m/s where speeds are ground speeds; angles in degrees; power in kW, energy in MWh; km axes are
the projected (LAEA) grid of the planning domain; time axes are UTC.
"""

from __future__ import annotations

import base64
import io
import json
import re
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
import matplotlib.ticker  # noqa: F401

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

from horizon.core.units import KNOT  # noqa: E402
from horizon.viz.export import decode_array  # noqa: E402

__all__ = ["FIGURE_IDS", "build_tech_figures", "render_figures"]

_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLAR_DIR = Path("/home/claude/circeo-horizon-data/power-polar")
DEFAULT_ERA5_CACHE = _ROOT / "data" / "cache" / "era5"
DEFAULT_RUNS = _ROOT / "outputs" / "s4_runs"
DEFAULT_VALUE = _ROOT / "outputs" / "value"
DEFAULT_CACHE = _ROOT / "data" / "cache" / "tech_figures"
SVG_BUDGET_BYTES = 150_000

# ------------------------------------------------------------------------------------- style
INK, MUTE, GRID = "#1d2330", "#667085", "#dfe3ea"
BLUE, RED, GREEN, ORANGE, PURPLE, GREY, TEAL = (
    "#2f5fd0", "#c8372d", "#1b8a5a", "#d98a1c", "#7a4fb5", "#8a93a3", "#1496a6")
POLICY_STYLE = {  # router -> (colour, linestyle, short label)
    "Oracle_REF_H": (INK, "-", "Oracle"),
    "B0": (GREY, "--", "B0 fixed station"),
    "B1_5d_REF": (ORANGE, "-", "B1"),
    "B1c_5d_REF": (BLUE, "-", "B1c"),
    "ENS_REF": (GREEN, "-", "ENS"),
}


def _rc():
    return {
        "font.family": "DejaVu Sans", "font.size": 8.2, "axes.titlesize": 9.0,
        "axes.labelsize": 8.2, "xtick.labelsize": 7.6, "ytick.labelsize": 7.6,
        "legend.fontsize": 7.4, "legend.frameon": True, "legend.framealpha": 0.9,
        "legend.edgecolor": GRID, "axes.edgecolor": "#aab1bd", "axes.linewidth": 0.7,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
        "axes.labelcolor": INK, "text.color": INK, "xtick.color": "#4b5565",
        "ytick.color": "#4b5565", "figure.facecolor": "white", "savefig.facecolor": "white",
        "svg.fonttype": "none", "svg.hashsalt": "horizon", "lines.linewidth": 1.4,
        "axes.titleweight": "bold", "axes.titlelocation": "left",
    }


def _panel(ax, tag: str, title: str = ""):
    ax.set_title(f"{tag}  {title}" if title else tag, loc="left", fontsize=8.6, fontweight="bold")


def _note(ax, x, y, s, **kw):
    kw.setdefault("fontsize", 7.2)
    kw.setdefault("color", INK)
    kw.setdefault("bbox", {"boxstyle": "round,pad=0.25", "fc": "white", "ec": GRID, "alpha": 0.92})
    return ax.text(x, y, s, **kw)


def _svg_string(fig, dpi: int = 72) -> str:
    buf = io.BytesIO()
    with plt.rc_context(_rc()):
        fig.savefig(buf, format="svg", dpi=dpi, metadata={"Date": None, "Creator": "horizon"})
    s = buf.getvalue().decode("utf-8")
    s = s[s.index("<svg"):]
    s = re.sub(r'<svg([^>]*?)\swidth="[^"]*"\sheight="[^"]*"', r"<svg\1", s, count=1)
    return _shrink_images(s)


def _shrink_images(svg: str, colors: int = 64) -> str:
    """Re-encode the embedded raster layers as palette PNGs (3-4 times smaller)."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return svg

    def sub(m):
        raw = base64.b64decode(m.group(2))
        try:
            im = Image.open(io.BytesIO(raw))
            if im.mode == "RGBA":
                a = im.getchannel("A")
                q = im.convert("RGB").quantize(colors, method=Image.Quantize.MEDIANCUT)
                q = q.convert("RGBA")
                q.putalpha(a)
                im = q.quantize(colors, method=Image.Quantize.FASTOCTREE)
            else:
                im = im.convert("RGB").quantize(colors, method=Image.Quantize.MEDIANCUT)
            b = io.BytesIO()
            im.save(b, format="PNG", optimize=True)
        except Exception:  # noqa: BLE001
            return m.group(0)
        out = base64.b64encode(b.getvalue()).decode()
        return m.group(1) + out if len(out) < len(m.group(2)) else m.group(0)

    return re.sub(r'(data:image/png;base64,)\s*([A-Za-z0-9+/=\s]+?)(?=")', sub, svg)


# -------------------------------------------------------------------------------------- data
@dataclass
class Ctx:
    """Shared, lazily built inputs (all optional: figures skip when their input is missing)."""

    export: dict | None
    polar: object | None = None
    polar_dir: Path = DEFAULT_POLAR_DIR
    era5_cache: Path = DEFAULT_ERA5_CACHE
    runs_dir: Path = DEFAULT_RUNS
    value_dir: Path = DEFAULT_VALUE
    cache_dir: Path = DEFAULT_CACHE
    results_json: Path | None = None
    _lazy: dict = field(default_factory=dict)

    def lazy(self, key: str, make: Callable):
        if key not in self._lazy:
            self._lazy[key] = make()
        return self._lazy[key]

    # polar ------------------------------------------------------------------------------
    def get_polar(self):
        def make():
            if self.polar is not None:
                return self.polar
            from horizon.polar.beta import load_beta_polar

            if Path(self.polar_dir).is_dir() and list(Path(self.polar_dir).glob("polar_BETA*.csv")):
                return load_beta_polar(self.polar_dir)
            return _polar_from_export(self.export)
        return self.lazy("polar", make)

    def get_env(self):
        from horizon.polar.envelope import build_envelope
        return self.lazy("env", lambda: build_envelope(self.get_polar()))

    def get_hold(self):
        from horizon.polar.derived import hold_power_curve
        return self.lazy("hold", lambda: hold_power_curve(self.get_polar()))

    # weather / grid -----------------------------------------------------------------------
    def get_grid(self):
        from horizon.geo.grid import Grid
        from horizon.weather.era5 import ERA5_BOX
        return self.lazy("grid", lambda: Grid.from_bbox(*ERA5_BOX, 40e3))

    def get_archive(self):
        from horizon.weather.era5 import ERA5Archive

        def make():
            if not Path(self.era5_cache).is_dir() or not list(Path(self.era5_cache).glob("*.npz")):
                return None
            return ERA5Archive(self.era5_cache, self.get_grid(), year=2015)
        return self.lazy("archive", make)

    def get_coast(self):
        from horizon.geo.coast import CoastModel, build_basin_coast, signed_distance
        from horizon.weather.era5 import ERA5_BOX

        def make():
            arc = self.get_archive()
            if arc is None:
                return None
            c0 = build_basin_coast(40e3, bbox=ERA5_BOX)
            land = (c0.sdf < 0) | arc.outside
            return CoastModel(self.get_grid(), signed_distance(self.get_grid(), land))
        return self.lazy("coast", make)

    def get_weather(self, days: float = 365.0, seed: int = 1):
        from horizon.weather.forecast_model import ERA5ForecastWeather

        def make():
            arc = self.get_archive()
            if arc is None:
                return None
            return ERA5ForecastWeather(arc, self.get_grid(), np.datetime64("2015-01-01T00:00:00"),
                                       days * 86400.0, seed=seed)
        return self.lazy(f"wx{seed}", make)

    # export ----------------------------------------------------------------------------
    def seed_run(self):
        if not self.export or not self.export.get("seeds"):
            return None
        return self.export["seeds"][0]

    def npz_cache(self, name: str, make: Callable[[], dict]) -> dict:
        """Disk cache of expensive intermediate arrays (``data/cache/tech_figures``)."""
        f = Path(self.cache_dir) / f"{name}.npz"
        if f.exists():
            z = np.load(f, allow_pickle=False)
            return {k: z[k] for k in z.files}
        out = make()
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(f, **{k: np.asarray(v) for k, v in out.items()})
        except OSError:  # read-only cache: not fatal
            pass
        return {k: np.asarray(v) for k, v in out.items()}


def _polar_from_export(export):
    """Rebuild a (coarser) :class:`PolarTable` from the export's embedded polar."""
    from horizon.polar.table import PolarTable

    if not export or not export.get("polar"):
        raise FileNotFoundError("no polar available")
    pe = export["polar"]
    raw = decode_array(pe["p"]).astype(np.float64)
    inf = raw == pe["infeasible"]
    p = np.where(inf, np.nan, raw * pe["scale_kw"])
    tws = np.asarray(pe["tws_kn"], float) * KNOT
    return PolarTable(p, tws, np.asarray(pe["twa_deg"], float), np.asarray(pe["u_ms"], float),
                      strict=False, feasible=~inf, meta={"source": "export"},
                      p_bounds=(-5000.0, 5000.0))


def _tws_index(polar, kn: float) -> int:
    return int(np.argmin(np.abs(polar.tws / KNOT - kn)))


# =========================================================================== figure 1: polar
def fig_polar(ctx: Ctx):
    polar = ctx.get_polar()
    kn_list = (10, 18, 26)
    fig = plt.figure(figsize=(9.6, 7.4))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.78], hspace=0.36, wspace=0.12,
                          left=0.075, right=0.965, top=0.90, bottom=0.075)
    pd_, ud_ = polar.reduced()
    norm = TwoSlopeNorm(vmin=-2500, vcenter=0, vmax=3000)
    mask_meta = (polar.meta or {}).get("vpp_bug_mask")
    twa = polar.twa
    u = polar.u
    th_full = np.radians(np.concatenate([-twa[::-1], twa[1:]]))
    stats = {}
    mappable = None
    for c, kn in enumerate(kn_list):
        ax = fig.add_subplot(gs[0, c], projection="polar")
        it = _tws_index(polar, kn)
        p = polar.p[it]
        feas = polar.feasible[it]
        pf = np.concatenate([p[::-1], p[1:]], axis=0)
        ff = np.concatenate([feas[::-1], feas[1:]], axis=0)
        # cell edges
        dth = np.radians(twa[1] - twa[0])
        dr = u[1] - u[0]
        te = np.concatenate([th_full - dth / 2, [th_full[-1] + dth / 2]])
        re_ = np.concatenate([u - dr / 2, [u[-1] + dr / 2]])
        mappable = ax.pcolormesh(te, re_, np.ma.masked_invalid(pf).T, cmap="RdBu_r", norm=norm,
                                 rasterized=True)
        ax.contourf(th_full, u, (~ff).T.astype(float), levels=[0.5, 1.5], colors="none",
                    hatches=["/////"], zorder=3, rasterized=True)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rlim(0, 8.0)
        ax.set_rticks([2, 4, 6, 8])
        ax.set_thetagrids(range(0, 360, 45), [f"{abs(a if a <= 180 else a - 360)}°"
                                              for a in range(0, 360, 45)])
        ax.tick_params(labelsize=6.8, pad=1)
        ax.grid(True, color="#b9c0cc", lw=0.4)
        ax.set_rlabel_position(157)
        # optimum curve U*(TWA) where P>0
        up = np.where(np.isfinite(pd_[it]) & (pd_[it] > 60) & (ud_[it] >= 0.75), ud_[it], np.nan)
        upf = np.concatenate([up[::-1], up[1:]])
        ax.plot(th_full, upf, color=INK, lw=1.0, ls="--", zorder=5)
        if mask_meta:
            a0, u0 = mask_meta["twa_min_deg"], mask_meta["u_max_ms"]
            for sgn in (1, -1):
                t = np.radians(sgn * np.linspace(a0, 180, 40))
                ax.plot(np.concatenate([[np.radians(sgn * a0)], t, [np.radians(sgn * 180)]]),
                        np.concatenate([[0], np.full(40, u0), [0]]), color="#6a1b9a", lw=1.1,
                        zorder=6)
        ax.set_title(f"TWS = {kn} kn", fontsize=9, fontweight="bold", pad=8)
        kmax = int(np.nanargmax(pd_[it]))
        stats[f"pmax_{kn}"] = float(pd_[it][kmax])
        stats[f"twa_pmax_{kn}"] = float(twa[kmax])
        stats[f"u_pmax_{kn}"] = float(ud_[it][kmax])
        stats[f"pmin_{kn}"] = float(np.nanmin(p))
        stats[f"feasible_{kn}"] = float(feas.mean())
    cax = fig.add_axes([0.30, 0.468, 0.40, 0.013])
    cb = fig.colorbar(mappable, cax=cax, orientation="horizontal")
    cb.set_label("net power  P_net  [kW]   (blue < 0: the ship consumes; red > 0: it produces)",
                 fontsize=7.6)
    cb.ax.tick_params(labelsize=7)
    # legend proxies
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    handles = [Line2D([], [], color=INK, ls="--", lw=1.0, label="U*(TWA): speed of best P, where P > 0"),
               Patch(facecolor="white", edgecolor=MUTE, hatch="/////",
                     label="infeasible (speed not reachable at that angle)")]
    if mask_meta:
        handles.append(Line2D([], [], color="#6a1b9a", lw=1.1,
                              label="masked sector (VPP bug): TWA ≥ 135°, U ≤ 2.5 m/s"))
    handles.append(Line2D([], [], color="none", label="wind from the top: TWA 0° = head to wind; radius U [m/s]"))
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.995), ncol=2,
               fontsize=7.2, frameon=False)

    # (d) P-dagger curves
    ax = fig.add_subplot(gs[1, :])
    kns = [10, 14, 18, 22, 26, 30]
    cols = plt.cm.viridis(np.linspace(0.05, 0.9, len(kns)))
    for col, kn in zip(cols, kns, strict=True):
        it = _tws_index(polar, kn)
        ax.plot(twa, pd_[it], color=col, label=f"{kn} kn", lw=1.7 if kn in kn_list else 1.0)
    ax.axhline(0, color=INK, lw=0.8)
    ax.axvspan(75, 105, color=ORANGE, alpha=0.13, lw=0)
    ax.text(90, 3050, "beam reach 75-105°", ha="center", va="bottom", fontsize=7,
            color="#8a5a00")
    ax.set_xlim(0, 180)
    ax.set_xticks(range(0, 181, 15))
    ax.set_xlabel("true wind angle  TWA  [deg]   (0 = head to wind, 180 = dead downwind)")
    ax.set_ylabel("P†(TWA) = max over U of P_net  [kW]")
    ax.legend(title="TWS", ncol=1, loc="center left", bbox_to_anchor=(0.0, 0.62), fontsize=7, title_fontsize=7.4)
    it18 = _tws_index(polar, 18)
    k = int(np.nanargmax(pd_[it18]))
    ax.annotate(f"max {pd_[it18][k]:.0f} kW\nTWA {twa[k]:.0f}°, U {ud_[it18][k]:.1f} m/s",
                xy=(twa[k], pd_[it18][k]), xytext=(twa[k] + 18, pd_[it18][k] * 0.55),
                arrowprops={"arrowstyle": "->", "color": INK, "lw": 0.8}, fontsize=7.2)
    i0 = int(np.argmin(np.abs(twa - 0)))
    ax.annotate("head to wind: P ≤ 0\n(no thrust from the rotors)", xy=(0, pd_[it18][i0]),
                xytext=(9, pd_[it18][i0] + 700), arrowprops={"arrowstyle": "->", "color": INK, "lw": 0.8},
                fontsize=7.2)
    _panel(ax, "(d)", "Best net power over ship speed, per wind angle and wind speed")
    stats["p_dag_18"] = float(pd_[it18][k])
    stats["twa_dag_18"] = float(twa[k])
    stats["p_dag_head_18"] = float(pd_[it18][i0])
    fig.suptitle("")
    return fig, stats


# ========================================================================= figure 2: envelope
def fig_envelope(ctx: Ctx):
    polar, env = ctx.get_polar(), ctx.get_env()
    it = _tws_index(polar, 18)
    vp, vq = env.v_par_axis(), env.v_perp_axis()
    e, d, r = env.e[it], env.direct[it], env.reward[it]

    def mirror(a):  # (nvp, nvq>=0) -> (nvp, 2nvq-1) over v_perp in [-vmax, vmax]
        return np.concatenate([a[:, :0:-1], a], axis=1)

    vq_full = np.concatenate([-vq[:0:-1], vq])
    ip0 = int(round(-env.vp0 / env.dv))
    fig = plt.figure(figsize=(9.6, 6.9))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.12, 0.88], hspace=0.42, wspace=0.62,
                          left=0.07, right=0.955, top=0.94, bottom=0.08)
    norm = TwoSlopeNorm(vmin=-2600, vcenter=0, vmax=2100)
    ext = [vq_full[0] - env.dv / 2, vq_full[-1] + env.dv / 2, vp[0] - env.dv / 2, vp[-1] + env.dv / 2]
    axs = [fig.add_subplot(gs[0, k]) for k in range(3)]
    reach_only = np.isfinite(e) & ~np.isfinite(d)
    panels = [(d, "(a)", "One heading"),
              (r, "(b)", "Envelope (mixing)"),
              (np.where(np.isfinite(r), r - np.where(np.isfinite(d), d, np.nan), np.nan), "(c)",
               "Gain of mixing [kW]")]
    for ax, (a, tag, title) in zip(axs, panels, strict=True):
        if tag == "(c)":
            g = mirror(a)
            im2 = ax.imshow(np.ma.masked_invalid(g), origin="lower", extent=ext, aspect="equal",
                            cmap="magma_r", vmin=0, vmax=np.nanpercentile(a, 99), rasterized=True)
            cb = fig.colorbar(im2, ax=ax, fraction=0.046, pad=0.03)
            cb.ax.set_title("kW", fontsize=7.4, pad=4)
        else:
            im = ax.imshow(np.ma.masked_invalid(mirror(a)), origin="lower", extent=ext, aspect="equal",
                           cmap="RdBu_r", norm=norm, rasterized=True)
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03).ax.set_title("kW", fontsize=7.4, pad=4)
        ax.set_xlabel("v_perp  [m/s]  (across the wind)")
        ax.set_xlim(-8.5, 8.5)
        ax.set_ylim(-8.5, 8.5)
        ax.plot([0], [0], marker="*", ms=9, mfc="gold", mec=INK, mew=0.7, zorder=6)
        ax.axhline(0, color=INK, lw=0.4)
        ax.axvline(0, color=INK, lw=0.4)
        ax.grid(False)
        _panel(ax, tag, title)
    axs[0].set_ylabel("v_par  [m/s]  (towards the wind source)")
    axs[0].annotate("wind", xy=(-7.6, 7.8), xytext=(-7.6, 5.3), ha="center", fontsize=7,
                    arrowprops={"arrowstyle": "->"})
    fig.text(0.07, 0.505, "star = v 0 (station keeping)  |  white = velocity not reachable  |  wind blows from the top of each panel",
             fontsize=6.8, color=MUTE)

    # (d) cut along v_perp = 0
    ax = fig.add_subplot(gs[1, :2])
    ax.plot(vp, d[:, 0], color=GREY, lw=1.6, label="P_direct (one heading)")
    ax.plot(vp, e[:, 0], color=BLUE, lw=1.0, ls="--", label="E (concave envelope, no manoeuvre cost)")
    ax.plot(vp, r[:, 0], color=RED, lw=1.7, label="reward = max(P_direct, f_avail × E)")
    ax.axvline(0, color=INK, lw=0.5)
    ax.plot([0], [r[ip0, 0]], marker="*", ms=11, mfc="gold", mec=INK, zorder=6)
    ax.annotate(f"hold (v = 0): {r[ip0, 0]:.0f} kW\nvs {d[ip0, 0]:.0f} kW with one heading",
                xy=(0, r[ip0, 0]), xytext=(2.2, r[ip0, 0] + 150),
                arrowprops={"arrowstyle": "->"}, fontsize=7.4)
    ax.set_xlabel("v_par  [m/s]  (ground speed towards the wind source, v_perp = 0)")
    ax.set_ylabel("mean net power  [kW]")
    ax.set_xlim(vp[0], vp[-1])
    ax.legend(loc="lower left", fontsize=7)
    _panel(ax, "(d)", "Section along the wind axis, TWS = 18 kn")
    # (e) how a hold is built: two tacks
    ax = fig.add_subplot(gs[1, 2])
    # best operating point for hold: find leg that gives v = 0 mix
    from horizon.core.kinematics import station_keeping_twa
    best = None
    for uu in polar.u[polar.u >= 0.5]:
        th = float(station_keeping_twa(uu, polar.tws[it], 0.03))
        pp = float(polar(polar.tws[it], th, uu))
        if np.isfinite(pp) and (best is None or pp > best[2]):
            best = (th, float(uu), pp)
    th, uu, pp = best
    lw_ = 0.03 * polar.tws[it] * np.sin(np.radians(th))
    for sgn, col in ((1, BLUE), (-1, ORANGE)):
        vx = sgn * (uu * np.sin(np.radians(th)) + lw_ * np.cos(np.radians(th)))
        vy = uu * np.cos(np.radians(th)) - lw_ * np.sin(np.radians(th))
        ax.annotate("", xy=(vx, vy), xytext=(0, 0), arrowprops={"arrowstyle": "-|>", "color": col, "lw": 1.6})
        ax.text(vx * 0.95, vy + 0.6, f"{'starboard' if sgn > 0 else 'port'} tack\n"
                f"TWA {th:.0f}°, U {uu:.1f} m/s\nP {pp:.0f} kW", ha="center", fontsize=6.8, color=col)
    ax.plot([0], [0], marker="*", ms=11, mfc="gold", mec=INK, zorder=6)
    ax.set_xlim(-6, 6)
    ax.set_ylim(-4, 5.2)
    ax.set_aspect("equal")
    ax.set_xlabel("v_perp  [m/s]")
    ax.set_ylabel("v_par  [m/s]")
    ax.text(0, -3.6, "alternating the two tacks, equal time:\nmean ground velocity = 0", ha="center",
            fontsize=7, color=MUTE)
    _panel(ax, "(e)", "Why a hold produces power")
    stats = {"hold_env_kw": float(r[ip0, 0]), "hold_direct_kw": float(d[ip0, 0]),
             "hold_e_kw": float(e[ip0, 0]), "f_avail": float(env.f_avail),
             "gain_max_kw": float(np.nanmax(np.where(np.isfinite(d), r - d, np.nan))),
             "hold_twa": th, "hold_u": uu, "hold_p": pp,
             "reach_only_share": float(reach_only.sum() / max(np.isfinite(e).sum(), 1)),
             "vmax": float(np.nanmax(np.abs(vp[np.isfinite(e).any(axis=1)])))}
    return fig, stats


# ============================================================================ figure 3: DP
DP_T0_ISO = "2015-01-20T00:00:00"
DP_STEPS = 40  # 5 days of 3 h


def _start_xy(ctx: Ctx, grid):
    e = ctx.export
    if e and e.get("map", {}).get("start"):
        st = e["map"]["start"]
        return float(st["x_km"]) * 1e3, float(st["y_km"]) * 1e3
    return grid.to_xy(-21.6, 56.5)


def _dp_solve(ctx: Ctx):
    """Real backward DP (5 d, 3 h step, 49-arc stencil) on the 40 km ERA5 grid."""
    from horizon.dp.solver import solve_dp
    from horizon.dp.stencil import build_stencil

    wx, coast = ctx.get_weather(), ctx.get_coast()
    if wx is None or coast is None:
        raise FileNotFoundError("ERA5 cache not available")
    g = ctx.get_grid()
    t0 = float((np.datetime64(DP_T0_ISO) - np.datetime64("2015-01-01T00:00:00")) / np.timedelta64(1, "s"))
    dt = 10800.0
    truth = wx.truth(dt_s=dt, start_s=t0, end_s=t0 + DP_STEPS * dt)
    st = build_stencil(g, dt, max_span=2)
    dp = solve_dp(truth, t0, DP_STEPS, dt, ctx.get_polar(), ctx.get_hold(), coast, stencil=st,
                  envelope=ctx.get_env())
    x0, y0 = _start_xy(ctx, g)
    i0, j0 = (int(v) for v in g.index_of(x0, y0))
    path = dp.path(j0, i0, 0)
    return dp, truth, st, (j0, i0), path


def fig_dp(ctx: Ctx):
    dp, truth, st, (j0, i0), path = _dp_solve(ctx)
    g = ctx.get_grid()
    dt_h = st.dt_s / 3600.0
    X = (g.x0 + np.arange(g.nx) * g.dx) / 1e3
    Y = (g.y0 + np.arange(g.ny) * g.dx) / 1e3
    xs, ys = X[i0], Y[j0]
    fig = plt.figure(figsize=(9.6, 8.0))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.12, 0.88], hspace=0.34, wspace=0.28,
                          left=0.075, right=0.93, top=0.95, bottom=0.115)
    # (a) stencil on the real grid
    ax = fig.add_subplot(gs[0, 0])
    r = 5
    jj, ii = np.arange(j0 - r, j0 + r + 1), np.arange(i0 - r, i0 + r + 1)
    jj, ii = jj[(jj >= 0) & (jj < g.ny)], ii[(ii >= 0) & (ii < g.nx)]
    GX, GY = np.meshgrid(X[ii], Y[jj])
    w = truth.uv[0][np.ix_(jj, ii)]
    ws = np.hypot(w[..., 0], w[..., 1])
    ax.plot(GX, GY, ".", color="#c3c9d4", ms=2.5, zorder=1)
    q = ax.quiver(GX, GY, w[..., 0], w[..., 1], color="#9aa3b2", angles="xy",
                  scale_units="xy", scale=0.3, width=0.003, zorder=2)
    ax.quiverkey(q, 0.80, 0.05, 10, "10 m/s", labelpos="E", coordinates="axes")
    cmap = plt.cm.viridis
    spd = st.nominal_speed
    for k in range(1, st.n_arcs):
        a, b = st.di[k] * g.dx / 1e3, st.dj[k] * g.dx / 1e3
        col = cmap((spd[k] - 0.5) / 7.5)
        ax.plot([xs, xs + a], [ys, ys + b], color=col, lw=0.8 if st.span[k] == 1 else 0.7,
                ls="-" if st.span[k] == 1 else (0, (3, 1.5)), alpha=0.95, zorder=3)
        ax.plot([xs + a], [ys + b], "o", ms=3.2 if st.span[k] == 1 else 2.6, mfc=col,
                mec="white" if st.span[k] == 1 else col, mew=0.4, zorder=4)
    ax.plot([xs], [ys], "o", ms=7, mfc="gold", mec=INK, zorder=6)
    ax.set_xlim(X[ii[0]] - 12, X[ii[-1]] + 12)
    ax.set_ylim(Y[jj[0]] - 12, Y[jj[-1]] + 12)
    ax.set_aspect("equal")
    ax.set_xlabel("x  [km]  (LAEA projection, east)")
    ax.set_ylabel("y  [km]  (north)")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0.5, 8.0))
    plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.02).set_label("arc ground speed [m/s]", fontsize=7.4)
    n1, n2 = int((st.span[1:] == 1).sum()), int((st.span[1:] == 2).sum())
    _note(ax, 0.02, 0.945, f"{st.n_arcs} arcs = hold + {n1} one-step (solid, 3 h)\n"
          f"+ {n2} two-step (dashed, 6 h), 40 km grid", transform=ax.transAxes, fontsize=6.8, va="top")
    _panel(ax, "(a)", "Stencil of one node over the wind, to scale")
    # (b) value map at t0 and optimal path
    ax = fig.add_subplot(gs[0, 1])
    V0 = dp.V[0] / 1e3
    Vm = np.ma.masked_invalid(np.where(np.isfinite(V0), V0, np.nan))
    ext = [X[0] - g.dx / 2e3, X[-1] + g.dx / 2e3, Y[0] - g.dx / 2e3, Y[-1] + g.dx / 2e3]
    im = ax.imshow(Vm, origin="lower", extent=ext, cmap="YlGnBu", rasterized=True)
    land = np.where(dp.nav, np.nan, 1.0)
    ax.imshow(np.ma.masked_invalid(land), origin="lower", extent=ext, cmap="Greys", vmin=0, vmax=2.2,
              rasterized=True)
    px = (g.x0 + path.i * g.dx) / 1e3
    py = (g.y0 + path.j * g.dx) / 1e3
    px = np.append(px, (g.x0 + path.i_end[-1] * g.dx) / 1e3)
    py = np.append(py, (g.y0 + path.j_end[-1] * g.dx) / 1e3)
    ax.plot(px, py, color=RED, lw=1.5, label="optimal path (5 d)")
    ax.plot(px[0], py[0], "o", mfc="gold", mec=INK, ms=6, zorder=5, label="ship at t0")
    ax.axhline(ys, color=PURPLE, lw=0.9, ls=":")
    ax.text(ext[0] + 30, ys + 25, "transect of (c)", color=PURPLE, fontsize=7)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.02).set_label("V(x, y, t0)  [MWh]", fontsize=7.4)
    ax.set_xlabel("x  [km]")
    ax.set_ylabel("y  [km]")
    ax.set_aspect("equal")
    ax.legend(loc="lower left", fontsize=6.8)
    _note(ax, 0.98, 0.02, "grey: land, < 20 km from coast,\nor outside the ERA5 box", transform=ax.transAxes,
          ha="right", fontsize=6.6)
    _panel(ax, "(b)", "Value field at t0: energy-to-go from each node")
    # (c) V(x, t) on the transect
    ax = fig.add_subplot(gs[1, 0])
    Vt = dp.V[:, j0, :] / 1e3
    th = (dp.times_s - dp.times_s[0]) / 3600.0
    im = ax.imshow(np.ma.masked_invalid(np.where(np.isfinite(Vt), Vt, np.nan)), origin="lower",
                   extent=[X[0] - g.dx / 2e3, X[-1] + g.dx / 2e3, th[0] - dt_h / 2, th[-1] + dt_h / 2],
                   aspect="auto", cmap="YlGnBu", rasterized=True)
    pt = (dp.times_s[path.k] - dp.times_s[0]) / 3600.0
    ax.plot(px[:-1], pt, color=RED, lw=1.5, label="optimal path, x(t)")
    ax.set_ylim(-dt_h, th[-1] + dt_h)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.02).set_label("V(x, t)  [MWh]", fontsize=7.4)
    ax.set_xlabel("x  [km]  along the row y = %.0f km" % ys)
    ax.set_ylabel("time since t0  [h]")
    ax.grid(False)
    ax.legend(loc="upper left", fontsize=7)
    ax.text(X[-1], th[-1] - 6, "top edge: terminal value (here 0)", fontsize=7, color=INK, va="top", ha="right")
    _panel(ax, "(c)", "V(x, t) on one row; induction runs downwards")
    # (d) V along the path
    ax = fig.add_subplot(gs[1, 1])
    vk = np.array([dp.value_at((g.x0 + path.i[n] * g.dx), (g.y0 + path.j[n] * g.dx), int(path.k[n]))
                   for n in range(path.k.size)]) / 1e3
    ax.plot(pt, vk, color=BLUE, lw=1.6, label="V along the optimal path")
    ax.set_xlabel("time since t0  [h]")
    ax.set_ylabel("energy-to-go V  [MWh]", color=BLUE)
    ax2 = ax.twinx()
    ax2.step(pt, path.reward / dt_h / 1.0, where="post", color=ORANGE, lw=1.0, alpha=0.9)
    ax2.set_ylabel("mean power of the arc  [kW]", color=ORANGE)
    ax2.grid(False)
    ax2.set_ylim(-500, 3300)
    _note(ax, 0.03, 0.06, f"V(t0) = {vk[0]:.0f} MWh = energy of the plan\n"
          f"mean power {path.energy_kwh / (DP_STEPS * dt_h):.0f} kW over 120 h", transform=ax.transAxes)
    _panel(ax, "(d)", "V falls at the rate of the power harvested")
    fig.text(0.075, 0.035, "Recursion:   V_k(c) = max over arcs a of [ E(a; wind) + V_k+span(a) (c + a) ],      "
             "V_N(c) = V_terminal(c),      V = -inf on land and within 20 km of the coast", fontsize=8.0,
             color=INK, family="DejaVu Sans")
    stats = {"n_arcs": st.n_arcs, "n_one": n1, "n_two": n2, "v0_mwh": float(vk[0]),
             "mean_kw": float(path.energy_kwh / (DP_STEPS * dt_h)),
             "dist_km": float(np.sum(np.hypot(np.diff(px), np.diff(py)))),
             "vmax_mwh": float(np.nanmax(V0)), "vmin_mwh": float(np.nanmin(V0[np.isfinite(V0)])),
             "date": DP_T0_ISO[:10],
             "ws_start": float(ws[r, r]) if ws.shape[0] > r and ws.shape[1] > r else float("nan"),
             "span_max_km": float(np.max(np.hypot(st.di, st.dj) * g.dx / 1e3)),
             "n_nodes": int(g.nx * g.ny), "n_steps": DP_STEPS}
    return fig, stats


# ============================================================================ figure 4: MPC
MPC_T0_ISO = "2015-01-20T00:00:00"
MPC_N = 8  # successive plans, one per 6 h


def clim_hold_kw(ctx: Ctx):
    """Annual climatological hold power [kW] (Ny, Nx) from the cached monthly sums (or None)."""
    def make():
        acc, n = 0.0, 0
        for m in range(1, 13):
            f = _ROOT / "data" / "cache" / "s3" / f"hold_sum_2015_{m:02d}.npz"
            if not f.exists():
                return None
            z = np.load(f)
            acc = acc + z["s"]
            n += int(z["n"])
        return (acc / n).astype(np.float32)
    return ctx.lazy("clim", make)


def _track(ctx: Ctx, policy_name: str):
    sr = ctx.seed_run()
    if sr is None or policy_name not in sr["runs"]:
        raise KeyError(policy_name)
    r = sr["runs"][policy_name]
    t = np.asarray(sr["t_s"], float)
    return t, np.asarray(r["x_km"], float), np.asarray(r["y_km"], float), r


def _mpc_plans(ctx: Ctx):
    def make():
        from horizon.sim.policies import DeterministicMPCPolicy
        from horizon.sim.simulator import ForecastProvider

        wx, coast = ctx.get_weather(), ctx.get_coast()
        if wx is None or coast is None:
            raise FileNotFoundError("ERA5 cache not available")
        t, xk, yk, _ = _track(ctx, "B1_5d_REF")
        t0 = float((np.datetime64(MPC_T0_ISO) - np.datetime64("2015-01-01T00:00:00")) / np.timedelta64(1, "s"))
        pol = DeterministicMPCPolicy(ctx.get_polar(), ctx.get_hold(), coast, horizon_days=5.0)
        out = {"issue": [], "px": [], "py": [], "val": []}
        n_dest = int(5 * 8)
        for k in range(MPC_N):
            ts = t0 + k * 6 * 3600.0
            x = float(np.interp(ts, t, xk)) * 1e3
            y = float(np.interp(ts, t, yk)) * 1e3
            plan = pol.plan(ts, x, y, ForecastProvider(wx, ts, wx.duration_s))
            px = np.concatenate([[x], plan.x])[: n_dest + 1] / 1e3
            py = np.concatenate([[y], plan.y])[: n_dest + 1] / 1e3
            pad = n_dest + 1 - px.size
            if pad > 0:
                px, py = np.pad(px, (0, pad), mode="edge"), np.pad(py, (0, pad), mode="edge")
            out["issue"].append(ts)
            out["px"].append(px)
            out["py"].append(py)
            out["val"].append(plan.value_kwh)
        return {k: np.array(v) for k, v in out.items()}
    return ctx.npz_cache("mpc_plans_b1_" + MPC_T0_ISO[:10], make)


def fig_mpc(ctx: Ctx):
    t, xk, yk, run = _track(ctx, "B1_5d_REF")
    pl = _mpc_plans(ctx)
    t0 = pl["issue"][0]
    t_end = t0 + 72 * 3600.0
    sel = (t >= t0 - 3600) & (t <= t_end)
    cm = plt.cm.plasma
    fig = plt.figure(figsize=(9.6, 7.0))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1.0], hspace=0.40, wspace=0.30,
                          left=0.075, right=0.975, top=0.95, bottom=0.08)
    ax = fig.add_subplot(gs[:, 0])
    ax.plot(xk[sel], yk[sel], color=INK, lw=2.4, label="realised track (hourly, 72 h)", zorder=5)
    for k in range(pl["issue"].size):
        col = cm(k / max(pl["issue"].size - 1, 1) * 0.85)
        n_show = 2 * 8 + 1
        ax.plot(pl["px"][k][:n_show], pl["py"][k][:n_show], "-", color=col, lw=1.0, alpha=0.9, zorder=3)
        ax.plot(pl["px"][k][:1], pl["py"][k][:1], "o", color=col, ms=5, mec="white", mew=0.6, zorder=6)
        ax.plot(pl["px"][k][n_show - 1:n_show], pl["py"][k][n_show - 1:n_show], "s", color=col, ms=3.6, zorder=4)
    sm = plt.cm.ScalarMappable(cmap=cm, norm=plt.Normalize(0, (pl["issue"][-1] - t0) / 3600.0 / 0.85))
    cb = plt.colorbar(sm, ax=ax, fraction=0.035, pad=0.10, location="bottom")
    cb.set_label("plan issued at  [h after %s UTC]" % MPC_T0_ISO.replace("T", " ")[:16], fontsize=7.4)
    ax.set_xlabel("x  [km]  (LAEA, east)")
    ax.set_ylabel("y  [km]  (north)")
    ax.set_xlim(xk[sel].min() - 220, xk[sel].max() + 220)
    ax.set_ylim(yk[sel].min() - 220, yk[sel].max() + 330)
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="upper left", fontsize=7.2)
    _note(ax, 0.995, 0.03, "circle: ship at issue; square: plan at +48 h\n(only the first 48 h of each 5 d plan drawn)", transform=ax.transAxes, ha="right",
          fontsize=6.8)
    _panel(ax, "(a)", "6-hourly plans of B1 on the realised track")
    # (b) deviation of plans from the realised path vs lead
    ax = fig.add_subplot(gs[0, 1])
    lead = np.arange(pl["px"].shape[1]) * 3.0
    dev_all = []
    for k in range(pl["issue"].size):
        ts = pl["issue"][k] + lead * 3600.0
        ok = ts <= t[-1]
        xr = np.interp(ts, t, xk)
        yr = np.interp(ts, t, yk)
        dev = np.hypot(pl["px"][k] - xr, pl["py"][k] - yr)
        dev[~ok] = np.nan
        dev_all.append(dev)
        ax.plot(lead[:25], dev[:25], color=cm(k / max(pl["issue"].size - 1, 1) * 0.85), lw=1.0)
    dev_all = np.array(dev_all)
    ax.plot(lead[:25], np.nanmedian(dev_all, 0)[:25], color=INK, lw=2.0, label="median of the plans")
    ax.set_xlabel("lead time within the plan  [h]")
    ax.set_ylabel("distance plan - realised  [km]")
    ax.legend(loc="upper left", fontsize=7)
    _panel(ax, "(b)", "Distance plan vs sailed track")
    # (c) planned energy per replan
    ax = fig.add_subplot(gs[1, 1])
    tt = (pl["issue"] - t0) / 3600.0
    ax.bar(tt, pl["val"] / 1e3, width=4.2, color=[cm(k / max(pl["issue"].size - 1, 1) * 0.85)
                                                  for k in range(pl["issue"].size)])
    # realised energy over the following 5 d
    en = np.asarray(run["energy_kwh"], float)
    real = [(np.interp(ts + 5 * 86400, t, en) - np.interp(ts, t, en)) / 1e3 for ts in pl["issue"]]
    ax.plot(tt, real, "o-", color=INK, lw=1.2, ms=4, label="realised over the same 5 d (B1 run)")
    ax.set_xlabel("time of replan  [h after %s UTC]" % MPC_T0_ISO[:10])
    ax.set_ylabel("5 d energy  [MWh]")
    ax.set_ylim(0, max(np.nanmax(pl["val"]) / 1e3, np.nanmax(real)) * 1.25)
    ax.legend(loc="upper left", fontsize=7)
    _panel(ax, "(c)", "Energy promised vs delivered (5 d)")
    stats = {"n_plans": int(pl["issue"].size), "date": MPC_T0_ISO[:10],
             "dev24_km": float(np.nanmedian(dev_all[:, 8])), "dev48_km": float(np.nanmedian(dev_all[:, 16])),
             "dev12_km": float(np.nanmedian(dev_all[:, 4])),
             "val_mean_mwh": float(np.nanmean(pl["val"]) / 1e3), "real_mean_mwh": float(np.mean(real)),
             "val_min_mwh": float(np.nanmin(pl["val"]) / 1e3), "val_max_mwh": float(np.nanmax(pl["val"]) / 1e3),
             "end_shift_km": float(np.nanmean([np.hypot(*(pl["px"][k][-1:] - pl["px"][0][-1:]),
                                                         *(pl["py"][k][-1:] - pl["py"][0][-1:]))
                                                for k in range(1, pl["issue"].size)]))}
    return fig, stats


# ======================================================================= figure 5: forecasts
SKILL_ISSUES = {  # ISO dates of the verification issues (00 UTC), 8 per season
    "winter": ["2015-01-03", "2015-01-10", "2015-01-17", "2015-01-24", "2015-01-31", "2015-02-07",
               "2015-02-14", "2015-02-21"],
    "summer": ["2015-07-04", "2015-07-11", "2015-07-18", "2015-07-25", "2015-08-01", "2015-08-08",
               "2015-08-15", "2015-08-22"],
}
ENS_ISSUE_ISO = "2015-01-18T00:00:00"
ENS_LEAD_D = 5


def _s_of(iso: str) -> float:
    return float((np.datetime64(iso) - np.datetime64("2015-01-01T00:00:00")) / np.timedelta64(1, "s"))


def _skill(ctx: Ctx):
    from horizon.weather.forecast_model import forecast_skill

    def make():
        wx, coast = ctx.get_weather(), ctx.get_coast()
        if wx is None or coast is None:
            raise FileNotFoundError("ERA5 cache not available")
        mask = coast.sdf >= 20e3
        out = {}
        for season, days in SKILL_ISSUES.items():
            sk = forecast_skill(wx, [_s_of(d) for d in days], n_members=20, max_lead_days=10, mask=mask)
            for k in ("lead_days", "control_rmse", "mean_rmse", "spread"):
                out[f"{season}_{k}"] = sk[k]
        return out
    return ctx.npz_cache("skill_v2", make)


def _ens_case(ctx: Ctx):
    from horizon.ensemble.reduce import reduce_ensemble

    wx = ctx.get_weather()
    if wx is None:
        raise FileNotFoundError("ERA5 cache not available")
    ta = _s_of(ENS_ISSUE_ISO)
    ens = wx.forecast_cycle(ta, ENS_LEAD_D * 86400.0 + 6 * 3600.0, 20, dt_s=6 * 3600.0)
    red = reduce_ensemble(ens, k=6, window_s=(ta + 2 * 86400.0, ens.times_s[-1]))
    kt = int(np.argmin(np.abs(ens.times_s - (ta + ENS_LEAD_D * 86400.0))))
    sp = np.hypot(ens.uv[:, kt, ..., 0], ens.uv[:, kt, ..., 1])
    tr = wx._truth_at(ens.times_s[kt:kt + 1])[0]
    return ens, red, sp, np.hypot(tr[..., 0], tr[..., 1])


def fig_forecast(ctx: Ctx):
    sk = _skill(ctx)
    ens, red, sp, sp_true = _ens_case(ctx)
    g = ctx.get_grid()
    fig = plt.figure(figsize=(9.6, 8.4))
    gs = fig.add_gridspec(2, 6, height_ratios=[0.8, 1.2], hspace=0.36, wspace=1.1,
                          left=0.07, right=0.975, top=0.95, bottom=0.075)
    stats = {}
    for c, (season, ttl) in enumerate((("winter", "(a)  Winter (Jan-Feb 2015, 8 issues)"),
                                       ("summer", "(b)  Summer (Jul-Aug 2015, 8 issues)"))):
        ax = fig.add_subplot(gs[0, 3 * c:3 * c + 3])
        d = sk[f"{season}_lead_days"]
        ax.plot(d, sk[f"{season}_control_rmse"], "o-", color=ORANGE, ms=3, label="control: RMSE")
        ax.plot(d, sk[f"{season}_mean_rmse"], "s-", color=BLUE, ms=3, label="ensemble mean: RMSE")
        ax.plot(d, sk[f"{season}_spread"], "^--", color=GREEN, ms=3, label="ensemble spread")
        ax.set_xlabel("lead time  [days]")
        ax.set_ylabel("vector wind error  [m/s]")
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 8)
        ax.set_xticks(range(0, 11, 2))
        if c == 0:
            ax.legend(loc="upper left", fontsize=7)
        _panel(ax, ttl)
        for dd in (1, 3, 5, 7):
            stats[f"{season}_ctrl_d{dd}"] = float(sk[f"{season}_control_rmse"][dd])
            stats[f"{season}_mean_d{dd}"] = float(sk[f"{season}_mean_rmse"][dd])
            stats[f"{season}_spr_d{dd}"] = float(sk[f"{season}_spread"][dd])
    # (c) spaghetti map
    ax = fig.add_subplot(gs[1, :4])
    X = (g.x0 + np.arange(g.nx) * g.dx) / 1e3
    Y = (g.y0 + np.arange(g.ny) * g.dx) / 1e3
    land = ~ctx.get_coast().is_navigable(*g.xy_mesh(), 0.0)
    ax.imshow(np.ma.masked_where(~land, np.ones(land.shape)), origin="lower", cmap="Greys", vmin=0, vmax=2.4,
              extent=[X[0] - 20, X[-1] + 20, Y[0] - 20, Y[-1] + 20], zorder=0)
    lev = 14.0
    spread = sp.std(0, ddof=1)
    imm = ax.imshow(np.ma.masked_where(land, spread), origin="lower", cmap="YlOrRd", vmin=0, vmax=6,
                    extent=[X[0] - 20, X[-1] + 20, Y[0] - 20, Y[-1] + 20], zorder=1, rasterized=True)
    plt.colorbar(imm, ax=ax, fraction=0.04, pad=0.02).set_label("spread of the 20 members, wind speed [m/s]",
                                                               fontsize=7.4)
    for m in range(sp.shape[0]):
        if m not in set(int(v) for v in red.members):
            continue
    ax.contour(X, Y, sp.mean(0), levels=[lev], colors=[BLUE], linewidths=1.6, zorder=3)
    ax.contour(X, Y, sp[0], levels=[lev], colors=[GREEN], linewidths=1.3, linestyles="--", zorder=3)
    ax.contour(X, Y, sp_true, levels=[lev], colors=[INK], linewidths=2.0, zorder=4)
    from matplotlib.lines import Line2D
    hs = [Line2D([], [], color=INK, lw=2.0, label="truth (ERA5)"),
          Line2D([], [], color=GREEN, lw=1.3, ls="--", label="control member"),
          Line2D([], [], color=BLUE, lw=1.6, label="ensemble mean")]
    ax.legend(handles=hs, loc="lower left", fontsize=7, title="14 m/s contour", title_fontsize=7)
    ax.set_xlabel("x  [km]  (LAEA, east)")
    ax.set_ylabel("y  [km]  (north)")
    ax.set_aspect("equal")
    _panel(ax, "(c)", f"Wind at lead {ENS_LEAD_D} d, issue {ENS_ISSUE_ISO[:10]} 00 UTC")
    # (d) calibration: spread / error of the ensemble mean
    ax = fig.add_subplot(gs[1, 4:])
    for season, col in (("winter", BLUE), ("summer", ORANGE)):
        d = sk[f"{season}_lead_days"][1:]
        ax.plot(d, sk[f"{season}_spread"][1:] / sk[f"{season}_mean_rmse"][1:], "o-", ms=3.5, color=col, label=season)
    ax.axhline(1.0, color=INK, lw=0.9, ls="--")
    ax.set_ylim(0.6, 1.5)
    ax.set_xlim(0.5, 10)
    ax.set_xlabel("lead time  [days]")
    ax.set_ylabel("spread / RMSE of the mean  [-]")
    ax.legend(loc="upper left", fontsize=7)
    _note(ax, 0.97, 0.05, "1 = calibrated\n> 1 over-dispersive\n< 1 over-confident", transform=ax.transAxes,
          ha="right", fontsize=6.8)
    _panel(ax, "(d)", "Is the spread honest?")
    ratio = sk["winter_spread"][1:8] / sk["winter_mean_rmse"][1:8]
    ratio_s = sk["summer_spread"][1:8] / sk["summer_mean_rmse"][1:8]
    stats.update({"issue": ENS_ISSUE_ISO[:10], "contour": lev, "ratio_w": float(ratio.mean()),
                  "ratio_s": float(ratio_s.mean()), "sp_max": float(spread.max()), "sp_med": float(np.median(spread[~land]))})
    return fig, stats


# ================================================================= figure: ensembles and risk
def fig_ensemble(ctx: Ctx):
    from horizon.dp.stochastic import weighted_cvar

    ens, red, sp, sp_true = _ens_case(ctx)
    g = ctx.get_grid()
    x0, y0 = _start_xy(ctx, g)
    i0, j0 = (int(v) for v in g.index_of(x0, y0))
    hold = ctx.get_hold()
    wx = ctx.get_weather()
    t_d = (ens.times_s - ens.times_s[0]) / 86400.0
    w_mem = np.hypot(ens.uv[:, :, j0, i0, 0], ens.uv[:, :, j0, i0, 1])  # (M, T) [m/s]
    tr = wx._truth_at(ens.times_s)[:, j0, i0]
    w_true = np.hypot(tr[:, 0], tr[:, 1])
    ph = np.nan_to_num(hold.p_hold.astype(float))
    cols = [BLUE, ORANGE, GREEN, PURPLE, RED, TEAL]
    meds = [int(m) for m in red.members]
    win = (t_d >= 2.0) & (t_d <= 5.0)
    e_mem = np.interp(w_mem[:, win], hold.tws, ph).mean(1)  # mean hold power over days 2-5 [kW]
    wts = np.full(e_mem.size, 1.0 / e_mem.size)
    alpha = 0.2
    cv_all = float(weighted_cvar(e_mem[:, None], wts, alpha)[0])
    e_med = e_mem[meds]
    cv_med = float(weighted_cvar(e_med[:, None], red.weights, alpha)[0])
    mean_all, mean_med = float(e_mem.mean()), float((red.weights * e_med).sum())
    fig = plt.figure(figsize=(9.6, 7.6))
    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.28, left=0.075, right=0.93, top=0.95, bottom=0.075)
    ax = fig.add_subplot(gs[0, 0])
    for m in range(w_mem.shape[0]):
        if m not in meds:
            ax.plot(t_d, w_mem[m], color="#c5ccd8", lw=0.8)
    for n, m in enumerate(meds):
        ax.plot(t_d, w_mem[m], color=cols[n % 6], lw=1.5, label=f"#{m}  ({100 * red.weights[n]:.0f} %)")
    ax.plot(t_d, w_true, color=INK, lw=2.2, label="truth")
    ax.axvspan(0, 2, color=ORANGE, alpha=0.12, lw=0)
    ax.text(1.0, ax.get_ylim()[1] * 0.97, "48 h trunk\n(one plan for all)", ha="center", va="top", fontsize=6.8, color="#8a5a00")
    ax.set_xlabel("lead time since the issue  [days]")
    ax.set_ylabel("wind speed at the ship  [m/s]")
    ax.set_xlim(0, t_d[-1])
    ax.legend(loc="upper right", fontsize=6.4, ncol=2, title="medoid # (weight)", title_fontsize=6.6)
    _panel(ax, "(a)", f"20 members, 6 medoids, issue {ENS_ISSUE_ISO[:10]} 00 UTC")
    ax = fig.add_subplot(gs[0, 1])
    pcs = red.eof.pcs
    for n, m in enumerate(meds):
        sel = red.labels == n
        ax.scatter(pcs[sel, 0], pcs[sel, 1], s=22, color=cols[n % 6], alpha=0.8, edgecolor="white", lw=0.4)
        ax.scatter(pcs[m, 0], pcs[m, 1], s=130 + 800 * red.weights[n], marker="*", color=cols[n % 6], edgecolor=INK, lw=0.7, zorder=5)
    ax.set_ylim(ax.get_ylim()[0], ax.get_ylim()[1] + 160)
    ax.set_xlabel("PC 1 score  [m/s, weighted]")
    ax.set_ylabel("PC 2 score  [m/s, weighted]")
    cum = red.eof.cumulative
    _note(ax, 0.03, 0.97, f"PC 1 + PC 2 carry {100 * cum[min(1, cum.size - 1)]:.0f} % of the variance\n"
          f"{red.eof.n_modes} modes kept ({100 * cum[-1]:.0f} %)\nstar = medoid, size = weight", transform=ax.transAxes, va="top", fontsize=6.8)
    _panel(ax, "(b)", "Members in EOF space, clustered by PAM")
    ax = fig.add_subplot(gs[1, 0])
    order = np.argsort(e_mem)
    ax.bar(np.arange(e_mem.size), e_mem[order], color=["#c5ccd8" if int(o) not in meds else cols[meds.index(int(o)) % 6]
                                                         for o in order], edgecolor="white", lw=0.4)
    ax.axhline(mean_all, color=INK, lw=1.2, label=f"mean {mean_all:.0f} kW")
    ax.axhline(cv_all, color=RED, lw=1.2, ls="--", label=f"CVaR 20 % {cv_all:.0f} kW")
    ax.set_xticks([])
    ax.set_xlabel("the 20 members, sorted")
    ax.set_ylabel("mean hold power, days 2-5  [kW]")
    ax.legend(loc="upper left", fontsize=7)
    _panel(ax, "(c)", "What CVaR looks at: the worst 20 % of outcomes")
    ax = fig.add_subplot(gs[1, 1])
    xs = np.arange(red.k)
    ax.bar(xs - 0.2, 100 * red.weights, 0.4, color=[cols[n % 6] for n in range(red.k)], label="weight [%]")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"#{m}" for m in meds])
    ax.set_ylabel("scenario weight  [%]")
    ax.set_xlabel("medoid member")
    ax2 = ax.twinx()
    ax2.plot(xs, e_med, "ko", ms=4)
    ax2.set_ylim(min(e_med) - 150, max(e_med) + 450)
    ax2.set_ylabel("scenario hold power, days 2-5  [kW]")
    ax2.grid(False)
    _note(ax, 0.97, 0.97, f"from 6 scenarios:\nmean {mean_med:.0f} kW, CVaR {cv_med:.0f} kW\n(all 20: {mean_all:.0f} / {cv_all:.0f})",
          transform=ax.transAxes, ha="right", va="top", fontsize=6.8)
    ax.set_ylim(0, 52)
    _panel(ax, "(d)", "6 scenarios keep the mean and the tail")
    stats = {"k": int(red.k), "w_min": float(100 * red.weights.min()), "w_max": float(100 * red.weights.max()),
             "n_modes": int(red.eof.n_modes), "cum_modes": float(100 * cum[-1]), "cum2": float(100 * cum[min(1, cum.size - 1)]),
             "dist_expl": float(100 * red.distortion_explained), "mean_all": mean_all, "cvar_all": cv_all,
             "mean_med": mean_med, "cvar_med": cv_med, "e_min": float(e_mem.min()), "e_max": float(e_mem.max()),
             "issue": ENS_ISSUE_ISO[:10], "w_true5": float(w_true[np.argmin(np.abs(t_d - 5))]),
             "w_rng5": float(np.ptp(w_mem[:, np.argmin(np.abs(t_d - 5))]))}
    return fig, stats


# ===================================================================== figure 6: refiner
REF_T0_ISO = "2015-01-20T12:00:00"


def _refine_case(ctx: Ctx):
    def make():
        from horizon.sim.policies import DeterministicMPCPolicy
        from horizon.sim.policies_refine import RefinedMPCPolicy
        from horizon.sim.simulator import ForecastProvider

        wx, coast = ctx.get_weather(), ctx.get_coast()
        if wx is None or coast is None:
            raise FileNotFoundError("ERA5 cache not available")
        g = ctx.get_grid()
        t, xk, yk, _ = _track(ctx, "B1_5d_REF")
        ts = _s_of(REF_T0_ISO)
        x, y = float(np.interp(ts, t, xk)) * 1e3, float(np.interp(ts, t, yk)) * 1e3
        pol = DeterministicMPCPolicy(ctx.get_polar(), ctx.get_hold(), coast, horizon_days=5.0)
        ref = RefinedMPCPolicy(pol)
        prov = ForecastProvider(wx, ts, wx.duration_s)
        ref.plan(ts, x, y, prov)
        r = ref.last_refine
        if r is None:
            raise RuntimeError("refiner returned the base plan")
        res = pol.last_result
        j0, i0 = (int(v) for v in g.index_of(x, y))
        if not np.isfinite(res.V[0, j0, i0]):
            raise RuntimeError("start cell not navigable")
        path = res.path(j0, i0, 0)
        n = 16
        return {"r_t": r.t_s, "r_x": r.x, "r_y": r.y, "r_ve": r.ve, "r_vn": r.vn, "r_p": r.power_kw,
                "dp_k": path.k[:n], "dp_x": g.x0 + path.i[:n] * g.dx, "dp_y": g.y0 + path.j[:n] * g.dx,
                "dp_xe": g.x0 + path.i_end[:n] * g.dx, "dp_ye": g.y0 + path.j_end[:n] * g.dx,
                "dp_speed": path.speed[:n], "dp_kw": path.reward[:n] / (res.stencil.dt_s / 3600.0),
                "scalars": np.array([r.energy_kwh, r.warm_energy_kwh, r.terminal_kwh, r.penalty_kwh,
                                     r.iterations, float(r.success), ts, res.stencil.dt_s])}
    return ctx.npz_cache("refine_" + REF_T0_ISO[:13], make)


def fig_refiner(ctx: Ctx):
    c = _refine_case(ctx)
    sc = c["scalars"]
    e_ref, e_dp, term, pen, iters, ok, ts, dp_dt = sc
    h_dp = dp_dt / 3600.0
    t_h = (c["r_t"] - c["r_t"][0]) / 3600.0
    sp_ref = np.hypot(c["r_ve"], c["r_vn"])
    fig = plt.figure(figsize=(9.6, 7.0))
    gs = fig.add_gridspec(3, 2, width_ratios=[1.05, 1.0], hspace=0.50, wspace=0.28,
                          left=0.075, right=0.975, top=0.95, bottom=0.085)
    ax = fig.add_subplot(gs[:, 0])
    dpx = np.append(c["dp_x"], c["dp_xe"][-1]) / 1e3
    dpy = np.append(c["dp_y"], c["dp_ye"][-1]) / 1e3
    ax.plot(dpx, dpy, "o-", color=ORANGE, lw=1.5, ms=4.5, mec="white", mew=0.5,
            label="DP path (3 h nodes, 40 km grid)", zorder=4)
    ax.plot(c["r_x"] / 1e3, c["r_y"] / 1e3, "-", color=BLUE, lw=1.9, label="refined path (30 min stages)", zorder=5)
    ax.plot(c["r_x"][::6] / 1e3, c["r_y"][::6] / 1e3, "s", color=BLUE, ms=3.2, zorder=5)
    ax.plot([dpx[0]], [dpy[0]], "*", ms=13, mfc="gold", mec=INK, zorder=7, label="ship at issue")
    g = ctx.get_grid()
    xx = np.concatenate([dpx, c["r_x"] / 1e3])
    yy = np.concatenate([dpy, c["r_y"] / 1e3])
    pad = 60
    ax.set_xlim(xx.min() - pad, xx.max() + pad)
    ax.set_ylim(yy.min() - pad, yy.max() + pad)
    xt = (g.x0 + np.arange(g.nx) * g.dx) / 1e3
    yt = (g.y0 + np.arange(g.ny) * g.dx) / 1e3
    GX, GY = np.meshgrid(xt, yt)
    inb = (GX > xx.min() - pad) & (GX < xx.max() + pad) & (GY > yy.min() - pad) & (GY < yy.max() + pad)
    ax.plot(GX[inb], GY[inb], ".", color="#b9c0cc", ms=2.5, zorder=1, label="grid nodes")
    ax.set_xlabel("x  [km]  (LAEA, east)")
    ax.set_ylabel("y  [km]  (north)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="best", fontsize=7)
    _panel(ax, "(a)", "Same 48 h window: grid DP vs refiner")
    tu = f"hours after {REF_T0_ISO[:10]} {REF_T0_ISO[11:16]} UTC"
    # speed
    ax = fig.add_subplot(gs[0, 1])
    ax.step(np.arange(c["dp_speed"].size) * h_dp, c["dp_speed"], where="post", color=ORANGE, lw=1.5, label="DP")
    ax.plot((t_h[:-1] + t_h[1:]) / 2, sp_ref, color=BLUE, lw=1.4, label="refined")
    ax.set_ylabel("ground speed  [m/s]")
    ax.set_xlabel(tu)
    ax.set_xlim(0, 48)
    ax.legend(loc="upper right", fontsize=7, ncol=2)
    _panel(ax, "(b)", "Ground speed")
    # power
    ax = fig.add_subplot(gs[1, 1])
    ax.step(np.arange(c["dp_kw"].size) * h_dp, c["dp_kw"], where="post", color=ORANGE, lw=1.5, label="DP")
    ax.plot((t_h[:-1] + t_h[1:]) / 2, c["r_p"], color=BLUE, lw=1.4, label="refined")
    ax.set_ylabel("net power  [kW]")
    ax.set_xlabel(tu)
    ax.set_xlim(0, 48)
    _panel(ax, "(c)", "Power on the envelope")
    # cumulative energy
    ax = fig.add_subplot(gs[2, 1])
    ax.step(np.arange(c["dp_kw"].size + 1) * h_dp, np.concatenate([[0], np.cumsum(c["dp_kw"] * h_dp)]) / 1e3,
            where="post", color=ORANGE, lw=1.5, label="DP")
    ax.plot(t_h, np.concatenate([[0], np.cumsum(c["r_p"] * 0.5)]) / 1e3, color=BLUE, lw=1.4, label="refined")
    ax.set_ylabel("cumulated energy  [MWh]")
    ax.set_xlabel(tu)
    ax.set_xlim(0, 48)
    _panel(ax, "(d)", "Energy over the window")
    e_dp48 = float(np.sum(c["dp_kw"] * h_dp)) / 1e3
    e_rf48 = float(np.sum(c["r_p"] * 0.5)) / 1e3
    stats = {"e_dp": e_dp48, "e_ref": e_rf48, "gain_pct": 100 * (e_rf48 / e_dp48 - 1) if e_dp48 else 0.0,
             "iters": int(iters), "dist_dp": float(np.sum(np.hypot(np.diff(dpx), np.diff(dpy)))),
             "dist_ref": float(np.sum(np.hypot(np.diff(c["r_x"]), np.diff(c["r_y"]))) / 1e3),
             "date": REF_T0_ISO[:10], "hour": REF_T0_ISO[11:16],
             "vmax_ref": float(sp_ref.max()), "vmin_ref": float(sp_ref.min()),
             "turn_dp": float(np.nanmean(np.abs(np.diff(c["dp_speed"])))) ,
             "turn_ref": float(np.mean(np.abs(np.diff(sp_ref))))}
    ax.text(0.03, 0.95, f"DP {e_dp48:.1f} MWh  /  refined {e_rf48:.1f} MWh ({stats['gain_pct']:+.1f} %)",
            transform=ax.transAxes, va="top", fontsize=7.2,
            bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": GRID})
    return fig, stats


# ==================================================================== figure 7: terminal value
VT_T0_ISO = "2015-01-20T00:00:00"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _vtheta_map(ctx: Ctx):
    def make():
        from horizon.sim.simulator import ForecastProvider
        from horizon.value.model import ValueModel, ValueTerminal

        model_f = _ROOT / "data" / "cache" / "value" / "models" / "vtheta_pol_all.joblib"
        wx, coast, clim = ctx.get_weather(), ctx.get_coast(), clim_hold_kw(ctx)
        if wx is None or coast is None or clim is None or not model_f.exists():
            raise FileNotFoundError("value model / ERA5 / climatology not available")
        hold = ctx.get_hold()
        vt = ValueTerminal(ValueModel.load(model_f), ctx.get_grid(), clim, coast.sdf, wx.epoch,
                           hold.tws, np.nan_to_num(hold.p_hold.astype(float)))
        ts = _s_of(VT_T0_ISO)
        prov = ForecastProvider(wx, ts, wx.duration_s)
        v = vt(ts, ts + 5 * 86400.0, prov)
        return {"v": v, "nav": coast.sdf >= 20e3}
    return ctx.npz_cache("vtheta_map_" + VT_T0_ISO[:10], make)


def fig_terminal(ctx: Ctx):
    g = ctx.get_grid()
    clim = clim_hold_kw(ctx)
    if clim is None:
        raise FileNotFoundError("climatology")
    vm = _vtheta_map(ctx)
    nav = vm["nav"]
    ext = [(g.x0 - g.dx / 2) / 1e3, (g.x0 + (g.nx - 0.5) * g.dx) / 1e3,
           (g.y0 - g.dx / 2) / 1e3, (g.y0 + (g.ny - 0.5) * g.dx) / 1e3]
    fig = plt.figure(figsize=(9.6, 8.0))
    gs = fig.add_gridspec(2, 2, hspace=0.34, wspace=0.40, left=0.075, right=0.94, top=0.95, bottom=0.075)
    for c, (arr, ttl, lab, vmax) in enumerate((
            (np.where(nav, clim, np.nan), "(a)  Climatological hold power, 2015 mean", "P_clim  [kW]", 3000),
            (np.where(nav, vm["v"] / 1e3, np.nan), f"(b)  Learned value V_theta, {VT_T0_ISO[:10]}",
             "5 d energy-to-go  [MWh]", None))):
        ax = fig.add_subplot(gs[0, c])
        im = ax.imshow(np.ma.masked_invalid(arr), origin="lower", extent=ext, cmap="YlGnBu", vmin=0,
                       vmax=vmax, rasterized=True)
        ax.imshow(np.ma.masked_where(nav, np.ones(nav.shape)), origin="lower", extent=ext, cmap="Greys",
                  vmin=0, vmax=2.4, rasterized=True)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.02).set_label(lab, fontsize=7.4)
        ax.set_xlabel("x  [km]")
        ax.set_ylabel("y  [km]")
        ax.set_aspect("equal")
        ax.grid(False)
        _panel(ax, ttl)
    stats = {"clim_min": float(np.nanmin(np.where(nav, clim, np.nan))),
             "clim_max": float(np.nanmax(np.where(nav, clim, np.nan))),
             "clim_med": float(np.nanmedian(np.where(nav, clim, np.nan))),
             "clim120_med": float(np.nanmedian(np.where(nav, clim, np.nan)) * 120 / 1e3),
             "vt_min": float(np.nanmin(np.where(nav, vm["v"], np.nan)) / 1e3),
             "vt_max": float(np.nanmax(np.where(nav, vm["v"], np.nan)) / 1e3),
             "vt_med": float(np.nanmedian(np.where(nav, vm["v"], np.nan)) / 1e3), "date": VT_T0_ISO[:10]}
    # (c) E0
    ax = fig.add_subplot(gs[1, 0])
    f = Path(ctx.value_dir) / "E0_results.json"
    if f.exists():
        e0 = json.loads(f.read_text())["by_month_rollout"]
        mo = [int(k) for k in e0 if e0[k]]
        bias = [e0[str(m)]["mean_kwh"] / 1e3 for m in mo]
        rel = [e0[str(m)]["rel_pct"] for m in mo]
        se = [e0[str(m)]["se_kwh"] / 1e3 for m in mo]
        ax.bar(mo, bias, yerr=se, color=BLUE, alpha=0.85, error_kw={"lw": 0.8})
        ax.set_xticks(mo)
        ax.set_xticklabels([MONTHS[m - 1] for m in mo])
        ax.set_ylabel("hindsight bias  [MWh over 5 d]", color=BLUE)
        ax2 = ax.twinx()
        ax2.plot(mo, rel, "o-", color=ORANGE, lw=1.4, ms=4)
        ax2.set_ylabel("bias / hindsight value  [%]", color=ORANGE)
        ax2.set_ylim(0, 25)
        ax2.grid(False)
        allr = json.loads(f.read_text())["by_H_source"]["H5d_rollout"]
        stats.update({"e0_all_pct": float(allr["rel_pct"]), "e0_all_mwh": float(allr["mean_kwh"] / 1e3),
                      "e0_min_pct": float(min(rel)), "e0_max_pct": float(max(rel)),
                      "e0_max_month": MONTHS[mo[int(np.argmax(rel))] - 1],
                      "e0_min_month": MONTHS[mo[int(np.argmin(rel))] - 1],
                      "vhind_mwh": float(allr["V_hind_mean"] / 1e3), "vpol_mwh": float(allr["V_pol_mean"] / 1e3)})
    else:
        raise FileNotFoundError(f)
    _panel(ax, "(c)", "Hindsight bias by month (E0)")
    # (d) MAE by month of terminal-value candidates
    ax = fig.add_subplot(gs[1, 1])
    cv = json.loads((Path(ctx.value_dir) / "Vtheta_cv.json").read_text())
    mo = sorted(int(k) for k in cv["by_month"] if cv["by_month"][k])
    names = [("clim", "climatology x 120 h", GREY), ("clim_cal", "climatology, recalibrated", ORANGE),
             ("hind_big", "learned on hindsight", PURPLE), ("pol", "learned on causal runs (V_theta)", BLUE)]
    for k, lab, col in names:
        ax.plot(mo, [cv["by_month"][str(m)][k] / 1e3 for m in mo], "o-", ms=3.5, color=col, label=lab,
                lw=2.0 if k == "pol" else 1.2)
    ax.set_xticks(mo)
    ax.set_xticklabels([MONTHS[m - 1] for m in mo])
    ax.set_ylabel("mean absolute error of the 5 d value  [MWh]")
    ax.legend(loc="upper left", fontsize=6.8)
    ax.set_ylim(0, None)
    _panel(ax, "(d)", "Held-out-month error of candidate values")
    r = cv["metrics"]["rollout"]
    stats.update({"mae_pol": r["pol"]["MAE_kwh"] / 1e3, "mae_clim_cal": r["clim_cal"]["MAE_kwh"] / 1e3,
                  "mae_hind": r["hind_big"]["MAE_kwh"] / 1e3, "mae_clim": r["clim"]["MAE_kwh"] / 1e3,
                  "r2_pol": r["pol"]["R2"], "r2_clim_cal": r["clim_cal"]["R2"], "r2_hind": r["hind_big"]["R2"],
                  "target_mean": r["pol"]["mean_target_kwh"] / 1e3})
    return fig, stats


# ======================================================================== figure 8: results
def _month_edges_h(t_s, epoch):
    """Hour-sample index of each month start for an hourly series."""
    e = np.datetime64(epoch[:19])
    ab = e + np.round(np.asarray(t_s, float)).astype("timedelta64[s]")
    mon = ab.astype("datetime64[M]").astype(int) % 12
    return mon


def monthly_cf(export: dict):
    """Per-router monthly capacity factor [-] (and energy [MWh]) from the exported hourly tracks."""
    sr = export["seeds"][0]
    p_rated = float(export["meta"].get("p_rated_kw", 3000.0))
    t = np.asarray(sr["t_s"], float)
    mon = _month_edges_h(t, sr["epoch"] if "epoch" in sr else export["meta"]["epoch"])
    out = {}
    for name, r in sr["runs"].items():
        e = np.asarray(r["energy_kwh"], float)
        pw = np.diff(e)  # kWh per hour
        m = mon[1:]
        cf = np.array([pw[m == k].sum() / (p_rated * (m == k).sum()) if (m == k).any() else np.nan
                       for k in range(12)])
        mwh = np.array([pw[m == k].sum() / 1e3 for k in range(12)])
        out[name] = {"cf": cf, "mwh": mwh, "total": e[-1] / 1e3, "e": e}
    return out, p_rated


def fig_results(ctx: Ctx):
    if not ctx.export or not ctx.export.get("seeds"):
        raise KeyError("export")
    res, p_rated = monthly_cf(ctx.export)
    ref = ctx.export["meta"].get("reference", "Oracle_REF_H")
    names = [n for n in POLICY_STYLE if n in res] + [n for n in res if n not in POLICY_STYLE]
    sr = ctx.seed_run()
    t_h = np.asarray(sr["t_s"], float) / 86400.0
    fig = plt.figure(figsize=(9.6, 8.0))
    gs = fig.add_gridspec(2, 2, hspace=0.36, wspace=0.28, left=0.075, right=0.975, top=0.95, bottom=0.15)
    mo = np.arange(12)
    ax = fig.add_subplot(gs[0, 0])
    for n in names:
        col, ls, lab = POLICY_STYLE.get(n, (GREY, "-", n))
        ax.plot(mo, 100 * res[n]["cf"], ls, color=col, marker="o", ms=3, label=lab, lw=1.9 if n == ref else 1.3)
    ax.set_xticks(mo)
    ax.set_xticklabels(MONTHS, fontsize=7)
    ax.set_ylabel("capacity factor  [%]   (100 % = 3 MW all year)")
    ax.set_ylim(30, 100)
    ax.legend(loc="lower left", fontsize=6.8, ncol=1)
    _panel(ax, "(a)", "Monthly capacity factor, 2015")
    ax = fig.add_subplot(gs[0, 1])
    others = [n for n in names if n != ref]
    w = 0.8 / max(len(others), 1)
    for i, n in enumerate(others):
        col, _, lab = POLICY_STYLE.get(n, (GREY, "-", n))
        ax.bar(mo + (i - (len(others) - 1) / 2) * w, 100 * (res[ref]["cf"] - res[n]["cf"]), w * 0.95,
               color=col, label=lab)
    ax.set_xticks(mo)
    ax.set_xticklabels(MONTHS, fontsize=7)
    ax.set_ylabel("gap to the oracle  [percentage points of CF]")
    ax.legend(loc="upper left", fontsize=6.8, ncol=2)
    _panel(ax, "(b)", "Gap to the hindsight oracle")
    # (c) energy budget
    ax = fig.add_subplot(gs[1, 0])
    hold = {n: np.asarray(sr["runs"][n]["hold_frac"], float) for n in names}
    for i, n in enumerate(names):
        e = res[n]["e"]
        pw = np.diff(e)
        hold_e = float((pw * hold[n]).sum()) / 1e3
        sail_e = res[n]["total"] - hold_e
        col = POLICY_STYLE.get(n, (GREY,))[0]
        ax.bar(i, sail_e / 1e3, color=col, alpha=0.95, width=0.62)
        ax.bar(i, hold_e / 1e3, bottom=sail_e / 1e3, color=col, alpha=0.45, width=0.62, hatch="///",
               edgecolor="white")
        gap = res[ref]["total"] - res[n]["total"]
        if n != ref:
            ax.bar(i, gap / 1e3, bottom=res[n]["total"] / 1e3, color="none", edgecolor=INK, ls="--", lw=0.8,
                   width=0.62)
        cf = 100 * res[n]["total"] * 1e3 / (p_rated * 8760.0)
        ax.text(i, res[ref]["total"] / 1e3 + 0.4 if n != ref else res[n]["total"] / 1e3 + 0.4,
                f"{cf:.1f} %", ha="center", fontsize=7.2, fontweight="bold")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([POLICY_STYLE.get(n, (0, 0, n))[2].replace(" fixed station", "\nfixed st.") for n in names],
                       fontsize=7)
    ax.set_ylabel("energy over 2015  [GWh]")
    ax.set_ylim(0, res[ref]["total"] / 1e3 * 1.12)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(fc=GREY, label="while sailing"), Patch(fc=GREY, alpha=0.45, hatch="///", ec="white",
                                                                    label="while holding"),
                       Patch(fc="none", ec=INK, ls="--", label="gap to oracle")], loc="lower right", fontsize=6.6)
    _panel(ax, "(c)", "Annual energy budget (label: annual CF)")
    # (d) cumulative gap
    ax = fig.add_subplot(gs[1, 1])
    for n in others:
        col, ls, lab = POLICY_STYLE.get(n, (GREY, "-", n))
        ax.plot(t_h, (res[ref]["e"] - res[n]["e"]) / 1e6, ls, color=col, label=lab, lw=1.4)
    ax.set_xlabel("day of 2015 (UTC)")
    ax.set_ylabel("cumulated shortfall vs oracle  [GWh]")
    ax.set_xlim(0, 365)
    ax.set_xticks([0, 59, 120, 181, 243, 304, 365])
    ax.set_xticklabels(["1 Jan", "1 Mar", "1 May", "1 Jul", "1 Sep", "1 Nov", "31 Dec"], fontsize=7)
    ax.legend(loc="upper left", fontsize=6.8)
    _panel(ax, "(d)", "Where the energy is lost during the year")
    fig.text(0.075, 0.045, "B0 = optimal fixed station (perfect hindsight): ship held still at the best location of 2015\n"
             "(argmax of the 2015 mean hold power of the ERA5 truth; >= 50 km from the coast; within 800 NM of 47N 6.5W).\n"
             "Oracle = rolling 15 d look-ahead on the true wind + refiner (not causal, approximate bound).",
             fontsize=7.2, color=MUTE, va="bottom")
    stats = {}
    for n in names:
        tag = {"Oracle_REF_H": "or", "B0": "b0", "B1_5d_REF": "b1", "B1c_5d_REF": "b1c", "ENS_REF": "ens"}.get(n, n)
        cf = 100 * res[n]["total"] * 1e3 / (p_rated * 8760.0)
        stats[f"cf_{tag}"] = cf
        stats[f"mwh_{tag}"] = res[n]["total"]
        stats[f"gap_{tag}"] = 100 * res[ref]["total"] * 1e3 / (p_rated * 8760.0) - cf
        stats[f"cfmin_{tag}"] = 100 * float(np.nanmin(res[n]["cf"]))
        stats[f"cfmax_{tag}"] = 100 * float(np.nanmax(res[n]["cf"]))
        stats[f"holdshare_{tag}"] = 100 * float(np.sum(np.diff(res[n]["e"]) * hold[n]) / max(np.sum(np.diff(res[n]["e"])), 1))
    if "B1c_5d_REF" in res and "B1_5d_REF" in res:
        stats["clim_gain_pp"] = stats["cf_b1c"] - stats["cf_b1"]
    if "ENS_REF" in res and "B1c_5d_REF" in res:
        stats["ens_gain_pp"] = stats["cf_ens"] - stats["cf_b1c"]
    gapm = {n: 100 * (res[ref]["cf"] - res[n]["cf"]) for n in others}
    if "B1c_5d_REF" in gapm:
        stats["gap_b1c_worst"] = float(np.nanmax(gapm["B1c_5d_REF"]))
        stats["gap_b1c_worst_m"] = MONTHS[int(np.nanargmax(gapm["B1c_5d_REF"]))]
        stats["gap_b1c_best"] = float(np.nanmin(gapm["B1c_5d_REF"]))
        stats["gap_b1c_best_m"] = MONTHS[int(np.nanargmin(gapm["B1c_5d_REF"]))]
    stats["cf_or_worst_m"] = MONTHS[int(np.nanargmin(res[ref]["cf"]))]
    stats["cf_or_best_m"] = MONTHS[int(np.nanargmax(res[ref]["cf"]))]
    return fig, stats


# ======================================================================== figure 9: safety
LORIENT = (-3.4, 47.7)
D_MIN_KM, D_PORT_KM, RAMP_KM = 20.0, 1.0, 40.0
RUN_DIRS = {"Oracle_REF_H": "A_OracleH", "B0": "A_B0", "B1_5d_REF": "A_B1_REF_s1",
            "B1c_5d_REF": "A_B1c_REF_s1", "ENS_REF": "A_ENS_REF_s1"}


def _min_margins(ctx: Ctx) -> dict:
    """Exact minimum margin to the 20 km limit [km] of each year run (run_info.json / results)."""
    out = {}
    f = ctx.results_json or (_ROOT / "outputs" / "S4_results.json")
    if Path(f).exists():
        for k, v in json.loads(Path(f).read_text()).get("safety", {}).items():
            name = k.split(" ")[0]
            if " s1" in k or " " not in k:
                out[name] = v
    for name, d in RUN_DIRS.items():
        ri = Path(ctx.runs_dir) / d / "run_info.json"
        if name not in out and ri.exists():
            j = json.loads(ri.read_text())
            out[name] = {"min_margin_km": j.get("min_margin_km"), "coast_violations": j.get("coast_violations", 0),
                         "guard_interventions": j.get("guard_interventions", 0)}
    return out


def fig_safety(ctx: Ctx):
    from horizon.geo.coast import build_basin_coast, port_corridor

    coast = build_basin_coast(10e3)
    g = coast.grid
    px, py = g.to_xy(*LORIENT)
    cor = port_corridor(coast, *LORIENT, d_min=D_MIN_KM * 1e3, d_port=D_PORT_KM * 1e3, ramp_m=RAMP_KM * 1e3)
    X, Y = g.xy_mesh()
    rx, ry = (X - px) / 1e3, (Y - py) / 1e3
    box = (np.abs(rx) < 330) & (np.abs(ry) < 260)
    jj, ii = np.where(box)
    sl = (slice(jj.min(), jj.max() + 1), slice(ii.min(), ii.max() + 1))
    fig = plt.figure(figsize=(9.6, 7.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 0.75], hspace=0.36, wspace=0.28,
                          left=0.075, right=0.965, top=0.95, bottom=0.075)
    ax = fig.add_subplot(gs[0, 0])
    sd = coast.true_sdf[sl] / 1e3
    im = ax.pcolormesh(rx[sl], ry[sl], np.ma.masked_where(sd < 0, np.minimum(sd, 200)), cmap="YlGnBu",
                       vmin=0, vmax=200, shading="auto", rasterized=True)
    ax.pcolormesh(rx[sl], ry[sl], np.ma.masked_where(sd >= 0, np.ones(sd.shape)), cmap="Greys", vmin=0, vmax=2.4,
                  shading="auto", rasterized=True)
    ax.contour(rx[sl], ry[sl], coast.true_sdf[sl] / 1e3, levels=[D_MIN_KM], colors=[RED], linewidths=1.4)
    ax.contour(rx[sl], ry[sl], cor.sdf[sl] / 1e3, levels=[D_MIN_KM], colors=[INK], linewidths=1.4,
               linestyles="--")
    ax.plot([0], [0], "*", ms=13, mfc="gold", mec=INK, zorder=6)
    ax.annotate("Lorient", xy=(0, 0), xytext=(-250, -60), fontsize=8, arrowprops={"arrowstyle": "->"})
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.02).set_label("distance to coast  SDF  [km] (capped at 200)",
                                                               fontsize=7.4)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], color=RED, lw=1.4, label="SDF = 20 km (nominal limit)"),
                       Line2D([], [], color=INK, lw=1.4, ls="--", label="limit with the Lorient corridor")],
              loc="upper left", fontsize=6.8)
    ax.set_xlabel("km east of Lorient")
    ax.set_ylabel("km north of Lorient")
    ax.set_aspect("equal")
    ax.grid(False)
    _panel(ax, "(a)", "Coast margin around Brittany (10 km grid)")
    # (b) required clearance vs distance to the port
    ax = fig.add_subplot(gs[0, 1])
    r = np.linspace(0, 80, 400)
    d_req = D_PORT_KM + (D_MIN_KM - D_PORT_KM) * np.minimum(r / RAMP_KM, 1)
    ax.plot(r, d_req, color=INK, lw=1.8, label="required clearance d_req(r)")
    ax.fill_between(r, 0, d_req, color=RED, alpha=0.10, label="forbidden")
    ax.fill_between(r, d_req, 25, color=GREEN, alpha=0.08, label="navigable")
    ax.axhline(D_MIN_KM, color=RED, lw=0.9, ls=":")
    ax.text(79, D_MIN_KM + 0.5, "20 km", ha="right", fontsize=7, color=RED)
    ax.text(1.5, D_PORT_KM + 1.0, "1 km at the port", fontsize=7)
    ax.set_xlim(0, 80)
    ax.set_ylim(0, 25)
    ax.set_xlabel("distance to Lorient  r  [km]")
    ax.set_ylabel("required distance to coast  [km]")
    ax.legend(loc="lower right", fontsize=7)
    _note(ax, 0.04, 0.58, "d_req = 1 + 19 min(r / 40 km, 1)\nimplemented as an SDF relaxation:\n"
          "SDF' = SDF + (20 - d_req)  >=  20 km", transform=ax.transAxes, fontsize=6.8)
    _panel(ax, "(b)", "Harbour corridor: the limit ramps from 1 to 20 km")
    # (c) distribution of the hourly distance to coast along the tracks
    ax = fig.add_subplot(gs[1, 0])
    stats = {}
    mm = _min_margins(ctx)
    sr = ctx.seed_run()
    if sr and ctx.export.get("map", {}).get("sdf"):
        sdf_e = decode_array(ctx.export["map"]["sdf"]).astype(float) * ctx.export["map"]["sdf"].get("unit_km", 0.1)
        ge = ctx.export["map"]["grid"]
        for n, (col, ls, lab) in POLICY_STYLE.items():
            if n not in sr["runs"] or n == "B0":
                continue
            xk, yk = np.asarray(sr["runs"][n]["x_km"]), np.asarray(sr["runs"][n]["y_km"])
            fi = (xk - ge["x0_km"]) / ge["dx_km"]
            fj = (yk - ge["y0_km"]) / ge["dx_km"]
            from scipy.ndimage import map_coordinates
            d = map_coordinates(sdf_e, [fj, fi], order=1, mode="nearest")
            vals = np.sort(d)
            ax.plot(vals, 100 * np.arange(1, vals.size + 1) / vals.size, color=col, ls=ls, label=lab, lw=1.5)
            stats[f"p1_{n}"] = float(np.percentile(d, 1))
            stats[f"frac100_{n}"] = float(100 * np.mean(d < 100))
            stats[f"min_{n}"] = float(d.min())
    ax.axvline(D_MIN_KM, color=RED, ls=":", lw=1.0)
    ax.set_xscale("log")
    ax.set_xlim(15, 1500)
    ax.set_xticks([20, 50, 100, 200, 500, 1000])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.minorticks_off()
    ax.set_xlabel("distance to coast along the hourly track  [km]  (log scale)")
    ax.set_ylabel("share of the year below  [%]")
    ax.legend(loc="upper left", fontsize=6.8)
    ax.text(D_MIN_KM * 1.04, 50, "20 km limit", rotation=90, fontsize=7, color=RED, va="center")
    _panel(ax, "(c)", "How close the routers sail to land (2015)")
    # (d) min margin table
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    rows = []
    for n, (_col, _ls, lab) in POLICY_STYLE.items():
        v = mm.get(n)
        if v is None:
            continue
        mmg = v.get("min_margin_km")
        rows.append([lab, f"{mmg:.2f}" if mmg is not None and mmg < 100 else "n/a (static)",
                     str(v.get("coast_violations", 0)), str(v.get("guard_interventions", 0))])
        stats[f"mm_{n}"] = float(mmg) if mmg is not None else float("nan")
    if rows:
        tb = ax.table(cellText=rows, colLabels=["router", "min margin\n[km]", "limit\nviolations", "guard\ninterventions"],
                      loc="upper center", cellLoc="center", colLoc="center")
        tb.auto_set_font_size(False)
        tb.set_fontsize(7.4)
        tb.scale(1.0, 1.55)
        for (rr, _cc), cell in tb.get_celld().items():
            cell.set_edgecolor(GRID)
            if rr == 0:
                cell.set_facecolor("#eef1f6")
                cell.set_text_props(fontweight="bold", fontsize=7)
    ax.text(0.5, 0.02, "margin = smallest value over the year of  SDF - 20 km  along the exact\n"
            "straight chords sailed (bilinear SDF); 0 = touching the limit, never beyond", ha="center",
            fontsize=6.8, color=MUTE, transform=ax.transAxes)
    _panel(ax, "(d)", "Exact minimum margins, 1-year runs")
    mov = [v for k, v in stats.items() if k.startswith("mm_") and k != "mm_B0" and v == v]
    stats["mm_max_routers"] = float(max(mov or [0]))
    stats["mm_min"] = float(min(mov or [0]))
    stats["relax_ok"] = float(cor.sdf_at(px, py) / 1e3)
    stats["n_runs"] = len(rows)
    return fig, stats


# =================================================================== figure 0: architecture
def _stencil_k() -> int:
    try:
        from horizon.dp.stencil import macro_arcs

        return int(macro_arcs(40e3, 10800.0, max_span=2)[0].size)
    except Exception:  # noqa: BLE001
        return 49


def fig_architecture(ctx: Ctx):
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    K = _stencil_k()
    fig = plt.figure(figsize=(9.6, 8.6))
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.grid(False)

    def box(x, y, w, h, title, lines, fc, ec, fs=6.9, tfs=7.8):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.9", fc=fc, ec=ec, lw=1.1))
        ax.text(x + 0.9, y + h - 1.1, title, fontsize=tfs, fontweight="bold", color=INK, va="top")
        ax.text(x + 0.9, y + h - 3.7, "\n".join(lines), fontsize=fs, color=INK, va="top", linespacing=1.28)

    def layer(y, h, name, ec, fc):
        ax.add_patch(FancyBboxPatch((1, y), 77, h, boxstyle="round,pad=0.3,rounding_size=1.2", fc=fc, ec=ec, lw=1.8, alpha=0.55))
        ax.text(2, y + h - 0.8, name, fontsize=8.6, fontweight="bold", color=ec, va="top")

    def arrow(x0, y0, x1, y1, label="", dx=0.6, dy=0.0, color=MUTE, ha="left"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=11, color=color, lw=1.3))
        if label:
            ax.text((x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy, label, fontsize=6.5, color=color, va="center", ha=ha,
                    bbox={"fc": "white", "ec": "none", "pad": 0.4, "alpha": 0.85})

    # ---- inputs
    ax.text(1, 98.6, "INPUTS", fontsize=8.6, fontweight="bold", color=MUTE)
    box(1, 85, 25, 12.2, "Weather", ["backtest: ERA5 truth, 2015, 1 h", "NWP ensemble: control + 20 members",
                                     "cycles every 6 h, latency 4-6 h", "lead 0-15 d; wind u, v [m/s]"], "#eef3fd", BLUE)
    box(27, 85, 25, 12.2, "Ship", ["BETA polar P(TWS, TWA, U) [kW]", "-> power envelope E(v_par, v_perp)",
                                   "-> hold power P_hold(TWS) [kW]", "rated 3 MW; 8 m/s max speed"], "#eef3fd", BLUE)
    box(53, 85, 25, 12.2, "Coast", ["signed distance SDF [km]", "limit 20 km from land", "Lorient corridor: 1 -> 20 km",
                                    "over 40 km from the port"], "#eef3fd", BLUE)
    # ---- exploration
    layer(52, 29, "1  STRATEGIC EXPLORATION  (what is the best route under uncertainty?)", BLUE, "#e3ecfb")
    box(3, 60.5, 22, 17.5, "Ensemble reduction", ["20 members -> EOF (principal", "components) -> PAM k-medoids", "-> k = 6 scenarios, weights",
                                                  "sum to 1 (real members)"], "white", BLUE)
    box(27.5, 60.5, 25, 17.5, "Stochastic DP", ["graph: 40 km grid x 3 h steps", f"K = {K} macro-arcs (hold + 16 of",
                                                "3 h + 32 of 6 h), speed 0.5-8 m/s", "horizon 10-15 d, backward", "induction, one DP per scenario"],
        "white", BLUE)
    box(54.5, 60.5, 22.5, 17.5, "Risk and trunk", ["mean + CVaR (worst 20 %)", "of the scenario values", "common 48 h trunk (no",
                                                   "anticipation), then one", "branch per scenario"], "white", BLUE)
    box(3, 53.5, 74, 5.4, "Terminal value at the end of the window  [MWh]", [], "white", BLUE, tfs=7.2)
    ax.text(37, 54.2, "climatological: P_clim(x) x 120 h   |   learned V_theta (LightGBM, 5 d)", fontsize=6.9, ha="center", va="bottom")
    arrow(25.5, 69, 27.2, 69)
    arrow(52.7, 69, 54.2, 69)
    # ---- refinement
    layer(30.5, 18.5, "2  TACTICAL REFINEMENT  (make the first 48 h flyable)", GREEN, "#e2f4ea")
    box(3, 32, 74, 12.2, "Continuous optimal control (CasADi + IPOPT, multiple shooting)",
        ["window 0-48 h, 96 stages of 30 min, warm start = DP path; objective = energy + V_DP(48 h) - small penalties",
         "constraints: ground speed <= 8 m/s, SDF >= 20 km checked exactly on the chords, velocity inside the envelope hull",
         "fallback: if the solver fails or does not improve, the DP plan is kept"], "white", GREEN)
    # ---- execution
    layer(14.5, 13.5, "3  EXECUTION  (act, observe, replan)", ORANGE, "#fcf0dc")
    box(3, 15.5, 35, 8.6, "MPC replanning every 6 h", ["execute only the first 6 h, then", "re-run layers 1-2 on the newest forecast"], "white", ORANGE)
    box(41, 15.5, 36, 8.6, "Simulator + guard", ["15 min step on the TRUE wind; power from the", "envelope; coast guard (never < 20 km)"], "white", ORANGE)
    arrow(38.4, 19.8, 40.7, 19.8)
    # ---- outputs
    layer(1, 11.5, "4  OUTPUTS", INK, "#eceef2")
    ax.text(3, 4.4, "energy [MWh]  |  capacity factor CF [%] = E / (3 MW x hours)  |  gap to the oracle [percentage points of CF]\n"
            "hold share [%]  |  minimum coast margin [km]  |  plan optimism [MWh]", fontsize=7.1, va="center", linespacing=1.5)
    # ---- flows
    arrow(13.5, 84.6, 13.5, 81.6, "", color=BLUE)
    ax.text(15.5, 83.0, "forecast winds, 3 h", fontsize=6.4, color=BLUE, va="center")
    arrow(39.5, 84.6, 39.5, 81.6, "", color=BLUE)
    ax.text(41.5, 83.0, "rewards [kW] per arc", fontsize=6.4, color=BLUE, va="center")
    arrow(58, 84.6, 58, 81.6, "", color=BLUE)
    ax.text(60.5, 83.0, "feasible nodes, SDF [km]", fontsize=6.4, color=BLUE, va="center")
    arrow(40, 52.0, 40, 49.3, "", color=GREEN)
    ax.text(42, 50.6, "coarse plan: a node every 3 h [km] + value field V [MWh]", fontsize=6.4, color=GREEN, va="center")
    arrow(40, 30.4, 40, 28.2, "", color=ORANGE)
    ax.text(42, 29.3, "48 h trajectory every 30 min [km]; first 6 h executed", fontsize=6.4, color=ORANGE, va="center")
    arrow(40, 14.4, 40, 12.7, "", color=INK)
    ax.text(42, 13.6, "track, power [kW], energy [kWh]", fontsize=6.4, color=INK, va="center")
    # feedback loop (new forecast, position)
    ax.add_patch(FancyArrowPatch((78.5, 19.5), (78.5, 91), connectionstyle="arc3,rad=-0.0", arrowstyle="-|>", mutation_scale=11,
                                 color=ORANGE, lw=1.3, ls="--"))
    ax.text(79.3, 56, "every 6 h:\nnew forecast,\nship position", fontsize=6.6, color=ORANGE, va="center")
    # ---- time-scale ruler
    ax.text(88, 98.6, "TIME SCALES", fontsize=8.0, fontweight="bold", color=MUTE, ha="center")
    ruler = [(91.2, "1 y mission\n(365 d)", MUTE), (66, "10-15 d horizon\nstep 3 h, 40 km", BLUE),
             (38, "0-48 h\nstep 30 min", GREEN), (21, "6 h replan\n15 min sim", ORANGE), (6.5, "metrics:\nmonthly, yearly", INK)]
    for y, t, c in ruler:
        ax.text(89.5, y, t, fontsize=6.9, color=c, ha="center", va="center", linespacing=1.3,
                bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": c, "lw": 0.8})
    ax.plot([89.5, 89.5], [8.5, 88.5], color=GRID, lw=1.5, zorder=0)
    stats = {"K": K, "n_one": 16, "n_two": 32, "members": 20, "k": 6, "dx": 40, "dt": 3, "replan": 6,
             "trunk": 48, "stage_min": 30, "stages": 96}
    return fig, stats


# ============================================================================== registry
FIGURES: dict[str, Callable] = {"architecture": fig_architecture, "polar": fig_polar, "forecast": fig_forecast, "safety": fig_safety, "envelope": fig_envelope, "dp": fig_dp, "ensemble": fig_ensemble, "terminal": fig_terminal, "refiner": fig_refiner, "mpc": fig_mpc, "results": fig_results}
FIGURE_IDS = tuple(FIGURES)


def render_figures(ctx: Ctx, only: Sequence[str] | None = None, progress=None):
    """Yield ``(id, matplotlib Figure, stats)`` for each figure that can be produced."""
    for fid, fn in FIGURES.items():
        if only is not None and fid not in only:
            continue
        try:
            with plt.rc_context(_rc()), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig, stats = fn(ctx)
        except (FileNotFoundError, KeyError, ValueError, RuntimeError, ImportError) as exc:
            if progress:
                progress(f"{fid}: skipped ({type(exc).__name__}: {exc})")
            continue
        if progress:
            progress(f"{fid}: done")
        yield fid, fig, stats


class _SafeStats(dict):
    """``format_map`` source: a missing statistic prints as nan instead of raising."""

    def __missing__(self, key):
        return float("nan")


def build_tech_figures(export_data: dict, polar=None, *, only: Sequence[str] | None = None,
                       polar_dir=None, era5_cache=None, runs_dir=None, value_dir=None,
                       cache_dir=None, results_json=None, preview_dir=None, progress=None):
    """Build the technical Guide figures.

    Returns a list of ``{id, title_fr, title_en, svg, caption_fr, caption_en, body_fr, body_en}``.
    """
    from horizon.viz.tech_figures_text import TEXTS

    ctx = Ctx(export_data, polar)
    for k, v in (("polar_dir", polar_dir), ("era5_cache", era5_cache), ("runs_dir", runs_dir),
                 ("value_dir", value_dir), ("cache_dir", cache_dir), ("results_json", results_json)):
        if v is not None:
            setattr(ctx, k, Path(v))
    out = []
    for fid, fig, stats in render_figures(ctx, only, progress):
        svg = _svg_string(fig)
        if preview_dir is not None:
            Path(preview_dir).mkdir(parents=True, exist_ok=True)
            fig.savefig(Path(preview_dir) / f"{fid}.png", dpi=130)
        plt.close(fig)
        t = TEXTS[fid]
        stats = _SafeStats(stats)
        out.append({"id": fid, "title_fr": t["title_fr"], "title_en": t["title_en"], "svg": svg,
                    "caption_fr": t["caption_fr"].format_map(stats),
                    "caption_en": t["caption_en"].format_map(stats),
                    "body_fr": t["body_fr"].format_map(stats), "body_en": t["body_en"].format_map(stats)})
    return out


def _dump_stats(data, only=None):  # pragma: no cover - dev helper
    ctx = Ctx(data)
    for fid, fig, stats in render_figures(ctx, only):
        plt.close(fig)
        print(fid, json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in stats.items()}))


def _main():  # pragma: no cover - CLI
    import argparse
    import gzip

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--export", default=str(_ROOT / "outputs/s4_inspector/year.json.gz"))
    ap.add_argument("--out", default=str(_ROOT / "outputs/tech_figures"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    data = json.load(gzip.open(a.export))
    figs = build_tech_figures(data, only=a.only, preview_dir=a.out, progress=print)
    for f in figs:
        print(f"{f['id']:10s} {len(f['svg']) / 1e3:7.1f} kB")
    if a.stats:
        _dump_stats(data, a.only)
    print("total", sum(len(f["svg"]) for f in figs) / 1e3, "kB")


if __name__ == "__main__":  # pragma: no cover
    _main()
