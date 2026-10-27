"""Download daily (since 2015) and 15-min (since --start) equity candles for config/stocks.yaml into data/stocks/<SYM>/.
DHAN_ACCESS_TOKEN from the environment. Resumable (skips files already present unless --refresh)."""
import argparse
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.data.dhan import DhanClient
from lightning.data.store import save_csv


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--start", default="2021-11-01"); a.add_argument("--end", default="2026-10-27")
    a.add_argument("--daily-start", default="2015-01-01"); a.add_argument("--refresh", action="store_true")
    args = a.parse_args()
    token = os.environ.get("DHAN_ACCESS_TOKEN") or sys.exit("set DHAN_ACCESS_TOKEN")
    cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "stocks.yaml").read_text())
    c = DhanClient(token)
    for sym, s in cfg["stocks"].items():
        out = Path("data/stocks") / sym
        sid = str(s["security_id"])
        for name, fn in (("daily.csv", lambda: c.daily(sid, "NSE_EQ", "EQUITY", args.daily_start, args.end)),
                         ("15m.csv", lambda: c.intraday(sid, "NSE_EQ", "EQUITY", args.start, args.end, 15))):
            path = out / name
            if path.exists() and not args.refresh:
                continue
            try:
                df = fn()
                save_csv(df, path)
                print(f"{sym} {name}: {len(df)} rows", flush=True)
            except Exception as e:  # keep going; report at the end
                print(f"{sym} {name}: FAILED {str(e)[:160]}", flush=True)


if __name__ == "__main__":
    main()
