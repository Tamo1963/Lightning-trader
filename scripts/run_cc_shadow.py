"""Covered-call shadow mode. NO ORDERS ARE PLACED.

Live (run once a day after 15:20 IST, e.g. via Task Scheduler / cron):
  DHAN_ACCESS_TOKEN=... DHAN_CLIENT_ID=... python scripts/run_cc_shadow.py --live
Replay (offline check on NSE bhavcopy data, reconciles with the backtest):
  python scripts/run_cc_shadow.py --replay --from 2025-09-01 --to 2026-10-27
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.config import load_params
from lightning.data.dhan import DhanClient
from lightning.live.covered_call import CoveredCallEngine, DhanCCSource, ReplayCCSource
from lightning.live.db import AuditDB
from lightning.overlays import run_symbol


def load_cfg():
    cfg = yaml.safe_load((ROOT / "config" / "shadow_cc.yaml").read_text())
    stocks = yaml.safe_load((ROOT / "config" / "stocks.yaml").read_text())["stocks"]
    return cfg, stocks


def replay(args):
    cfg, stocks = load_cfg()
    p = load_params()
    files = sorted(f for f in (ROOT / "data" / "nse" / "multi").glob("*.csv.gz") if args.start.replace("-", "") <= f.name[:8] <= args.end.replace("-", ""))
    cols = ["symbol", "kind", "date", "expiry", "strike", "opt", "close", "volume"]
    df = pd.concat([pd.read_csv(f, usecols=cols) for f in files], ignore_index=True)
    df = df[df["symbol"].isin(cfg["symbols"])]
    df["date"], df["expiry"] = pd.to_datetime(df["date"]).dt.date, pd.to_datetime(df["expiry"]).dt.date
    db_path = ROOT / "data" / "shadow" / f"cc_replay_{args.start}_{args.end}.sqlite"
    db_path.unlink(missing_ok=True)
    db = AuditDB(db_path)
    src = ReplayCCSource(df)
    eng = CoveredCallEngine(src, db, dict(cfg, min_days_to_open=10 ** 6), {s: stocks[s]["lot"] for s in cfg["symbols"]}, p.costs)
    for d in src.days:  # min_days_to_open huge: start only at a roll, exactly like the backtest
        src.d = d
        eng.step()
    cyc = pd.DataFrame(db.query("SELECT symbol, expiry, d_in, d_out, k, ret_b0, ret_c5 FROM cc_cycles WHERE status='CLOSED'"))
    print(f"replay DB: {db_path}")
    for sym in cfg["symbols"]:
        bt = run_symbol(df[df["symbol"] == sym], stocks[sym]["lot"], p.costs)
        bt["expiry"] = bt["expiry"].astype(str)
        m = cyc[cyc["symbol"] == sym].merge(bt[["expiry", "B0", "C5", "C5_k"]], on="expiry", how="left")
        print(f"\n{sym}: {len(m)} cycles | shadow C5 sum {m['ret_c5'].sum():+.4f} vs backtest {m['C5'].sum():+.4f} | "
              f"B0 {m['ret_b0'].sum():+.4f} vs {m['B0'].sum():+.4f} | same strikes {int((m['k'] == m['C5_k']).sum())}/{len(m)}")
        print(m.round(4).to_string(index=False))


def live():
    cfg, stocks = load_cfg()
    token, cid = os.environ.get("DHAN_ACCESS_TOKEN"), os.environ.get("DHAN_CLIENT_ID")
    if not token or not cid:
        sys.exit("set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID")
    now = pd.Timestamp.now(tz="Asia/Kolkata")
    if now.strftime("%H:%M") < cfg["run_after"] or now.weekday() >= 5:
        sys.exit(f"run after {cfg['run_after']} IST on a trading day (now {now:%a %H:%M})")
    src = DhanCCSource(DhanClient(token, client_id=cid), ROOT / cfg["scrip_master"],
                       {s: stocks[s]["security_id"] for s in cfg["symbols"]}, cfg["option_chain_segment"], cfg.get("holidays", []))
    db = AuditDB(ROOT / "data" / "shadow" / "covered_call.sqlite")
    CoveredCallEngine(src, db, cfg, {s: stocks[s]["lot"] for s in cfg["symbols"]}, load_params().costs).step()
    for r in db.query("SELECT ts, symbol, event, detail FROM cc_log ORDER BY ts DESC LIMIT 10"):
        print(r)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true"); g.add_argument("--replay", action="store_true")
    a.add_argument("--from", dest="start"); a.add_argument("--to", dest="end")
    args = a.parse_args()
    replay(args) if args.replay else live()
