"""East/north <-> grid-frame vector conversion using the local projection Jacobian."""

from __future__ import annotations

import numpy as np

from horizon.geo.grid import Grid

__all__ = ["en_to_grid", "grid_to_en"]


def en_to_grid(grid: Grid, ve, vn, lon, lat):
    """Convert true east/north vector components to the grid (x, y) frame.

    ``(gx, gy) = ve * e_east + vn * e_north`` with ``Grid.local_basis`` (Jacobian columns). This is
    NOT a pure rotation: LAEA is non-conformal, so lengths change. Grid lengths differ from ground
    lengths by the local scale factor (grid metres per ground metre, ~1 near the projection centre).

    Parameters
    ----------
    ve, vn : float or ndarray  east / north components (any consistent unit, e.g. m or m/s).
    lon, lat : float or ndarray  [deg] position.

    Returns
    -------
    gx, gy : ndarray  same unit as input, grid frame.
    """
    e, n = grid.local_basis(lon, lat)
    ve = np.asarray(ve, dtype=float)
    vn = np.asarray(vn, dtype=float)
    return ve * e[..., 0] + vn * n[..., 0], ve * e[..., 1] + vn * n[..., 1]


def grid_to_en(grid: Grid, gx, gy, lon, lat):
    """Inverse of :func:`en_to_grid`: grid-frame ``(gx, gy)`` -> true ``(east, north)``.

    Solves the 2x2 Jacobian system; output lengths are ground lengths (see :func:`en_to_grid`).
    """
    e, n = grid.local_basis(lon, lat)
    gx = np.asarray(gx, dtype=float)
    gy = np.asarray(gy, dtype=float)
    det = e[..., 0] * n[..., 1] - e[..., 1] * n[..., 0]
    return (gx * n[..., 1] - gy * n[..., 0]) / det, (e[..., 0] * gy - e[..., 1] * gx) / det
