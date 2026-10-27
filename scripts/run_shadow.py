"""Shadow testing runner. NO ORDERS ARE PLACED.

Live (market hours, IST; start before 09:15, exits after 15:35):
  DHAN_ACCESS_TOKEN=... DHAN_CLIENT_ID=... [JEV_API_KEY=...] python scripts/run_shadow.py --live
  Kill switch: create the file data/shadow/STOP (the loop exits within a few seconds).
Replay (offline check of the whole pipeline on stored data, simulated clock):
  python scripts/run_shadow.py --replay --from 2024-06-03 --to 2024-06-28
"""
import argparse
import os
import sys
import time
import traceback
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data import store
from lightning.data.dhan import DhanClient
from lightning.live.db import AuditDB
from lightning.live.engine import ShadowEngine
from lightning.live.jev import JevGate
from lightning.live.sources import DhanLiveSource, ReplaySource
from lightning.signals import BAR

IST = "Asia/Kolkata"
STOP = ROOT / "data" / "shadow" / "STOP"


def replay(args, p, cfg):
    d = ROOT / "data" / "NIFTY"
    raw = store.load_intraday(d / "spot_15m.csv")
    cal = ExpiryCalendar(store.calendar_days(raw), p.expiry_schedule)
    spot, _ = store.clean_intraday(raw)
    opt = store.load_options(d)
    spot = store.attach_option_volume(spot, opt)
    src = ReplaySource(spot, store.load_daily(d / "spot_daily.csv"), opt, cal.expiries, half_spread=args.half_spread)
    db_path = ROOT / "data" / "shadow" / f"replay_{args.start}_{args.end}.sqlite"
    db_path.unlink(missing_ok=True)
    db = AuditDB(db_path)
    lo, hi = pd.Timestamp(args.start, tz=IST), pd.Timestamp(args.end, tz=IST) + pd.Timedelta(days=1)
    ends = [t + BAR for t in spot.index if lo <= t < hi]
    src.clock = ends[0] - BAR + pd.Timedelta(seconds=10)  # engine warm-up sees history before the first bar
    eng = ShadowEngine(src, db, p, cfg, JevGate(cfg["jev"]), mode="REPLAY", volume_is_proxy=True)
    for e in ends:
        src.clock = e + pd.Timedelta(seconds=10)
        eng.step()
    print(f"replay done: {db_path}")
    for r in db.query("SELECT status, COUNT(*) n FROM candidates GROUP BY status"):
        print(" candidates", r)
    for r in db.query("SELECT strategy, COUNT(*) n, ROUND(SUM(net)) net, ROUND(AVG(net_r),3) avg_r FROM paper_trades "
                      "WHERE status='CLOSED' GROUP BY strategy"):
        print(" paper", r)


def next_boundary(now: pd.Timestamp) -> pd.Timestamp:
    start = now.normalize() + pd.Timedelta(hours=9, minutes=15)
    k = max(0, int((now - start) / BAR) + 1)
    return start + k * BAR


def live(p, cfg):
    token, client_id = os.environ.get("DHAN_ACCESS_TOKEN"), os.environ.get("DHAN_CLIENT_ID")
    if not token or not client_id:
        sys.exit("set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID")
    src = DhanLiveSource(DhanClient(token, client_id=client_id), cfg["underlying"]["security_id"], cfg["underlying"]["segment"])
    db = AuditDB(ROOT / "data" / "shadow" / "live.sqlite")
    eng = ShadowEngine(src, db, p, cfg, JevGate(cfg["jev"]), mode="SHADOW")
    close = pd.Timestamp.now(tz=IST).normalize() + pd.Timedelta(hours=15, minutes=35)
    print("shadow live started; kill switch:", STOP)
    while pd.Timestamp.now(tz=IST) < close and not STOP.exists():
        nb = next_boundary(pd.Timestamp.now(tz=IST)) + pd.Timedelta(seconds=15)
        while pd.Timestamp.now(tz=IST) < nb and not STOP.exists():
            try:
                eng.poll()
            except Exception as e:  # noqa: BLE001 - keep running; no entries happen without fresh data
                db.insert("heartbeat", {"ts": pd.Timestamp.now(tz=IST), "status": "POLL_ERROR", "detail": str(e)[:300]})
            time.sleep(min(cfg["poll_seconds"], max(1.0, (nb - pd.Timestamp.now(tz=IST)).total_seconds())))
        if STOP.exists():
            break
        try:
            eng.step()
        except Exception as e:  # noqa: BLE001
            db.insert("heartbeat", {"ts": pd.Timestamp.now(tz=IST), "status": "STEP_ERROR",
                                    "detail": (str(e) + " | " + traceback.format_exc()[-500:])[:900]})
    print("shadow live stopped", "(kill switch)" if STOP.exists() else "(after close)")


def main():
    a = argparse.ArgumentParser()
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true"); g.add_argument("--replay", action="store_true")
    a.add_argument("--from", dest="start"); a.add_argument("--to", dest="end")
    a.add_argument("--half-spread", type=float, default=0.005)
    args = a.parse_args()
    p, cfg = load_params(), yaml.safe_load((ROOT / "config" / "shadow.yaml").read_text())
    if args.replay:
        if not (args.start and args.end):
            sys.exit("--replay needs --from and --to")
        replay(args, p, cfg)
    else:
        live(p, cfg)


if __name__ == "__main__":
    main()
