"""H4: plan optimism = predicted value at t0 - realised energy over the same window (S2 pickles)."""
import pickle

import numpy as np

R = "/home/claude/horizon/outputs/s2_runs/"
H = {"B1_5d": 5, "B1_15d": 15, "ENS_g0": 15, "ENS_g03": 15}
print("policy seed  windows  pred[MWh] real[MWh] optimism[MWh] (pred/real-1)   [windows t<=15d, window = min(H, T-t)]")
out = {}
for name, h in H.items():
    for seed in (101, 102, 103):
        d = pickle.load(open(f"{R}{name}_{seed}.pkl", "rb"))
        res = d["res"]; E = res.energy_kwh; t = res.t_s; dt = res.sim_dt_s
        T = t[-1]
        P, Rr = [], []
        for r in d["records"]:
            t0 = r["t_s"]
            if t0 > 15*86400: continue
            t1 = min(t0 + h*86400, T)
            if name.startswith("ENS"):
                p = r["diag"].get("v_t0_kwh", r["planned_value_kwh"])
            else:
                p = r["planned_value_kwh"]
            e = np.interp(t1, t, E) - np.interp(t0, t, E)
            P.append(p); Rr.append(e)
        P, Rr = np.array(P), np.array(Rr)
        out[(name, seed)] = (P, Rr)
        print(f"{name:8s} {seed} {len(P):4d}  {P.mean()/1e3:8.1f} {Rr.mean()/1e3:8.1f} {(P-Rr).mean()/1e3:8.1f}  ({P.mean()/Rr.mean()-1:+.1%})")
print()
for name in H:
    P = np.concatenate([out[(name, s)][0] for s in (101,102,103)]); Rr = np.concatenate([out[(name, s)][1] for s in (101,102,103)])
    print(f"{name:8s} pooled optimism {(P-Rr).mean()/1e3:7.1f} MWh = {(P/Rr).mean()-1:+.1%} ; per-window corr(pred,real) {np.corrcoef(P,Rr)[0,1]:.2f}")
