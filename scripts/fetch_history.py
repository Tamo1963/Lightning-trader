"""Fetch everything the Nifty baseline needs from DhanHQ into data/<NAME>/ (git-ignored). Resumable.

  DHAN_ACCESS_TOKEN must be set in the environment (never pass it on the command line or print it).
  python scripts/fetch_history.py --start 2021-11-01 --end 2026-10-27

Writes:
  spot_daily.csv            daily OHLC since --daily-start (monthly RSI needs long history)
  spot_15m.csv              15-min index OHLC (volume is 0 for an index)
  options/slot{S}_{CE|PE}_{k}.csv   rolling expired options, ATM-k..ATM+k, near (S=0) and next (S=1) weekly expiry
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.config import load_params
from lightning.data.dhan import DhanClient
from lightning.data.store import offset_label, save_csv


def resume_start(path: Path, start: str) -> str:
    """Re-fetch from the start of the last stored day (that day may have been partial)."""
    if not path.exists():
        return start
    ts = pd.read_csv(path, usecols=["ts"])["ts"]
    if ts.empty:
        return start
    last = pd.Timestamp(ts.iloc[-1])
    last = last.tz_convert("Asia/Kolkata") if last.tzinfo else last
    return max(pd.Timestamp(start), last.tz_localize(None).normalize()).strftime("%Y-%m-%d")


def append(path: Path, new: pd.DataFrame):
    if path.exists():
        old = pd.read_csv(path, parse_dates=["ts"], index_col="ts")
        old.index = pd.DatetimeIndex(old.index).tz_convert("Asia/Kolkata")
        new = pd.concat([old, new])
        new = new[~new.index.duplicated(keep="last")].sort_index()
    save_csv(new, path)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--name", default="NIFTY")
    a.add_argument("--start", required=True); a.add_argument("--end", required=True)
    a.add_argument("--daily-start", default="2015-01-01")
    a.add_argument("--skip-options", action="store_true")
    args = a.parse_args()
    token = os.environ.get("DHAN_ACCESS_TOKEN")
    if not token:
        sys.exit("set DHAN_ACCESS_TOKEN in the environment")
    p = load_params()
    uid, k, slots = p.underlying_security_id, p.data["strike_offsets"], p.data["rolling_slots"]
    out = Path("data") / args.name
    c = DhanClient(token)

    daily = c.daily(str(uid), "IDX_I", "INDEX", args.daily_start, args.end)
    save_csv(daily, out / "spot_daily.csv"); print(f"spot_daily: {len(daily)} rows")

    p15 = out / "spot_15m.csv"
    s15 = c.intraday(str(uid), "IDX_I", "INDEX", resume_start(p15, args.start), args.end, 15)
    append(p15, s15); print(f"spot_15m: +{len(s15)} rows")

    if args.skip_options:
        return
    for slot, code in slots.items():
        for side, tag in (("CALL", "CE"), ("PUT", "PE")):
            for off in range(-k, k + 1):
                path = out / "options" / f"slot{slot}_{tag}_{off}.csv"
                df = c.rolling_options(uid, resume_start(path, args.start), args.end, side, offset_label(off), code)
                append(path, df)
                print(f"options slot{slot} {tag} {offset_label(off)}: +{len(df)} rows")
    for w in c.skipped:
        print("skipped (DH-907 no data):", w)


if __name__ == "__main__":
    main()
