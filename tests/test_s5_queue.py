"""Sprint-5 campaign infrastructure: spec normalisation, queue idempotency, status."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
S5 = ROOT / "scripts" / "s5"

FAKE = '''
import json, sys, time
sys.path.insert(0, "%s")
import s5lib as L
spec = json.loads(sys.argv[2])
cid = L.case_id(spec)
if L.is_done(cid):
    sys.exit(0)
import os
if os.environ.get("S5_CLAIMED") != "1" and not L.claim(cid):
    sys.exit(75)
time.sleep(float(__import__("os").environ.get("FAKE_SLEEP", "0.5")))
L.atomic_json(L.result_path(cid), {"id": cid, "spec": L.normalise(spec), "cf_pct": 50.0,
    "wall_s": 1.0, "cpu_s": 1.0, "hold_share": 0.0,
    "manoeuvres": {"total": 0, "per_day": 0.0}})
pass  # the master releases the lock
''' % S5

CAMPAIGN = """
duration_days: 30
tiers: [A, B]
experiments:
  - {id: e1, tier: A, router: B1c_5d_REF, seeds: [1], windows: ens4}
  - {id: e2, tier: B, router: B1c_5d_REF, windows: ens4, vary: {env.error_scale: [0.5]}}
"""


@pytest.fixture()
def env(tmp_path):
    (tmp_path / "fake.py").write_text(FAKE)
    (tmp_path / "campaign.yaml").write_text(CAMPAIGN)
    e = dict(os.environ, S5_OUT=str(tmp_path / "out"), S5_RUN_CASE=str(tmp_path / "fake.py"),
             PYTHONPATH=str(S5))
    return tmp_path, e


def _lib(tmp, monkeypatch):
    monkeypatch.setenv("S5_OUT", str(tmp / "out"))
    sys.path.insert(0, str(S5))
    sys.modules.pop("s5lib", None)
    import s5lib
    return s5lib


def test_normalisation_and_ids(tmp_path, monkeypatch):
    L = _lib(tmp_path, monkeypatch)
    a = L.case_id({"router": {"name": "B1c_5d_REF", "horizon_days": 5}, "env": {
        "error_scale": 1.0, "manoeuvre": True}, "start": "2015-01-01"})
    b = L.case_id({"router": {"name": "B1c_5d_REF"}, "env": {}, "start": "2015-01-01"})
    assert a == b  # default-valued overrides are dropped: x1 shares the base result
    c = L.case_id({"router": {"name": "B1c_5d_REF"}, "env": {"error_scale": 0.5},
                   "start": "2015-01-01"})
    assert c != b and "error_scale=0.5" in c
    # forecast knobs and the seed do not distinguish hindsight / fixed routers
    o1 = L.case_id({"router": {"name": "Oracle_REF_H"}, "env": {"error_scale": 2}, "seed": 7,
                    "start": "2015-01-01"})
    o2 = L.case_id({"router": {"name": "Oracle_REF_H"}, "env": {}, "start": "2015-01-01"})
    assert o1 == o2
    with pytest.raises(ValueError):
        L.normalise({"router": {"name": "B1c_5d_REF", "bogus": 1}, "start": "2015-01-01"})
    camp = L.load_campaign(S5 / "campaign.yaml")
    cases = L.expand(camp)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)) and cases[0]["tier"] == "A"
    tiers = [c["tier"] for c in cases]
    assert tiers == sorted(tiers)  # priority order


def test_queue_idempotent_kill_restart_and_status(env):
    tmp, e = env
    e = dict(e, FAKE_SLEEP="1.5")
    cmd = [sys.executable, str(S5 / "campaign_queue.py"), "--campaign", str(tmp / "campaign.yaml"),
           "--workers", "2"]
    p = subprocess.Popen(cmd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(9)
    # a second master must refuse to start
    r2 = subprocess.run(cmd + ["--once"], env=e, capture_output=True, text=True, timeout=30)
    assert "another queue master" in r2.stdout
    p.send_signal(signal.SIGKILL)  # hard kill of the master (children may survive: VM restart)
    p.wait()
    runs = tmp / "out" / "runs"
    n1 = len(list(runs.glob("*.json")))
    assert 0 < n1 < 8
    time.sleep(3)  # orphan children finish by themselves
    e = dict(e, FAKE_SLEEP="0.2")
    r3 = subprocess.run(cmd + ["--once"], env=e, capture_output=True, text=True, timeout=120)
    assert r3.returncode == 0
    files = sorted(runs.glob("*.json"))
    assert len(files) == 8  # 4 windows x (base + error_scale 0.5): all done, none duplicated
    r4 = subprocess.run(cmd + ["--once"], env=e, capture_output=True, text=True, timeout=60)
    assert "start [" not in r4.stdout  # idempotent: nothing left to launch
    st = subprocess.run([sys.executable, str(S5 / "status.py"), "--campaign",
                         str(tmp / "campaign.yaml")], env=e, capture_output=True, text=True,
                        timeout=60)
    assert st.returncode == 0
    assert "8/8" in st.stdout and "NOT RUNNING" in st.stdout and "e2" in st.stdout
    assert "No errors" in st.stdout
    assert not list((tmp / "out" / "locks").glob("*.lock"))


def test_stale_lock_is_reclaimed(tmp_path, monkeypatch):
    L = _lib(tmp_path, monkeypatch)
    assert L.claim("x", pid=os.getpid())
    assert not L.claim("x", pid=os.getpid() + 0)  # live holder
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    L.set_lock_pid("x", dead.pid)
    assert L.claim("x")  # holder dead -> stale lock broken
    L.release("x")
    json.dumps({})
