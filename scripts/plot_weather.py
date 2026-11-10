"""Plot synthetic truth snapshots and forecast skill to outputs/ (requires matplotlib)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from horizon.geo.grid import Grid  # noqa: E402
from horizon.weather.synthetic import SyntheticWeather, skill_vs_truth  # noqa: E402

DAY = 86400.0
EPOCH = np.datetime64("2024-01-01T00:00:00")
OUT = Path(__file__).resolve().parents[1] / "outputs"


def snapshots(wx: SyntheticWeather) -> Path:
    g = wx.grid
    f = wx.truth(dt_s=3600.0)
    ext = [(g.x0 - g.dx / 2) / 1e3, (g.x0 + (g.nx - 0.5) * g.dx) / 1e3,
           (g.y0 - g.dx / 2) / 1e3, (g.y0 + (g.ny - 0.5) * g.dx) / 1e3]
    fig, axs = plt.subplots(2, 2, figsize=(11, 9), sharex=True, sharey=True)
    for ax, day in zip(axs.ravel(), (5, 10, 15, 20), strict=True):
        k = day * 24
        u, v = f.uv[k, ..., 0], f.uv[k, ..., 1]
        im = ax.imshow(np.hypot(u, v), origin="lower", extent=ext, vmin=0, vmax=30, cmap="viridis")
        s = 4
        ax.quiver(g.x[::s] / 1e3, g.y[::s] / 1e3, u[::s, ::s], v[::s, ::s], color="w", scale=500,
                  width=0.002)
        ax.set_title(f"truth, day {day} (true east/north components, drawn in grid frame)",
                     fontsize=8)
    fig.colorbar(im, ax=axs, label="wind speed [m/s]", shrink=0.8)
    p = OUT / "weather_truth.png"
    fig.savefig(p, dpi=110, bbox_inches="tight")
    return p


def skill(grid: Grid, seeds=(0, 1, 2), issues_d=(3, 8, 13, 18), n_members=8):
    rows = []
    for seed in seeds:
        wx = SyntheticWeather(grid, EPOCH, 30 * DAY, seed=seed)
        tr = wx.truth(start_s=0.0, end_s=33 * DAY)
        for d in issues_d:
            k = skill_vs_truth(wx.forecast(d * DAY, 15 * DAY, n_members), tr)
            rows.append([k["rmse_control"], k["rmse_mean"], k["spread"]])
    r = np.sqrt(np.mean(np.square(rows), axis=0))
    lead_d = np.arange(r.shape[1]) * 3.0 / 24.0
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(lead_d, r[0], label="RMSE control")
    ax.plot(lead_d, r[1], label="RMSE ensemble mean")
    ax.plot(lead_d, r[2], "--", label="ensemble spread")
    ax.set(xlabel="lead [days]", ylabel="vector wind [m/s]", title="Synthetic forecast skill")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.savefig(OUT / "weather_skill.png", dpi=120, bbox_inches="tight")
    return lead_d, r


def main() -> None:
    OUT.mkdir(exist_ok=True)
    grid = Grid.from_bbox(-45.0, 5.0, 35.0, 65.0, 40_000.0)
    print(snapshots(SyntheticWeather(grid, EPOCH, 30 * DAY, seed=1)))
    lead_d, r = skill(grid)
    print("lead_d  rmse_ctrl  rmse_mean  spread")
    for d in (0, 1, 3, 5, 7, 10, 15):
        i = int(np.argmin(abs(lead_d - d)))
        print(f"{d:5d}  {r[0, i]:9.2f}  {r[1, i]:9.2f}  {r[2, i]:6.2f}")


if __name__ == "__main__":
    main()
