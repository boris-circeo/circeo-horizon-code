"""Plot the basin SDF map to outputs/coast_sdf.png (requires matplotlib)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from horizon.geo.coast import build_basin_coast  # noqa: E402


def main() -> None:
    m = build_basin_coast()
    g = m.grid
    ext = [(g.x0 - g.dx / 2) / 1e3, (g.x0 + (g.nx - 0.5) * g.dx) / 1e3,
           (g.y0 - g.dx / 2) / 1e3, (g.y0 + (g.ny - 0.5) * g.dx) / 1e3]
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(m.sdf / 1e3, origin="lower", extent=ext, cmap="RdBu", vmin=-500, vmax=500)
    ax.contour(g.x / 1e3, g.y / 1e3, m.sdf, levels=[0.0], colors="k", linewidths=0.4)
    fig.colorbar(im, label="SDF [km] (sea > 0, land < 0)")
    ax.set(xlabel="x [km] (LAEA)", ylabel="y [km]", title="Signed distance to coast, 10 km grid")
    out = Path(__file__).resolve().parents[1] / "outputs"
    out.mkdir(exist_ok=True)
    fig.savefig(out / "coast_sdf.png", dpi=130, bbox_inches="tight")
    print(out / "coast_sdf.png")


if __name__ == "__main__":
    main()
