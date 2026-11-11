"""A3b: feature translation velocity by block cross-correlation of consecutive TWS-anomaly fields."""
import sys, json, time; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
g, arc, sea, land, env, tws, ph = setup()
uv = np.load(OUT/"uv_2015.npy", mmap_mode="r")
n = uv.shape[0]; ny, nx = g.shape; mon = month_of_hour(arc)
DT = int(sys.argv[1]) if len(sys.argv) > 1 else 6      # lag between fields [h]
S = 12; TS = 10; BS = 2                                    # max shift [cells], tile [cells], block = BS tiles
ts = np.arange(DT, n - DT, 3)                              # t0; pair (t0, t0+DT); velocity assigned to mid time
nbj, nbi = (ny // TS) - BS + 1, (nx // TS) - BS + 1
M = sea.astype(np.float32)
# monthly cell mean of TWS (kn)
mu = np.zeros((12, ny, nx), np.float32)
for m in range(12):
    lo, hi = int(arc._offset[m]), int(arc._offset[m+1])
    a = np.asarray(uv[lo:hi:3]); mu[m] = (np.hypot(a[...,0], a[...,1]).mean(0))/KN
def field(t):
    a = np.asarray(uv[t]); return (np.hypot(a[...,0], a[...,1])/KN - mu[mon[t]-1]) * M
def tilesum(X):  # X (..., ny, nx) -> block sums (..., nbj, nbi) with tile TS and block BS tiles
    Y = X[..., :(ny//TS)*TS, :(nx//TS)*TS]
    sh = Y.shape[:-2] + (ny//TS, TS, nx//TS, TS)
    T = Y.reshape(sh).sum((-3, -1))
    return sum(T[..., a:a+nbj, b:b+nbi] for a in range(BS) for b in range(BS) if True) if False else \
        sum(T[..., a:a+nbj, b:b+nbi] for a in range(BS) for b in range(BS))
npair = ts.size
best = np.full((npair, nbj, nbi, 2), np.nan, np.float32); peak = np.full((npair, nbj, nbi), np.nan, np.float32)
c0 = np.full((npair, nbj, nbi), np.nan, np.float32); bmean = np.zeros((npair, nbj, nbi), np.float32)
bsea = tilesum(M[None])[0]/ (BS*TS)**2
shifts = [(dj, di) for dj in range(-S, S+1) for di in range(-S, S+1)]
t0c = time.time()
CH = 60
for c0i in range(0, npair, CH):
    idx = np.arange(c0i, min(npair, c0i+CH)); tt = ts[idx]
    A = np.stack([field(t) for t in tt]); B = np.stack([field(t+DT) for t in tt])
    Bp = np.pad(B, ((0,0),(S,S),(S,S)))
    B2 = Bp*Bp
    Aa2 = tilesum(A*A)
    # block-mean raw TWS at t (kn) for weighting
    Wr = np.stack([np.hypot(*np.moveaxis(np.asarray(uv[t]),-1,0))/KN for t in tt])*M
    bmean[idx] = tilesum(Wr)/np.maximum(tilesum(np.broadcast_to(M, Wr.shape)), 1)
    corr = np.zeros((len(idx), len(shifts), nbj, nbi), np.float32)
    for k, (dj, di) in enumerate(shifts):
        Bs = Bp[:, S+dj:S+dj+ny, S+di:S+di+nx]
        num = tilesum(A*Bs); den = tilesum(B2[:, S+dj:S+dj+ny, S+di:S+di+nx])
        corr[:, k] = num/np.sqrt(np.maximum(Aa2*den, 1e-6))
    # restrict to valid blocks
    K = corr.argmax(1); pk = corr.max(1)
    kz = shifts.index((0,0)); c0[idx] = corr[:, kz]
    for q, (dj, di) in enumerate(shifts): pass
    sj = np.array([s[0] for s in shifts]); si = np.array([s[1] for s in shifts])
    # subpixel (parabolic) in 2D separably
    cg = corr.reshape(len(idx), 2*S+1, 2*S+1, nbj, nbi)
    kj = sj[K] + S; ki = si[K] + S
    I, Jb, Ib = np.meshgrid(np.arange(len(idx)), np.arange(nbj), np.arange(nbi), indexing="ij")
    interior = (kj > 0) & (kj < 2*S) & (ki > 0) & (ki < 2*S)
    kj_ = np.clip(kj, 1, 2*S-1); ki_ = np.clip(ki, 1, 2*S-1)
    cc = cg[I, kj_, ki_, Jb, Ib]
    def par(m, p, c):
        d = m - 2*c + p
        return np.where(np.abs(d) > 1e-9, 0.5*(m-p)/d, 0.0)
    fj = par(cg[I, kj_-1, ki_, Jb, Ib], cg[I, kj_+1, ki_, Jb, Ib], cc)
    fi = par(cg[I, kj_, ki_-1, Jb, Ib], cg[I, kj_, ki_+1, Jb, Ib], cc)
    sjv = np.where(interior, sj[K] + np.clip(fj, -1, 1), np.nan); siv = np.where(interior, si[K] + np.clip(fi, -1, 1), np.nan)
    best[idx, :, :, 0] = siv; best[idx, :, :, 1] = sjv; peak[idx] = pk
    if c0i == 0: print("chunk time", time.time()-t0c, flush=True)
np.savez(OUT/f"a3_adv_dt{DT}.npz", best=best, peak=peak, c0=c0, bmean=bmean, bsea=bsea, ts=ts, DT=DT, TS=TS, BS=BS)
print("done", time.time()-t0c)
