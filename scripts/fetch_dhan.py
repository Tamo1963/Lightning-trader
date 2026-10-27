"""Download historical candles from DhanHQ into data/ (git-ignored). Token comes from the DHAN_ACCESS_TOKEN
environment variable and is never printed. Security IDs come from Dhan's instrument master [VERIFY].

Examples (IDs are placeholders):
  python scripts/fetch_dhan.py daily    --id <SPOT_ID> --segment IDX_I   --instrument INDEX  --start 2019-01-01 --end 2026-10-26 --out data/NIFTY_spot_daily.csv
  python scripts/fetch_dhan.py intraday --id <FUT_ID>  --segment NSE_FNO --instrument FUTIDX --start 2024-01-01 --end 2026-10-26 --out data/NIFTY_fut_15m.csv
For a multi-year futures series, fetch each monthly contract and combine with lightning.data.store.stitch_contracts.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.data.dhan import DhanClient
from lightning.data.store import save_csv, validate_intraday


def main():
    a = argparse.ArgumentParser()
    a.add_argument("kind", choices=["daily", "intraday"])
    a.add_argument("--id", required=True); a.add_argument("--segment", required=True)
    a.add_argument("--instrument", required=True)
    a.add_argument("--start", required=True); a.add_argument("--end", required=True)
    a.add_argument("--interval", type=int, default=15); a.add_argument("--out", required=True)
    args = a.parse_args()
    token = os.environ.get("DHAN_ACCESS_TOKEN")
    if not token:
        sys.exit("set DHAN_ACCESS_TOKEN in the environment")
    c = DhanClient(token)
    if args.kind == "daily":
        df = c.daily(args.id, args.segment, args.instrument, args.start, args.end)
    else:
        df = c.intraday(args.id, args.segment, args.instrument, args.start, args.end, args.interval)
        for problem in validate_intraday(df, args.interval):
            print("DATA WARNING:", problem)
    save_csv(df, Path(args.out))
    print(f"saved {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
