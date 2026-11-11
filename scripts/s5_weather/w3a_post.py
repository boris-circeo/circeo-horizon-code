"""Fix-up: fill symmetric column and recompute e-folding lengths from saved spatial ACF maps."""
import sys, json; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from scipy.ndimage import map_coordinates
z = np.load(OUT/"a3_spatial_acf.npz"); R = int(z["R"]); dx = 40.0
res = json.load(open(OUT/"a3a.json")); out = {}
def fix(C):
    C = C.copy()
    for dj in range(1, R+1): C[R-dj, 0] = C[R+dj, 0]
    C[R, 0] = 1.0
    return C
def ef(C, th, lev=1/np.e):
    r = np.arange(0, R, 0.05); t = np.radians(th)
    di = r*np.cos(t); dj = r*np.sin(t); s = np.where(di < 0, -1, 1)
    v = map_coordinates(C, [dj*s+R, di*s], order=1)
    k = np.nonzero(v < lev)[0]
    return float(r[k[0]]*dx) if k.size else float("nan")
for name, key in (("vector","Cv"),("u","Cu"),("v","Cvv"),("tws_anom","Cs")):
    C = fix(z[key]); az = {str(t): ef(C, t) for t in range(0, 180, 15)}
    h = {str(t): ef(C, t, 0.5) for t in range(0, 180, 15)}
    a = np.array(list(az.values()))
    out[name] = {"efold_km_by_azimuth_from_east": az, "halfcorr_km_by_azimuth": h,
                 "EW_km": az["0"], "NS_km": az["90"], "min_km": float(np.nanmin(a)), "max_km": float(np.nanmax(a)),
                 "mean_km": float(np.nanmean(a)), "n_nan": int(np.isnan(a).sum())}
    out[name]["EW_half_km"] = h["0"]; out[name]["NS_half_km"] = h["90"]
    print(name, {k: (round(v,0) if isinstance(v,float) else v) for k,v in out[name].items() if not isinstance(v,dict)})
    print("  ", az)
res["spatial"] = out
json.dump(res, open(OUT/"a3a.json","w"), indent=1)
