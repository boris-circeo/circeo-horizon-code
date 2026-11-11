"""A4c: oracle DP confined to a disc of radius Rmax around the S4 start (value of local vs regional mobility)."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from scipy.ndimage import maximum_filter
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r"); n = uv.shape[0]; ny, nx = g.shape
STEP = 3; nt = n//STEP; okp = np.isfinite(ph)
P3 = np.empty((nt, ny, nx), np.float32)
for k in range(0, nt, 100):
    k1 = min(nt, k+100); a = np.asarray(uv[k*STEP:k1*STEP]); w = np.hypot(a[...,0], a[...,1])/KN
    P3[k:k1] = (np.interp(w, tws/KN, np.where(okp, ph, 0.0))/3000).reshape(k1-k, STEP, ny, nx).mean(1)
x0, y0 = g.to_xy(-21.6, 56.49); j0, i0 = (int(a) for a in g.index_of(x0, y0))
jj, ii = np.mgrid[0:ny, 0:nx]; dist = np.hypot(jj-j0, ii-i0)*40
NEG = np.float32(-1e9); res = {}
for Rmax in (0, 80, 160, 320, 640, 1280, 99999):
    allowed = sea & (dist <= Rmax)
    for v in (4, 8, 16):
        r = v*STEP*3600/40e3; R = int(np.ceil(r)); yy, xx = np.mgrid[-R:R+1, -R:R+1]; fp = (yy**2+xx**2) <= r*r+1e-9
        V = np.zeros((ny, nx), np.float32)
        for t in range(nt-1, -1, -1):
            mf = maximum_filter(np.where(allowed, V, NEG), footprint=fp, mode="constant", cval=NEG)
            V = np.where(allowed, P3[t] + mf, NEG)
        res[f"R{Rmax}_v{v}"] = float(V[j0, i0]/nt)
    print(Rmax, {k: round(x, 3) for k, x in res.items() if k.startswith(f"R{Rmax}_")}, flush=True)
json.dump(res, open(OUT/"a4c.json", "w"), indent=1)
